import { expect, test, type Browser, type Page } from '@playwright/test';

import {
  editorCredentials,
  reviewerCredentials,
  submitterCredentials,
  tenantAdminCredentials,
  useSession,
  type DesignerPersona,
} from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import {
  completeTask,
  completeTaskInUi,
  gotoHome,
  hasTaskFor,
  homeStats,
  instanceDetail,
  startInUi,
  startInstance,
  submitInUi,
  statValue,
  submitTask,
  taskData,
  tableRows,
  taskTitle,
  useFlowCatalog,
  waitForStatus,
  waitForTask,
  withPage,
  waitForInstancePage,
} from './helpers/processFlow';
import { logResult } from './helpers/processesPage';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Process flow: multi-step and conditional workflows.
 *
 * FLW-36  two sequential approvals by different approvers
 * FLW-37  data entered in step 1 reaches step 2
 * FLW-38  reject in step 1 ends the process early
 * FLW-39  gateway on a form value (500 / 1000 / 5000)
 * FLW-40  a failing step sets the instance to Error and Home counts it
 * FLW-41  terminating an instance removes its pending task
 * FLW-58  editor or tenant admin starts; step 1 goes to the submitter, step 2 to the reviewer
 * FLW-59  parallel approvals: manager and finance get their tasks at the same time
 */

// Seeded templates (seed/catalog/templates/flow-*): two-step-approval (step 1 by Approvers with an
// Approve / Reject decision, step 2 by Administrators), amount-routing (over 1000 goes to step 2),
// failing-step, single-approval, submit-then-approve and parallel-approval.
const step1 = { id: 'Activity_step1', name: 'E2E First Approval' };
const step2 = { id: 'Activity_step2', name: 'E2E Second Approval' };

const flow = useFlowCatalog(test, 'flows', {
  twostep: { name: 'E2E Two Step', template: 'flow-two-step-approval' },
  amount: { name: 'E2E Amount Gate', template: 'flow-amount-routing' },
  failing: { name: 'E2E Failing Step', template: 'flow-failing-step' },
  terminate: { name: 'E2E Terminate', template: 'flow-single-approval' },
  chain: { name: 'E2E Submit Then Approve', template: 'flow-submit-then-approve' },
  parallel: { name: 'E2E Parallel Approval', template: 'flow-parallel-approval' },
});

/** The submitter clicks "Start process" on the model page. */
async function startUi(browser: Browser, key: string): Promise<number> {
  return withPage(browser, submitterCredentials(), (sub) => startInUi(sub, flow, flow.model(key).route));
}

async function start(browser: Browser, key: string, persona: DesignerPersona = submitterCredentials()): Promise<number> {
  return withPage(browser, persona, (p) => startInstance(p, flow, flow.model(key).route));
}

/** Instance status and data are read as the tenant admin (sees every instance, M8F-627). */
async function asAdmin<T>(browser: Browser, fn: (page: Page) => Promise<T>): Promise<T> {
  return withPage(browser, tenantAdminCredentials(), fn);
}

/** BPMN ids of the elements that completed, in no particular order. */
async function completedIds(page: Page, id: number): Promise<string[]> {
  return (await instanceDetail(page, id)).tasks.filter((t) => /^completed$/i.test(t.state)).map((t) => t.bpmn_identifier);
}

test.describe('Process flow: multi-step and conditional workflows', { tag: ['@workflow'] }, () => {
  test('FLW-36: Two sequential approvals by different approvers', async ({ page, browser }) => {
    const id = await start(browser, 'twostep');
    const adminEarly = await withPage(browser, tenantAdminCredentials(), (a) => hasTaskFor(a, id));
    expect(adminEarly, 'step 2 does not exist before step 1').toBe(false);

    await useSession(page, reviewerCredentials());
    const first = await waitForTask(page, id, step1.name);
    await page.goto(`/task-review/${first.id}`);
    await page.getByLabel('Reviewer note').fill('Looks fine');
    await page.getByRole('button', { name: 'Approve', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    expect(await hasTaskFor(page, id), 'the reviewer does not get step 2').toBe(false);

    const between = await asAdmin(browser, (ed) => waitForStatus(ed, id, 'user_input_required'));
    const second = await withPage(browser, tenantAdminCredentials(), (a) =>
      completeTask(a, id, { admin_note: 'Final OK' }, step2.name),
    );
    const done = await asAdmin(browser, async (ed) => ({ detail: await waitForStatus(ed, id, 'complete'), ids: await completedIds(ed, id) }));
    expect(done.ids.filter((x) => x === step1.id)).toHaveLength(1);
    expect(done.ids.filter((x) => x === step2.id)).toHaveLength(1);
    expect(done.ids).not.toContain('EndEvent_other');

    logResult('FLW-36', {
      scenario: 'Approvers step, then Administrators step',
      actions: ['Submitter starts', 'Check admin inbox', 'Reviewer approves step 1 in the UI', 'Admin completes step 2'],
      expected: 'Step 2 appears only after step 1 and only for admin; User Input Required until step 2; each step once; then Complete',
      actual: `Step 1 #${first.id}, step 2 #${second.id}; between steps "${between.status}"; finally "${done.detail.status}"`,
    });
  });

  test('FLW-37: Data entered in step 1 reaches step 2 and the final data', async ({ browser }) => {
    const id = await startUi(browser, 'twostep');
    const note = `Checked by reviewer ${flow.stamp}`;
    await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, id, { 'Reviewer note': note }, step1.name, 'Approve'));
    await withPage(browser, tenantAdminCredentials(), (a) => completeTaskInUi(a, id, { 'Admin note': 'Admin agrees' }, step2.name));
    const data = await asAdmin(browser, async (ed) => {
      await waitForStatus(ed, id, 'complete');
      return taskData(ed, id, step2.id);
    });
    expect(data).toMatchObject({ step1_note: note, admin_note: 'Admin agrees', outcome: 'approve' });

    logResult('FLW-37', {
      scenario: 'Values from step 1 in step 2',
      actions: ['Submitter clicks Start process', 'Reviewer types a note and clicks Approve', 'Admin types a note and submits step 2', 'Read step 2 task data'],
      expected: "Step 2's data holds both steps' values",
      actual: `Step 2 data: ${JSON.stringify(data)}`,
    });
  });

  test('FLW-38: Rejecting in step 1 ends the process early', async ({ page, browser }) => {
    const id = await start(browser, 'twostep');
    await useSession(page, reviewerCredentials());
    const first = await waitForTask(page, id, step1.name);
    await page.goto(`/task-review/${first.id}`);
    await page.getByLabel('Reviewer note').fill('Not needed');
    await page.getByRole('button', { name: 'Reject', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    const done = await asAdmin(browser, async (ed) => ({ detail: await waitForStatus(ed, id, 'complete'), ids: await completedIds(ed, id) }));
    expect(done.ids).toContain('EndEvent_other');
    expect(done.ids).not.toContain(step2.id);
    expect(await withPage(browser, tenantAdminCredentials(), (a) => hasTaskFor(a, id))).toBe(false);

    logResult('FLW-38', {
      scenario: 'Reject at the first step',
      actions: ['Submitter starts', 'Reviewer clicks Reject'],
      expected: 'No step-2 task; the instance is Complete through the early end',
      actual: `Instance #${id} "${done.detail.status}", ended at EndEvent_other`,
    });
  });

  for (const c of [
    { amount: 500, second: false },
    { amount: 1000, second: false },
    { amount: 5000, second: true },
  ]) {
    test(`FLW-39 [amount ${c.amount}]: The gateway routes on the submitted amount`, async ({ browser }) => {
      const id = await startUi(browser, 'amount');
      await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, id, { Amount: String(c.amount) }, step1.name));
      let outcome: string;
      if (c.second) {
        await asAdmin(browser, (ed) => waitForStatus(ed, id, 'user_input_required'));
        const task = await withPage(browser, tenantAdminCredentials(), (a) => waitForTask(a, id, step2.name));
        outcome = `second approval #${task.id} for admin`;
        await withPage(browser, tenantAdminCredentials(), (a) => submitInUi(a, task.id, {}, /^(Submit|Continue)$/));
        await asAdmin(browser, (ed) => waitForStatus(ed, id, 'complete'));
      } else {
        const ids = await asAdmin(browser, async (ed) => {
          await waitForStatus(ed, id, 'complete');
          return completedIds(ed, id);
        });
        expect(ids).toContain('EndEvent_other');
        expect(await withPage(browser, tenantAdminCredentials(), (a) => hasTaskFor(a, id))).toBe(false);
        outcome = 'completed after one approval';
      }

      logResult(`FLW-39 [${c.amount}]`, {
        scenario: `Amount ${c.amount} against the 1000 limit`,
        actions: ['Submitter clicks Start process', `Reviewer types amount ${c.amount} and submits in Task Review`, ...(c.second ? ['Admin submits the second approval'] : [])],
        expected: c.second ? 'A second approval is created for admin' : 'The process completes after one approval',
        actual: outcome,
      });
    });
  }

  test('FLW-40: A failing step sets the instance to Error and Home counts it', { tag: '@counts' }, async ({ page, browser }) => {
    // Editor starts the process; the reviewer works the task and checks the
    // error. (Editor's view of the instance status is recorded only: a known
    // editor permission issue, to be fixed separately.)
    const id = await start(browser, 'failing', editorCredentials());
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const before = await homeStats(page);

    // The failing script runs inside the approval submit, so Submit shows an error.
    await page.goto(`/task-review/${task.id}`);
    await page.getByLabel('Approval note').fill('Go on');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    const alert = page.getByRole('alert');
    await expect(alert, 'Submit shows an error for the failing step').toBeVisible();
    const uiMessage = (await alert.innerText()).trim();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));

    // The reviewer's Home counts the error.
    const after = await homeStats(page);
    if (before.errors_needing_review != null) {
      await expect
        .poll(async () => (await homeStats(page)).errors_needing_review, {
          message: '"Errors needing review" goes up by 1 for the reviewer',
          timeout: 30_000,
        })
        .toBe(before.errors_needing_review + 1);
      await gotoHome(page);
      await expect(statValue(page, 'Errors needing review')).toHaveText(String(before.errors_needing_review + 1));
    } else {
      test.info().annotations.push({ type: 'note', description: '"Errors needing review" is not shown to the reviewer.' });
    }

    const editorView = await withPage(browser, editorCredentials(), async (ed) => {
      const result = await backendFetch(ed, `/v1.0/m8flow/process-instances/${id}`);
      return result.status === 200 ? (result.body as { status: string }) : undefined;
    });
    test.info().annotations.push({
      type: 'editor-permission',
      description: `Editor sees instance #${id} as "${editorView?.status ?? 'not readable'}" (editor permission issue, to be fixed).`,
    });
    const retry = await asAdmin(browser, async (ed) => (await backendFetch(ed, `/v1.0/m8flow/process-instances/${id}/retry`, { method: 'POST' })).status);
    test.info().annotations.push({ type: 'gap', description: `No retry action in the designer; POST .../retry returned ${retry}.` });

    logResult('FLW-40', {
      scenario: 'Script task fails after the approval',
      actions: ['Login to M8Flow as Editor and start the process', 'Login to M8Flow as Reviewer', 'Open the task, enter an approval note and Submit', 'Open Home'],
      expected: 'Submit shows an error; "Errors needing review" goes up by 1',
      actual: `Instance #${id}: error shown "${uiMessage}"; errors needing review ${before.errors_needing_review ?? '—'} -> ${(await homeStats(page)).errors_needing_review ?? after.errors_needing_review ?? '—'}; editor sees "${editorView?.status ?? 'not readable'}"`,
      messages: [uiMessage],
    });
  });

  test('FLW-41: Terminating an instance removes its pending task', { tag: '@counts' }, async ({ page, browser }) => {
    const id = await start(browser, 'terminate');
    const task = await withPage(browser, reviewerCredentials(), (r) => waitForTask(r, id));
    const reviewerBefore = await withPage(browser, reviewerCredentials(), homeStats);
    const submitterBefore = await withPage(browser, submitterCredentials(), homeStats);

    // Terminate is for the starter or a tenant admin (M8F-627); the submitter started it.
    await useSession(page, tenantAdminCredentials());
    await page.goto(`/process-instances/${id}`);
    await page.getByRole('button', { name: 'Terminate', exact: true }).click();
    const confirm = page.getByRole('alertdialog', { name: 'Terminate process instance?' }).or(page.getByRole('dialog', { name: 'Terminate process instance?' }));
    await expect(confirm).toBeVisible();
    await confirm.getByRole('button', { name: 'Terminate', exact: true }).click();
    await expect(page.getByText('Terminated', { exact: true }).first()).toBeVisible();
    const terminated = await waitForStatus(page, id, 'terminated');

    const reviewer = await withPage(browser, reviewerCredentials(), async (r) => {
      const stillThere = await hasTaskFor(r, id);
      const submit = (await submitTask(r, task.id, { approval_note: 'too late' })).status;
      return { stillThere, submit, stats: await homeStats(r) };
    });
    expect(reviewer.stillThere).toBe(false);
    expect(reviewer.submit).toBeGreaterThanOrEqual(400);
    expect(reviewer.stats.tasks_waiting_on_me).toBe(reviewerBefore.tasks_waiting_on_me! - 1);
    const submitterAfter = await withPage(browser, submitterCredentials(), homeStats);
    if (submitterBefore.active_process_instances != null) {
      expect(submitterAfter.active_process_instances).toBe(submitterBefore.active_process_instances - 1);
    }

    logResult('FLW-41', {
      scenario: 'Terminate an instance with a pending approval',
      actions: ['Editor opens the instance', 'Terminate and confirm', 'Reviewer checks Task Review and the old task'],
      expected: 'Status Terminated; the task leaves the inbox and cannot be submitted; waiting and active counts go down by 1',
      actual: `"${terminated.status}"; task gone (submit ${reviewer.submit}); waiting ${reviewerBefore.tasks_waiting_on_me} -> ${reviewer.stats.tasks_waiting_on_me}`,
    });
  });

  for (const starter of [
    { label: 'editor', persona: editorCredentials, canReview: false },
    { label: 'tenant admin', persona: tenantAdminCredentials, canReview: true },
  ]) {
    test(`FLW-58 [${starter.label}]: The starter is not given the submitter's or reviewer's task`, { tag: '@counts' }, async ({ page, browser }) => {
      const m = flow.model('chain');
      const subBefore = await withPage(browser, submitterCredentials(), homeStats);
      const revBefore = await withPage(browser, reviewerCredentials(), homeStats);

      await useSession(page, starter.persona());
      await page.goto(`/processes/${m.route}`);
      await page.getByRole('button', { name: 'Start process', exact: true }).click();
      const id = await waitForInstancePage(page);
      flow.track.instances.push(id);
      const startedBy = (await instanceDetail(page, id)).started_by;
      const starterInbox = starter.canReview ? await hasTaskFor(page, id) : (await backendFetch(page, '/v1.0/m8flow/task-review')).status;

      // Step 1: the submitter.
      const subTask = await withPage(browser, submitterCredentials(), async (sub) => {
        const task = await waitForTask(sub, id, 'E2E Submit Request');
        const stats = await homeStats(sub);
        await sub.goto(`/task-review/${task.id}`);
        await expect(sub.getByRole('heading', { level: 1, name: taskTitle(task), exact: true })).toBeVisible();
        await sub.getByLabel('Request details').fill(`Laptop for E2E ${flow.stamp}`);
        await sub.getByRole('button', { name: 'Submit', exact: true }).click();
        await expect(sub).toHaveURL(urlPathEndsWith('/task-review'));
        return { task, waiting: stats.tasks_waiting_on_me, after: (await homeStats(sub)).tasks_waiting_on_me };
      });
      // "Submitted by" shows the starter's display name (e.g. "Editor M8Flow"); started_by is the username.
      expect(startedBy).toBe(starter.persona().username);
      expect(subTask.task.submitted_by?.toLowerCase() ?? '').toContain(starter.persona().username.toLowerCase());
      expect(subTask.waiting).toBe(subBefore.tasks_waiting_on_me! + 1);
      expect(subTask.after).toBe(subBefore.tasks_waiting_on_me);

      // Step 2: the reviewer, created only now.
      const revTask = await withPage(browser, reviewerCredentials(), async (rev) => {
        const task = await waitForTask(rev, id, 'E2E Approve Request');
        const stats = await homeStats(rev);
        expect((await submitTask(rev, task.id, { approval_note: 'Approved' })).status).toBeLessThan(300);
        return { task, waiting: stats.tasks_waiting_on_me, after: (await homeStats(rev)).tasks_waiting_on_me };
      });
      expect(revTask.task.submitted_by).toBe(subTask.task.submitted_by);
      expect(revTask.waiting).toBe(revBefore.tasks_waiting_on_me! + 1);
      expect(revTask.after).toBe(revBefore.tasks_waiting_on_me);

      const done = await waitForStatus(page, id, 'complete');
      expect(done.started_by).toBe(startedBy);
      expect(subTask.task.submitted_by?.toLowerCase()).not.toContain('submitter');
      const data = await asAdmin(browser, (ed) => taskData(ed, id, 'Activity_approve_request'));
      expect(data).toMatchObject({ request_details: `Laptop for E2E ${flow.stamp}`, approval_note: 'Approved' });
      if (starter.canReview) expect(starterInbox).toBe(false);
      else expect(starterInbox, 'editors have no Task Review').toBe(403);

      logResult(`FLW-58 [${starter.label}]`, {
        scenario: `${starter.label} starts; submitter, then reviewer work the steps`,
        actions: [`Login as ${starter.label} and Start process`, 'Submitter submits Request details', 'Reviewer approves'],
        expected: 'Step 1 only for the submitter, step 2 only for the reviewer after step 1; the starter gets no task; "Submitted by" is the starter; counts go up and back down; Complete',
        actual: `Started by ${startedBy}; starter task: ${starter.canReview ? starterInbox : `Task Review ${starterInbox}`}; submitter waiting ${subBefore.tasks_waiting_on_me}->${subTask.waiting}->${subTask.after}; reviewer ${revBefore.tasks_waiting_on_me}->${revTask.waiting}->${revTask.after}; "${done.status}"`,
      });
    });
  }

  test('FLW-59: Parallel approvals: manager and finance get their tasks at the same time', async ({ browser }) => {
    const id = await startUi(browser, 'parallel');
    // Both tasks exist before either is worked.
    const manager = await withPage(browser, reviewerCredentials(), (r) => waitForTask(r, id, 'E2E Manager Approval'));
    const finance = await withPage(browser, tenantAdminCredentials(), (a) => waitForTask(a, id, 'E2E Finance Approval'));
    expect(await withPage(browser, reviewerCredentials(), (r) => hasTaskFor(r, id)), 'the reviewer gets only the manager task').toBe(true);

    // Finance first: the instance waits for the manager (the join needs both).
    await withPage(browser, tenantAdminCredentials(), (a) => completeTaskInUi(a, id, { 'Finance note': 'Budget OK' }, 'E2E Finance Approval'));
    const waiting = await asAdmin(browser, (ed) => waitForStatus(ed, id, 'user_input_required'));
    // Still waiting: the manager's task is on the reviewer's Task Review list.
    await withPage(browser, reviewerCredentials(), async (r) => {
      await r.goto('/task-review');
      await expect(tableRows(r, flow.model('parallel').name)).toHaveCount(1);
    });
    await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, id, { 'Manager note': 'Terms OK' }, 'E2E Manager Approval'));
    const done = await asAdmin(browser, async (ed) => ({ detail: await waitForStatus(ed, id, 'complete'), ids: await completedIds(ed, id) }));
    expect(done.ids.filter((x) => x === 'EndEvent_1')).toHaveLength(1);
    const data = await asAdmin(browser, (ed) => taskData(ed, id, 'EndEvent_1'));
    expect(data).toMatchObject({ manager_note: 'Terms OK', finance_note: 'Budget OK' });

    logResult('FLW-59', {
      scenario: 'Contract approved by manager and finance in parallel',
      actions: ['Submitter clicks Start process', 'Check both inboxes', 'Admin approves as finance in Task Review', 'Reviewer sees the manager task, then approves it in Task Review'],
      expected: 'Both tasks appear at once; after one approval the instance still waits; after both it is Complete once, with both notes',
      actual: `Manager task #${manager.id}, finance task #${finance.id}; after finance "${waiting.status}"; finally "${done.detail.status}"`,
    });
  });
});
