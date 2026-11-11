import { expect, test, type Page } from '@playwright/test';

import {
  editorCredentials,
  integratorCredentials,
  logOutFromDesigner,
  reviewerCredentials,
  submitterCredentials,
  superAdminCredentials,
  tenantAdminCredentials,
  useSession,
  viewerCredentials,
} from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import {
  completeTask,
  completeTaskInUi,
  hasTaskFor,
  homeStats,
  instanceAction,
  instanceDetail,
  myTasks,
  shown,
  startInUi,
  startInstance,
  statValue,
  submitTask,
  tableRows,
  taskData,
  taskTitle,
  useFlowCatalog,
  waitForStatus,
  waitForTask,
  withPage,
  gotoHome,
  type FlowModel,
} from './helpers/processFlow';
import { logResult } from './helpers/processesPage';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Process flow: task assignment, Task Review access and task submission.
 *
 * FLW-17..24  assignment by lane, roles without Task Review, other users'
 *             tasks, refresh/logout, late tasks, super admin
 * FLW-25..35  form validation, optional fields, special characters, schema
 *             rules, double submit, stale tab, completed task URL, failed
 *             submit and retry, outcome buttons, suspended instance
 *
 * Every test starts its own instance (no test depends on another).
 */

// Seeded templates (seed/catalog/templates/flow-*): each has one task "E2E Approve Request"
// (Activity_approve_request); they differ in its lane and form.
const flow = useFlowCatalog(test, 'flowt', {
  approval: { name: 'E2E Approval', template: 'flow-single-approval' },
  late: { name: 'E2E Late Task', template: 'flow-single-approval' },
  admin: { name: 'E2E Admin Approval', template: 'flow-admin-approval' },
  nobody: { name: 'E2E Nobody Lane', template: 'flow-unassigned-lane' },
  designers: { name: 'E2E Designers Lane', template: 'flow-designers-lane' },
  request: { name: 'E2E Request Form', template: 'flow-request-form' },
  limits: { name: 'E2E Field Limits', template: 'flow-field-limits' },
  outcome: { name: 'E2E Outcome', template: 'flow-decision-buttons' },
});

/** Starts an instance of model `key` (or of a fresh model) as the submitter and returns its id. */
/** The submitter clicks "Start process" on the model page. */
async function startUi(browser: import('@playwright/test').Browser, key: string): Promise<number> {
  return withPage(browser, submitterCredentials(), (sub) => startInUi(sub, flow, flow.model(key).route));
}

async function start(browser: import('@playwright/test').Browser, key: string | FlowModel): Promise<number> {
  const route = typeof key === 'string' ? flow.model(key).route : key.route;
  return withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, route));
}

/** Instance status (read as the tenant admin, see instanceDetail). */
async function statusAsEditor(browser: import('@playwright/test').Browser, id: number, wanted?: string): Promise<string> {
  return withPage(browser, editorCredentials(), async (ed) =>
    wanted ? (await waitForStatus(ed, id, wanted)).status : (await instanceDetail(ed, id)).status,
  );
}

async function openTask(page: Page, taskId: number, title: string): Promise<void> {
  await page.goto(`/task-review/${taskId}`);
  await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible();
}

test.describe('Process flow: task assignment and Task Review access', { tag: ['@permissions', '@workflow'] }, () => {
  test("FLW-17: A task in the 'Administrators' lane goes to the tenant admin only", async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'admin');
    const id = await start(browser, m);
    await useSession(page, tenantAdminCredentials());
    const task = await waitForTask(page, id);
    await page.goto('/task-review');
    await expect(tableRows(page, m.name)).toHaveCount(1);
    const reviewerHas = await withPage(browser, reviewerCredentials(), (rev) => hasTaskFor(rev, id));
    expect(reviewerHas, 'the reviewer does not get an Administrators task').toBe(false);
    expect((await submitTask(page, task.id, { approval_note: 'Approved by admin' })).status).toBeLessThan(300);
    const status = await statusAsEditor(browser, id, 'complete');

    logResult('FLW-17', {
      scenario: 'Task in the Administrators lane',
      actions: ['Submitter starts', 'Check admin and reviewer inboxes', 'Admin submits'],
      expected: 'Only the tenant admin gets the task and can complete it',
      actual: `Task #${task.id} only in admin's inbox; instance #${id} "${status}"`,
    });
  });

  test('FLW-18: A task in a lane with no members is not given to anyone', async ({ browser }) => {
    const id = await startUi(browser, 'nobody');
    const status = await statusAsEditor(browser, id, 'user_input_required');
    const holders: string[] = [];
    for (const [label, persona] of [
      ['submitter', submitterCredentials()],
      ['reviewer', reviewerCredentials()],
      ['admin', tenantAdminCredentials()],
    ] as const) {
      await withPage(browser, persona, async (p) => {
        // On screen: Task Review lists nothing of this process; and the server agrees.
        await p.goto('/task-review');
        await expect(p.getByRole('heading', { level: 1 }).first()).toBeVisible();
        await expect(p.getByText('Loading…', { exact: true })).toHaveCount(0);
        await expect(tableRows(p, flow.model('nobody').name)).toHaveCount(0);
        if (await hasTaskFor(p, id)) holders.push(label);
      });
    }
    expect(holders, 'no seed user gets the task').toEqual([]);
    test.info().annotations.push({ type: 'needs-confirmation', description: 'Intended behaviour for a lane with no members (unassigned vs error vs fallback).' });

    logResult('FLW-18', {
      scenario: 'Lane named after a group with no members',
      actions: ['Submitter clicks Start process', 'Open Task Review as submitter, reviewer and admin'],
      expected: 'Nobody gets the task; the instance keeps waiting',
      actual: `Instance #${id} "${status}"; task in no inbox`,
    });
  });

  test("FLW-19: A task in the 'Designers' lane cannot be worked through Task Review", async ({ browser }) => {
    const id = await start(browser, 'designers');
    const status = await statusAsEditor(browser, id, 'user_input_required');
    const editorInbox = await withPage(browser, editorCredentials(), async (ed) => {
      const api = (await backendFetch(ed, '/v1.0/m8flow/task-review')).status;
      await ed.goto('/task-review');
      await expect(ed).toHaveURL((url) => url.pathname === '/');
      return api;
    });
    expect(editorInbox, 'editors may not use Task Review').toBe(403);
    expect(await withPage(browser, reviewerCredentials(), (p) => hasTaskFor(p, id))).toBe(false);
    test.info().annotations.push({ type: 'product-question', description: 'Tasks can be assigned to a group whose role has no Task Review access.' });

    logResult('FLW-19', {
      scenario: 'Task assigned to the Designers group (editor)',
      actions: ['Submitter starts', 'Editor opens Task Review', 'Check the reviewer inbox'],
      expected: 'Editor is sent back to Home and the API refuses; nobody else gets the task',
      actual: `Editor Task Review API ${editorInbox}, page redirected to Home; instance "${status}"`,
    });
  });

  for (const role of [
    { label: 'viewer', persona: viewerCredentials },
    { label: 'editor', persona: editorCredentials },
    { label: 'integrator', persona: integratorCredentials },
  ]) {
    test(`FLW-20 [${role.label}]: A role without Task Review cannot see or open the task`, async ({ page, browser }) => {
      const id = await start(browser, 'approval');
      const task = await withPage(browser, reviewerCredentials(), (rev) => waitForTask(rev, id));

      await useSession(page, role.persona());
      await gotoHome(page);
      await expect(page.getByRole('link', { name: 'Task Review', exact: true })).toHaveCount(0);
      await page.goto('/task-review');
      await expect(page).toHaveURL((url) => url.pathname === '/');
      await page.goto(`/task-review/${task.id}`);
      // Viewer/integrator are sent back to Home. Editors may open task pages
      // (only their own tasks, M8F-647), so they get "Task not found." here.
      await expect
        .poll(async () => new URL(page.url()).pathname === '/' || (await page.getByText('Task not found.', { exact: true }).isVisible()), {
          message: 'the task page is not shown',
          timeout: 20_000,
        })
        .toBe(true);
      await expect(page.getByRole('button', { name: 'Submit', exact: true })).toHaveCount(0);
      const list = (await backendFetch(page, '/v1.0/m8flow/task-review')).status;
      const submit = (await submitTask(page, task.id, { approval_note: 'not allowed' })).status;
      expect(list).toBe(403);
      expect([403, 404]).toContain(submit);
      expect(await withPage(browser, reviewerCredentials(), (rev) => hasTaskFor(rev, id)), 'task still pending').toBe(true);

      logResult(`FLW-20 [${role.label}]`, {
        scenario: `${role.label} and someone else's pending task`,
        actions: ['Open Home', 'Open /task-review and /task-review/<id>', 'Call the list and submit APIs'],
        expected: 'No Task Review link; /task-review goes back to Home; the task page is not shown (Home, or "Task not found." for editors); the APIs refuse; the task stays pending',
        actual: `Task page not shown (${new URL(page.url()).pathname}); list API ${list}, submit API ${submit}; task #${task.id} still pending`,
      });
    });
  }

  for (const pair of [
    { label: 'submitter on the reviewer task', key: 'approval', owner: reviewerCredentials, other: submitterCredentials },
    { label: 'reviewer on the admin task', key: 'admin', owner: tenantAdminCredentials, other: reviewerCredentials },
  ]) {
    test(`FLW-21 [${pair.label}]: A user cannot open or submit a task assigned to someone else`, async ({ page, browser }) => {
      const id = await start(browser, pair.key);
      const task = await withPage(browser, pair.owner(), (own) => waitForTask(own, id));
      await useSession(page, pair.other());
      await page.goto(`/task-review/${task.id}`);
      const notFound = page.getByText('Task not found.', { exact: true });
      const heading = page.getByRole('heading', { level: 1, name: taskTitle(task), exact: true });
      await expect(notFound.or(heading).first()).toBeVisible();
      const visible = (await heading.count()) > 0;
      // Seeing someone else's task (its form and data) is reported as a possible
      // defect: the test is marked failed, but the checks below still run.
      expect.soft(visible, `POSSIBLE DEFECT: ${pair.label}: another user's task #${task.id} can be opened in Task Review`).toBe(false);
      let uiError = 'no Submit button';
      if (visible && (await page.getByRole('button', { name: 'Submit', exact: true }).isEnabled())) {
        await page.getByLabel('Approval note').fill('not mine');
        await page.getByRole('button', { name: 'Submit', exact: true }).click();
        await expect(page.getByRole('alert')).toBeVisible();
        uiError = (await page.getByRole('alert').innerText()).trim();
        await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
      }
      const submit = (await submitTask(page, task.id, { approval_note: 'not mine' })).status;
      expect([403, 404], 'submitting another user\'s task is refused').toContain(submit);
      expect(await withPage(browser, pair.owner(), (own) => hasTaskFor(own, id)), 'still pending for its owner').toBe(true);

      logResult(`FLW-21 [${pair.label}]`, {
        scenario: `Open and submit a task assigned to another user (${pair.label})`,
        actions: ['Open /task-review/<id>', 'POST submit'],
        expected: '"Task not found." with no Submit; any submit is refused; the task stays with its owner',
        actual: `Task page ${visible ? 'OPENED (possible defect)' : '"Task not found."'}; UI submit: ${uiError}; submit API ${submit}; task #${task.id} still pending`,
      });
    });
  }

  test('FLW-22: The task stays available after refresh, navigation and logout/login', async ({ page, browser }) => {
    const m = flow.model('approval');
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const row = () => page.getByRole('table').getByRole('button').filter({ hasText: m.name });

    await page.goto('/task-review');
    await expect(row()).not.toHaveCount(0);
    await page.reload();
    await expect(row()).not.toHaveCount(0);
    await openTask(page, task.id, taskTitle(task));
    await gotoHome(page);
    await page.goBack();
    await expect(page.getByRole('heading', { level: 1, name: taskTitle(task), exact: true })).toBeVisible();

    await logOutFromDesigner(page);
    await useSession(page, reviewerCredentials());
    await gotoHome(page);
    const link = page.locator(`a[href="/task-review/${task.id}"]`);
    await expect(link).toHaveCount(1);
    await link.click();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
    expect((await myTasks(page)).filter((t) => t.id === task.id)).toHaveLength(1);

    logResult('FLW-22', {
      scenario: 'Approver leaves and comes back before completing',
      actions: ['Refresh Task Review', 'Open task, go Home, go back', 'Log out and log in', 'Open the task from Home "My tasks"'],
      expected: 'The task is listed once every time; the Home link opens the same task',
      actual: `Task #${task.id} listed after refresh, navigation and a fresh login; Home link opens it`,
    });
  });

  test('FLW-23: A task created while the inbox is open appears without reloading', async ({ page, browser }) => {
    test.setTimeout(120_000);
    const m = await flow.fresh(browser, 'late');
    await useSession(page, reviewerCredentials());
    await page.goto('/task-review');
    await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0);
    await expect(tableRows(page, m.name)).toHaveCount(0);

    const id = await start(browser, m);
    const row = tableRows(page, m.name);
    await expect(row).toHaveCount(1, { timeout: 45_000 }); // the inbox refreshes itself every 30 s
    await expect(row).toContainText('New');

    logResult('FLW-23', {
      scenario: 'Task created while Task Review is open',
      actions: ['Reviewer opens Task Review', 'Submitter starts an instance', 'Wait without reloading'],
      expected: 'The task appears within the automatic refresh, marked "New"',
      actual: `Instance #${id}'s task appeared without a reload`,
    });
  });

  test('FLW-24: Super admin can see pending tasks but cannot submit them', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    const task = await withPage(browser, reviewerCredentials(), (rev) => waitForTask(rev, id));
    await useSession(page, superAdminCredentials(), 'platformAdmin');
    const list = await backendFetch(page, '/v1.0/m8flow/task-review?per_page=100');
    const listed =
      list.status === 200 && ((list.body as { results?: { id: number }[] }).results ?? []).some((t) => t.id === task.id);
    // Confirmed behaviour: the super admin can see the task (monitoring) but cannot
    // submit it, neither on screen (no Submit button) nor through the API (403).
    expect(list.status, 'super admin can read Task Review').toBe(200);
    expect(listed, 'the pending task is listed for the super admin').toBe(true);
    await page.goto('/task-review');
    await expect(tableRows(page, flow.model('approval').name).first()).toBeVisible();
    await openTask(page, task.id, taskTitle(task));
    // Confirmed behaviour: the super admin sees the task with a Submit button that stays
    // disabled, even after the form is filled in.
    const submitButton = page.getByRole('button', { name: 'Submit', exact: true });
    await expect(submitButton).toBeVisible();
    const note = page.getByLabel('Approval note');
    if (await note.isEditable().catch(() => false)) await note.fill('super admin');
    await expect(submitButton).toBeDisabled();
    // API contract (m8flow-backend task_review_controller.submit_task_review): a caller who
    // may not submit the task gets 403 (404 = task not visible, 409 = already completed,
    // 400 = missing fields). The session was just used above, so a 401 here is a real fault.
    const denied = await submitTask(page, task.id, { approval_note: 'super admin' });
    const submit = denied.status;
    expect(submit, `super admin submit is refused as forbidden (answer: ${JSON.stringify(denied.body).slice(0, 200)})`).toBe(403);
    // The invariant either way: the task is not completed and is still waiting for the reviewer.
    expect(await withPage(browser, reviewerCredentials(), (rev) => hasTaskFor(rev, id)), 'still pending').toBe(true);

    logResult('FLW-24', {
      scenario: "Super admin and a tenant's pending task",
      actions: ['Login through Platform Admin Sign In', 'Open Task Review', 'Open the task and fill the note', 'Try to submit it through the API'],
      expected: 'The task is listed and opens; Submit stays disabled; the API submit is refused (403); the task stays pending for the reviewer',
      actual: `Task #${task.id} listed and opened; Submit disabled; API submit ${submit}; task still pending`,
    });
  });
});

test.describe('Process flow: task input validation and submission', { tag: ['@validation', '@reliability'] }, () => {
  test('FLW-25 and FLW-26: Several required fields missing at once, and entered values are kept', async ({ page, browser }) => {
    const id = await start(browser, 'request');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    let submits = 0;
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes(`/task-review/${task.id}/submit`)) submits += 1;
    });
    await openTask(page, task.id, taskTitle(task));
    const submit = page.getByRole('button', { name: 'Submit', exact: true });

    await submit.click();
    const messages = ['Request title is required.', 'Amount is required.', 'Due date is required.'];
    for (const message of messages) await expect(page.getByText(message, { exact: true })).toBeVisible();
    await expect(page.getByText('Comment is required.', { exact: true })).toHaveCount(0);
    expect(submits, 'no submit request while required fields are empty').toBe(0);

    // FLW-26: fill some fields, leave one required field empty.
    await page.getByLabel('Request title').fill('Monitor');
    await page.getByLabel('Comment').fill('Optional note');
    await page.getByLabel('Due date').fill('2026-12-20');
    await submit.click();
    await expect(page.getByText('Amount is required.', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Request title')).toHaveValue('Monitor');
    await expect(page.getByLabel('Comment')).toHaveValue('Optional note');
    await expect(page.getByLabel('Due date')).toHaveValue('2026-12-20');
    expect(submits).toBe(0);

    await page.getByLabel('Amount').fill('300');
    await submit.click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    expect(submits).toBe(1);
    const saved = await withPage(browser, editorCredentials(), async (ed) => {
      await waitForStatus(ed, id, 'complete');
      return taskData(ed, id, 'Activity_approve_request');
    });
    expect(saved).toMatchObject({ request_title: 'Monitor', amount: 300, due_date: '2026-12-20', comment: 'Optional note' });

    logResult('FLW-25/26', {
      scenario: 'Required fields missing, then partly filled',
      actions: ['Submit the empty form', 'Fill all but Amount and submit', 'Fill Amount and submit'],
      expected: 'Each empty required field shows its message and nothing is sent; filled values stay; the final submit saves all values',
      actual: `Messages shown, 0 requests until valid; saved ${JSON.stringify(saved)}`,
      messages: [...messages, 'Amount is required.'],
    });
  });

  test('FLW-27: Optional fields left empty are not saved; filled ones are', async ({ browser }) => {
    const required = { request_title: 'Chair', amount: 80, due_date: '2026-12-21' };
    const onScreen = { 'Request title': 'Chair', Amount: '80', 'Due date': '2026-12-21' };
    const runs: Record<string, Record<string, unknown>> = {};
    // Filled in on the Task Review form: Comment left empty, then filled.
    for (const [label, extra] of [
      ['empty', {}],
      ['filled', { Comment: 'Please hurry' }],
    ] as const) {
      const id = await startUi(browser, 'request');
      await withPage(browser, reviewerCredentials(), (rev) => completeTaskInUi(rev, id, { ...onScreen, ...extra }));
      runs[label] = await withPage(browser, editorCredentials(), async (ed) => {
        await waitForStatus(ed, id, 'complete');
        return taskData(ed, id, 'Activity_approve_request');
      });
    }
    expect(runs.empty).toMatchObject(required);
    expect(runs.empty).not.toHaveProperty('comment');
    expect(runs.filled).toMatchObject({ ...required, comment: 'Please hurry' });

    // An explicit null for a text field is checked against the form schema and refused.
    const nullId = await start(browser, 'request');
    const nullSubmit = await withPage(browser, reviewerCredentials(), async (rev) => {
      const task = await waitForTask(rev, nullId);
      const refused = await submitTask(rev, task.id, { ...required, comment: null });
      await submitTask(rev, task.id, required);
      return refused;
    });
    expect(nullSubmit.status).toBe(400);
    expect(JSON.stringify(nullSubmit.body)).toContain("is not of type 'string'");

    logResult('FLW-27', {
      scenario: 'Optional field empty vs filled',
      actions: ['Fill the form in Task Review without Comment and submit', 'Fill it with Comment and submit', 'Send Comment = null through the API'],
      expected: 'An empty optional value is not saved; a filled one is saved exactly; null for a text field is refused (schema check)',
      actual: `empty: ${JSON.stringify(runs.empty)}; filled: ${JSON.stringify(runs.filled)}; null: ${nullSubmit.status}`,
      messages: [JSON.stringify(nullSubmit.body)],
    });
  });

  test('FLW-28: Special characters, other alphabets and long text are saved unchanged', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    let dialogs = 0;
    page.on('dialog', async (d) => {
      dialogs += 1;
      await d.dismiss();
    });
    const task = await waitForTask(page, id);
    const value = `<b>bold</b> & "quotes" <img src=x onerror=alert(1)> Prüfung 测试 🚀`;
    await openTask(page, task.id, taskTitle(task));
    await page.getByLabel('Approval note').fill(value);
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    const saved = await withPage(browser, editorCredentials(), async (ed) => {
      await waitForStatus(ed, id, 'complete');
      return taskData(ed, id, 'Activity_approve_request');
    });
    expect(saved.approval_note).toBe(value);
    expect(dialogs).toBe(0);

    // Long text: the note is limited to 255 characters (confirmed as sufficient);
    // anything longer is saved as its first 255 characters.
    const NOTE_LIMIT = 255;
    const longValue = `Long note ${flow.stamp} ${'x'.repeat(1000)}`;
    const longId = await start(browser, 'approval');
    await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, longId, { approval_note: longValue }));
    const longSaved = await withPage(browser, editorCredentials(), async (ed) => {
      await waitForStatus(ed, longId, 'complete');
      return String((await taskData(ed, longId, 'Activity_approve_request')).approval_note ?? '');
    });
    expect(longSaved.length, `a ${longValue.length}-character note is saved as its first ${NOTE_LIMIT} characters`).toBe(NOTE_LIMIT);
    expect(longSaved, 'what is saved is the start of the entered text').toBe(longValue.slice(0, NOTE_LIMIT));

    logResult('FLW-28', {
      scenario: 'HTML, quotes, other alphabets and emoji; then a 1,000+ character note',
      actions: ['Enter the special text in Approval note and submit', 'Submit a long note'],
      expected: `Values are saved exactly; no script or pop-up runs; a long note is kept up to ${NOTE_LIMIT} characters`,
      actual: `special text saved unchanged, ${dialogs} pop-ups; long note ${longValue.length} -> ${longSaved.length} characters saved`,
    });
  });

  test('FLW-29: Field length rules from the schema', async ({ page, browser }) => {
    const id = await start(browser, 'limits');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    await openTask(page, task.id, taskTitle(task));
    const code = page.getByLabel('Code');
    const submit = page.getByRole('button', { name: 'Submit', exact: true });

    await code.fill('abcd');
    await submit.click();
    const tooShort = 'Code must be at least 5 characters.';
    await expect(page.getByText(tooShort, { exact: true })).toBeVisible();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));

    // maxLength (10) is not checked by the form; record what the server does.
    await code.fill('abcdefghijk');
    await submit.click();
    const accepted = await page
      .waitForURL((url) => url.pathname === '/task-review', { timeout: 10_000 })
      .then(() => true)
      .catch(() => false);
    if (accepted) {
      test.info().annotations.push({ type: 'gap', description: 'maxLength from the form schema is not enforced (11 characters were accepted).' });
    } else {
      await code.fill('abcde');
      await submit.click();
      await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    }
    await statusAsEditor(browser, id, 'complete');

    logResult('FLW-29', {
      scenario: 'Code field with minLength 5 and maxLength 10',
      actions: ['Submit 4 characters', 'Submit 11 characters', accepted ? '(accepted)' : 'Submit 5 characters'],
      expected: '4 characters refused with a message; the 10-character limit behaviour is recorded',
      actual: `minLength enforced; maxLength ${accepted ? 'NOT enforced (11 characters accepted)' : 'enforced'}`,
      messages: [tooShort],
    });
  });

  test('FLW-30: Double-clicking Submit completes the task once', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const statuses: number[] = [];
    page.on('response', (r) => {
      if (r.request().method() === 'POST' && r.url().includes(`/task-review/${task.id}/submit`)) statuses.push(r.status());
    });
    await openTask(page, task.id, taskTitle(task));
    await page.getByLabel('Approval note').fill('Double click');
    await page.getByRole('button', { name: 'Submit', exact: true }).dblclick();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    await page.waitForLoadState('networkidle');
    const ok = statuses.filter((s) => s < 300).length;
    expect(ok, `submit responses: ${statuses.join(', ')}`).toBe(1);
    expect(statuses.filter((s) => s >= 300 && s !== 409), 'a second submit is only refused as already completed').toEqual([]);
    expect(await hasTaskFor(page, id)).toBe(false);
    const status = await statusAsEditor(browser, id, 'complete');

    logResult('FLW-30', {
      scenario: 'Double-click Submit',
      actions: ['Fill the form', 'Double-click Submit'],
      expected: 'Exactly one completion; any second request is refused (409); the task leaves the inbox once',
      actual: `Submit responses [${statuses.join(', ')}]; instance "${status}"`,
    });
  });

  test('FLW-31: Submitting a task that was already completed in another tab is refused', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const tabB = await page.context().newPage();
    await openTask(page, task.id, taskTitle(task));
    await openTask(tabB, task.id, taskTitle(task));

    await page.getByLabel('Approval note').fill('From tab A');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));

    await tabB.getByLabel('Approval note').fill('From tab B');
    await tabB.getByRole('button', { name: 'Submit', exact: true }).click();
    const error = tabB.getByRole('alert');
    await expect(error).toBeVisible();
    await expect(tabB).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
    const message = (await error.innerText()).trim();
    const saved = await withPage(browser, editorCredentials(), async (ed) => {
      await waitForStatus(ed, id, 'complete');
      return taskData(ed, id, 'Activity_approve_request');
    });
    expect(saved.approval_note).toBe('From tab A');
    await tabB.close();

    logResult('FLW-31', {
      scenario: 'Same task open in two tabs',
      actions: ['Submit in tab A', 'Submit in tab B'],
      expected: 'Tab B shows an error and stays on the task; only tab A\'s values are saved',
      actual: `Tab B error shown; saved note "${saved.approval_note}"`,
      messages: [message],
    });
  });

  test('FLW-32: A completed task opened by its URL cannot be submitted again', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await completeTask(page, id, { approval_note: 'Done' });
    await statusAsEditor(browser, id, 'complete');
    await page.goto(`/task-review/${task.id}`);
    const notFound = page.getByText('Task not found.', { exact: true });
    const completed = page.getByText('Completed', { exact: true });
    await expect(notFound.or(completed).first()).toBeVisible();
    const submit = page.getByRole('button', { name: 'Submit', exact: true });
    if (await submit.count()) await expect(submit).toBeDisabled();
    const shownAs = (await notFound.count()) ? '"Task not found."' : 'Completed (form locked)';
    const again = (await submitTask(page, task.id, { approval_note: 'Again' })).status;
    expect(again).toBeGreaterThanOrEqual(400);
    test.info().annotations.push({ type: 'needs-confirmation', description: `Completed task URL shows ${shownAs}.` });

    logResult('FLW-32', {
      scenario: 'Open a completed task by its URL',
      actions: ['Complete the task', 'Open /task-review/<id>', 'POST submit again'],
      expected: '"Task not found." or a locked Completed task; no way to submit again',
      actual: `Page shows ${shownAs}; second submit API ${again}`,
    });
  });

  test('FLW-33: A failed submit (server error, then network drop) can be retried', { tag: '@counts' }, async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const before = await homeStats(page);
    await openTask(page, task.id, taskTitle(task));
    const note = page.getByLabel('Approval note');
    await note.fill('Retry after failure');
    const submit = page.getByRole('button', { name: 'Submit', exact: true });
    const pattern = `**/v1.0/m8flow/task-review/${task.id}/submit`;
    const errors: string[] = [];

    await page.route(pattern, (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ message: 'E2E simulated server error' }) }),
    );
    await submit.click();
    await expect(page.getByRole('alert')).toBeVisible();
    errors.push((await page.getByRole('alert').innerText()).trim());
    await page.unroute(pattern);

    await page.route(pattern, (route) => route.abort('connectionreset'));
    await submit.click();
    await expect(page.getByRole('alert')).toBeVisible();
    errors.push((await page.getByRole('alert').innerText()).trim());
    await page.unroute(pattern);
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
    await expect(note).toHaveValue('Retry after failure');
    expect(await hasTaskFor(page, id), 'still pending after the failures').toBe(true);

    await submit.click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    expect(await hasTaskFor(page, id)).toBe(false);
    const after = await homeStats(page);
    expect(after.tasks_waiting_on_me).toBe(before.tasks_waiting_on_me! - 1);
    await gotoHome(page);
    await expect(statValue(page, 'Tasks waiting on me')).toHaveText(shown(after.tasks_waiting_on_me));
    const status = await statusAsEditor(browser, id, 'complete');

    logResult('FLW-33', {
      scenario: 'Submit fails twice, then succeeds',
      actions: ['Submit with a mocked 500', 'Submit with a dropped connection', 'Submit normally'],
      expected: 'Errors are shown, the page and values stay, the task stays pending; the retry completes it; Task Review, Home and Process Instances agree',
      actual: `Errors shown; retry completed instance #${id} ("${status}"); Tasks waiting on me ${shown(before.tasks_waiting_on_me)} -> ${shown(after.tasks_waiting_on_me)}`,
      messages: errors,
    });
  });

  test('FLW-34: A decision task shows Approve / Reject buttons and each leads to its own path', async ({ page, browser }) => {
    await useSession(page, reviewerCredentials());
    const results: string[] = [];
    for (const choice of [
      { button: 'Approve', end: 'EndEvent_1' },
      { button: 'Reject', end: 'EndEvent_other' },
    ]) {
      const id = await start(browser, 'outcome');
      const task = await waitForTask(page, id);
      await openTask(page, task.id, taskTitle(task));
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Reject', exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Submit', exact: true })).toHaveCount(0);
      await page.getByRole('button', { name: choice.button, exact: true }).click();
      await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
      const ended = await withPage(browser, editorCredentials(), async (ed) => {
        const detail = await waitForStatus(ed, id, 'complete');
        return detail.tasks.filter((t) => t.bpmn_identifier.startsWith('EndEvent') && /^completed$/i.test(t.state)).map((t) => t.bpmn_identifier);
      });
      expect(ended).toEqual([choice.end]);
      results.push(`${choice.button} -> ${ended.join(',')}`);
    }

    logResult('FLW-34', {
      scenario: 'Task followed by an outcome gateway',
      actions: ['Open the task', 'Click Approve (instance 1) / Reject (instance 2)'],
      expected: 'Approve and Reject buttons instead of Submit; each ends at its own end event',
      actual: results.join('; '),
    });
  });

  test('FLW-35: The task of a suspended instance cannot be submitted until it is resumed', async ({ page, browser }) => {
    const id = await start(browser, 'approval');
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    // Suspend/resume: the starter or a tenant admin (M8F-627).
    expect(await withPage(browser, tenantAdminCredentials(), (ad) => instanceAction(ad, id, 'suspend'))).toBeLessThan(300);

    await openTask(page, task.id, taskTitle(task));
    const suspended = 'This process instance is suspended. Resume it before submitting.';
    await expect(page.getByText(suspended, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit', exact: true })).toBeDisabled();

    expect(await withPage(browser, tenantAdminCredentials(), (ad) => instanceAction(ad, id, 'resume'))).toBeLessThan(300);
    await page.reload();
    await expect(page.getByText(suspended, { exact: true })).toHaveCount(0);
    await page.getByLabel('Approval note').fill('After resume');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    const status = await statusAsEditor(browser, id, 'complete');

    logResult('FLW-35', {
      scenario: 'Instance suspended while its task waits',
      actions: ['Editor suspends', 'Reviewer opens the task', 'Editor resumes', 'Reviewer submits'],
      expected: 'Suspended message and disabled Submit; after resume the submit works',
      actual: `Message shown while suspended; instance #${id} "${status}" after resume`,
      messages: [suspended],
    });
  });
});
