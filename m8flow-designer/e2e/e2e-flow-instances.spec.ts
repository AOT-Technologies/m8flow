import { expect, test, type Browser, type Page } from '@playwright/test';

import {
  editorCredentials,
  reviewerCredentials,
  submitterCredentials,
  tenantAdminCredentials,
  useSession,
  viewerCredentials,
} from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import {
  LANE,
  completeTask,
  completeTaskInUi,
  hasTaskFor,
  homeMyTasks,
  homeStats,
  instanceDetail,
  shown,
  startInUi,
  startInstance,
  statValue,
  tableRows,
  taskData,
  taskTitle,
  useFlowCatalog,
  utcDay,
  waitForStatus,
  waitForTask,
  withPage,
  gotoHome,
  type FlowModel,
  type HomeStats,
} from './helpers/processFlow';
import { logResult } from './helpers/processesPage';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Process flow: process instances and Home dashboard counts.
 *
 * FLW-42  a new instance is listed right away as User Input Required
 * FLW-43  two instances of the same model run independently (with Home counts)
 * FLW-44  instance detail shows the right process and task data after refresh
 * FLW-45  double-clicking "Start process" starts one instance
 * FLW-46  a server error on start is shown and creates nothing
 * FLW-47  approvers' "Tasks waiting on me" through a two-step flow
 * FLW-48  Home counts do not change on refresh or revisit
 * FLW-49  "Errors needing review" and "Avg. completion time" match the server
 * FLW-57  the assigned task is shown under "My tasks" on Home
 */

// Seeded templates: flow-single-approval ("E2E Approve Request", Approvers lane, field approval_note) and
// flow-two-step-approval ("E2E First Approval" by Approvers, then "E2E Second Approval" by Administrators).
const approve = { id: 'Activity_approve_request', name: 'E2E Approve Request' };

const flow = useFlowCatalog(test, 'flowi', {
  approval: { name: 'E2E Instances', template: 'flow-single-approval' },
  pair: { name: 'E2E Pair', template: 'flow-single-approval' },
  start: { name: 'E2E Start Twice', template: 'flow-single-approval' },
  mytasks: { name: 'E2E My Tasks', template: 'flow-single-approval' },
  twostep: { name: 'E2E Two Step Counts', template: 'flow-two-step-approval' },
});

async function start(browser: Browser, key: string | FlowModel): Promise<number> {
  const route = typeof key === 'string' ? flow.model(key).route : key.route;
  return withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, route));
}

/** The submitter clicks "Start process" on the model page. */
async function startUi(browser: Browser, model: FlowModel): Promise<number> {
  return withPage(browser, submitterCredentials(), (sub) => startInUi(sub, flow, model.route));
}

async function instancesOf(page: Page, modelName: string): Promise<{ id: number; status: string }[]> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-instances?search=${encodeURIComponent(modelName)}&per_page=100`);
  expect(result.status, 'GET /process-instances').toBe(200);
  return ((result.body as { results: { id: number; status: string; process_model_display_name: string }[] }).results ?? []).filter(
    (r) => r.process_model_display_name === modelName,
  );
}

async function expectCards(page: Page, stats: HomeStats, labels: [string, keyof HomeStats][]): Promise<void> {
  await gotoHome(page);
  for (const [label, key] of labels) {
    await expect(statValue(page, label)).toHaveText(shown(stats[key] as number | null));
  }
}

test.describe('Process flow: process instances', { tag: ['@workflow'] }, () => {
  test('FLW-42: A new instance is listed right away as User Input Required', async ({ page }) => {
    const m = flow.model('approval');
    await useSession(page, submitterCredentials());
    await page.goto(`/processes/${m.route}`);
    await page.getByRole('button', { name: 'Start process', exact: true }).click();
    await expect(page).toHaveURL((url) => /^\/process-instances\/\d+$/.test(url.pathname));
    const id = Number(new URL(page.url()).pathname.split('/').pop());
    flow.track.instances.push(id);
    await expect(page.getByText('User Input Required', { exact: true }).first()).toBeVisible();

    await page.goto('/process-instances');
    await page.getByRole('searchbox', { name: 'Search process instances' }).fill(m.name);
    const row = tableRows(page, m.name).filter({ hasText: String(id) });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('User Input Required');
    const detail = await instanceDetail(page, id);
    await expect(row).toContainText(detail.started_by);
    expect(detail.tasks.some((t) => t.bpmn_identifier === approve.id && !/^completed$/i.test(t.state))).toBe(true);
    await row.click();
    await expect(page).toHaveURL(urlPathEndsWith(`/process-instances/${id}`));

    logResult('FLW-42', {
      scenario: 'Instance right after the start',
      actions: ['Submitter clicks "Start process"', 'Open Process Instances and search', 'Open the row'],
      expected: 'Listed with its id, "User Input Required" and the starter; the approval task is pending',
      actual: `Instance #${id} "User Input Required", started by ${detail.started_by}; task pending`,
    });
  });

  test('FLW-43: Two instances of the same model run independently', { tag: '@counts' }, async ({ browser }) => {
    const m = await flow.fresh(browser, 'pair');
    const day = utcDay();
    const subBefore = await withPage(browser, submitterCredentials(), homeStats);
    const revBefore = await withPage(browser, reviewerCredentials(), homeStats);
    const first = await startUi(browser, m);
    const second = await startUi(browser, m);

    await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, first, { 'Approval note': 'First only' }));
    const after = await withPage(browser, submitterCredentials(), async (sub) => {
      await waitForStatus(sub, first, 'complete');
      const rows = await instancesOf(sub, m.name);
      return { rows, stats: await homeStats(sub), secondStatus: (await instanceDetail(sub, second)).status };
    });
    expect(after.secondStatus).toBe('user_input_required');
    expect(after.rows.map((r) => r.id).sort()).toEqual([first, second].sort());
    // The same on screen: Process Instances lists both, each with its own status.
    await withPage(browser, submitterCredentials(), async (sub) => {
      await sub.goto('/process-instances');
      await sub.getByRole('searchbox', { name: 'Search process instances' }).fill(m.name);
      await expect(tableRows(sub, m.name)).toHaveCount(2);
      await expect(tableRows(sub, m.name).filter({ hasText: String(first) })).toContainText('Complete');
      await expect(tableRows(sub, m.name).filter({ hasText: String(second) })).toContainText('User Input Required');
    });
    const rev = await withPage(browser, reviewerCredentials(), async (r) => ({
      first: await hasTaskFor(r, first),
      second: await hasTaskFor(r, second),
      stats: await homeStats(r),
    }));
    expect(rev).toMatchObject({ first: false, second: true });
    expect(rev.stats.tasks_waiting_on_me).toBe(revBefore.tasks_waiting_on_me! + 1);
    if (subBefore.active_process_instances != null) {
      expect(after.stats.active_process_instances).toBe(subBefore.active_process_instances + 1);
    }
    if (subBefore.completed_today != null && day === utcDay()) {
      expect(after.stats.completed_today).toBe(subBefore.completed_today + 1);
    }
    await withPage(browser, submitterCredentials(), (sub) =>
      expectCards(sub, after.stats, [
        ['Active process instances', 'active_process_instances'],
        ['Completed today', 'completed_today'],
      ]),
    );

    logResult('FLW-43', {
      scenario: 'Two instances, only the first approved',
      actions: ['Submitter clicks Start process twice', 'Reviewer approves the first in Task Review', 'Check Process Instances, the inbox and Home'],
      expected: 'First Complete, second still waiting; reviewer has only the second; Active +1, Completed today +1, Tasks waiting +1',
      actual: `#${first} complete, #${second} "${after.secondStatus}"; active ${shown(subBefore.active_process_instances)}->${shown(after.stats.active_process_instances)}, completed ${shown(subBefore.completed_today)}->${shown(after.stats.completed_today)}, waiting ${revBefore.tasks_waiting_on_me}->${rev.stats.tasks_waiting_on_me}`,
    });
  });

  test('FLW-44: Instance detail shows the right process and task data after refresh', async ({ page, browser }) => {
    const m = flow.model('approval');
    const id = await start(browser, 'approval');
    const note = `Detail check ${flow.stamp}`;
    await withPage(browser, reviewerCredentials(), (r) => completeTask(r, id, { approval_note: note }));

    // The submitter started it; a tenant admin can open any instance (M8F-627).
    await useSession(page, tenantAdminCredentials());
    await waitForStatus(page, id, 'complete');
    for (const pass of ['first load', 'after refresh']) {
      if (pass === 'after refresh') await page.reload();
      else await page.goto(`/process-instances/${id}`);
      await expect(page.getByText(m.name).first()).toBeVisible();
      await expect(page.getByText('Complete', { exact: true }).first()).toBeVisible();
      await page.getByRole('tab', { name: 'Tasks', exact: true }).click();
      // "Completed by me" is selected first; the editor did not complete the task.
      await page.getByRole('tab', { name: 'All completed', exact: true }).click();
      await expect(page.getByText(approve.name).first()).toBeVisible();
    }
    const viewerData = await withPage(browser, viewerCredentials(), (v) => taskData(v, id, approve.id));
    expect(viewerData.approval_note).toBe(note);

    logResult('FLW-44', {
      scenario: 'Completed instance detail',
      actions: ['Editor opens the instance', 'Open the Tasks tab', 'Refresh', 'Viewer reads the task data'],
      expected: 'Model name, Complete and the completed task are shown before and after refresh; the task data is readable',
      actual: `Shown both times; viewer read approval_note "${viewerData.approval_note}"`,
    });
  });

  test('FLW-45: Double-clicking "Start process" starts one instance', async ({ page }) => {
    const m = flow.model('start');
    await useSession(page, submitterCredentials());
    const before = (await instancesOf(page, m.name)).length;
    const starts: number[] = [];
    page.on('response', (r) => {
      if (r.request().method() === 'POST' && r.url().endsWith('/start')) starts.push(r.status());
    });
    await page.goto(`/processes/${m.route}`);
    await page.getByRole('button', { name: 'Start process', exact: true }).dblclick();
    await expect(page).toHaveURL((url) => /^\/process-instances\/\d+$/.test(url.pathname));
    flow.track.instances.push(Number(new URL(page.url()).pathname.split('/').pop()));
    await page.waitForLoadState('networkidle');
    const after = await instancesOf(page, m.name);
    after.forEach((r) => flow.track.instances.push(r.id));
    expect(starts.filter((s) => s < 300), `start responses: ${starts.join(', ')}`).toHaveLength(1);
    expect(after.length).toBe(before + 1);

    logResult('FLW-45', {
      scenario: 'Double-click Start process',
      actions: ['Count instances', 'Double-click "Start process"'],
      expected: 'Exactly one new instance (the button is disabled while starting)',
      actual: `Start requests [${starts.join(', ')}]; instances ${before} -> ${after.length}`,
    });
  });

  test('FLW-46: A server error on start is shown and creates nothing', async ({ page }) => {
    const m = flow.model('start');
    await useSession(page, submitterCredentials());
    const before = (await instancesOf(page, m.name)).length;
    await page.route('**/v1.0/m8flow/process-models/*/start', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ message: 'E2E simulated start failure' }) }),
    );
    await page.goto(`/processes/${m.route}`);
    await page.getByRole('button', { name: 'Start process', exact: true }).click();
    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    const message = (await alert.innerText()).trim();
    await expect(page).toHaveURL(urlPathEndsWith(`/processes/${m.route}`));
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    expect((await instancesOf(page, m.name)).length).toBe(before);

    logResult('FLW-46', {
      scenario: 'Start returns a server error (mocked 500)',
      actions: ['Click "Start process"'],
      expected: 'An error is shown, the page stays on the model and no instance is created',
      actual: `Error shown; instances unchanged (${before})`,
      messages: [message],
    });
  });
});

test.describe('Process flow: Home dashboard counts', { tag: ['@counts'] }, () => {
  test("FLW-47: Approvers' \"Tasks waiting on me\" through a two-step flow", async ({ browser }) => {
    const read = async () => ({
      reviewer: (await withPage(browser, reviewerCredentials(), homeStats)).tasks_waiting_on_me!,
      admin: (await withPage(browser, tenantAdminCredentials(), homeStats)).tasks_waiting_on_me!,
    });
    // Each reading is also checked on the Home card of both approvers.
    const cards = async (value: { reviewer: number; admin: number }) => {
      for (const [persona, n] of [
        [reviewerCredentials(), value.reviewer],
        [tenantAdminCredentials(), value.admin],
      ] as const) {
        await withPage(browser, persona, async (p) => {
          await gotoHome(p);
          await expect(statValue(p, 'Tasks waiting on me')).toHaveText(String(n));
        });
      }
    };
    const before = await read();
    await cards(before);
    const id = await startUi(browser, flow.model('twostep'));
    await withPage(browser, reviewerCredentials(), (r) => waitForTask(r, id, 'E2E First Approval'));
    const started = await read();
    await cards(started);
    await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, id, { 'Reviewer note': 'E2E ok' }, 'E2E First Approval', 'Approve'));
    await withPage(browser, tenantAdminCredentials(), (a) => waitForTask(a, id, 'E2E Second Approval'));
    const afterStep1 = await read();
    await cards(afterStep1);
    await withPage(browser, tenantAdminCredentials(), (a) => completeTaskInUi(a, id, { 'Admin note': 'E2E ok' }, 'E2E Second Approval'));
    await withPage(browser, editorCredentials(), (ed) => waitForStatus(ed, id, 'complete'));
    const done = await read();

    expect(started).toEqual({ reviewer: before.reviewer + 1, admin: before.admin });
    expect(afterStep1).toEqual({ reviewer: before.reviewer, admin: before.admin + 1 });
    expect(done).toEqual(before);
    await cards(done);

    logResult('FLW-47', {
      scenario: '"Tasks waiting on me" for both approvers',
      actions: ['Read the Home cards', 'Submitter clicks Start process', 'Reviewer approves step 1 in Task Review', 'Admin submits step 2 in Task Review', 'Home cards after each step'],
      expected: 'Reviewer +1 then back; admin +1 only after step 1, then back; cards match the server; never negative',
      actual: `reviewer ${before.reviewer}->${started.reviewer}->${afterStep1.reviewer}->${done.reviewer}; admin ${before.admin}->${started.admin}->${afterStep1.admin}->${done.admin}`,
    });
  });

  test('FLW-48: Home counts do not change on refresh or revisit', async ({ page }) => {
    await useSession(page, submitterCredentials());
    const stats = await homeStats(page);
    const labels: [string, keyof HomeStats][] = [
      ['Active process instances', 'active_process_instances'],
      ['Completed today', 'completed_today'],
    ];
    if (stats.show_tasks_waiting_on_me) labels.push(['Tasks waiting on me', 'tasks_waiting_on_me']);
    await expectCards(page, stats, labels);
    await page.reload();
    for (const [label, key] of labels) await expect(statValue(page, label)).toHaveText(shown(stats[key] as number | null));
    await page.goto('/process-instances');
    await gotoHome(page);
    for (const [label, key] of labels) await expect(statValue(page, label)).toHaveText(shown(stats[key] as number | null));
    expect(await homeStats(page)).toEqual(stats);

    logResult('FLW-48', {
      scenario: 'Home without any workflow change',
      actions: ['Open Home', 'Refresh', 'Go to Process Instances and back'],
      expected: 'The same counts each time, matching the server',
      actual: labels.map(([l, k]) => `${l} ${shown(stats[k] as number | null)}`).join('; '),
    });
  });

  test('FLW-49: "Errors needing review" and "Avg. completion time" match the server', async ({ browser }) => {
    const id = await startUi(browser, flow.model('approval'));
    await withPage(browser, reviewerCredentials(), (r) => completeTaskInUi(r, id, { 'Approval note': 'For the average' }));
    const results: string[] = [];
    for (const [label, persona] of [
      ['editor', editorCredentials()],
      ['admin', tenantAdminCredentials()],
    ] as const) {
      await withPage(browser, persona, async (p) => {
        await waitForStatus(p, id, 'complete');
        const stats = await homeStats(p);
        await gotoHome(p);
        await expect(statValue(p, 'Errors needing review')).toHaveText(shown(stats.errors_needing_review));
        await expect(statValue(p, 'Avg. completion time')).toHaveText(
          stats.avg_completion_minutes == null ? '—' : `${stats.avg_completion_minutes}m`,
        );
        if (stats.avg_completion_minutes != null) expect(stats.avg_completion_minutes).toBeGreaterThanOrEqual(0);
        if (stats.errors_needing_review != null) expect(stats.errors_needing_review).toBeGreaterThanOrEqual(0);
        results.push(`${label}: errors ${shown(stats.errors_needing_review)}, avg ${shown(stats.avg_completion_minutes)}`);
      });
    }
    test.info().annotations.push({ type: 'needs-confirmation', description: 'Scope of these counts (user or tenant) and which roles see them.' });

    logResult('FLW-49', {
      scenario: 'The two counters FLW-01..05 do not cover',
      actions: ['Start process and approve it in Task Review', 'Open Home as editor and as admin'],
      expected: 'Cards match the server; values are never negative; the average is shown in minutes',
      actual: results.join('; '),
    });
  });

  test('FLW-57: The assigned task is shown under "My tasks" on Home', async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'mytasks');
    const id = await start(browser, m);
    const submitterSees = await withPage(browser, submitterCredentials(), async (sub) =>
      (await homeMyTasks(sub)).some((t) => t.process_instance_id === id),
    );
    expect(submitterSees, "the submitter's My tasks does not list the approver's task").toBe(false);

    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const mine = (await homeMyTasks(page)).find((t) => t.process_instance_id === id);
    expect(mine, 'the task is in the reviewer\'s My tasks (API)').toBeTruthy();
    await gotoHome(page);
    await expect(page.getByRole('heading', { name: 'My tasks', exact: true })).toBeVisible();
    const link = page.locator(`a[href="/task-review/${task.id}"]`);
    await expect(link).toHaveCount(1);
    await expect(link).toContainText(taskTitle(task));
    await expect(link).toContainText(`${mine!.tenant_name} · waiting on ${mine!.lane_name ?? '—'}`);
    expect(mine!.lane_name).toBe(LANE.approvers);
    await link.click();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
    await gotoHome(page);
    // Home has two "View all" links (My tasks and Recent process instances); use the My tasks one.
    await page.locator('a[href="/task-review"]').filter({ hasText: 'View all' }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    await expect(tableRows(page, m.name)).toHaveCount(1);

    await completeTask(page, id, { approval_note: 'Done from My tasks' });
    await gotoHome(page);
    await expect(page.locator(`a[href="/task-review/${task.id}"]`)).toHaveCount(0);
    const remaining = await homeMyTasks(page);
    if (remaining.length === 0) await expect(page.getByText('No pending tasks.', { exact: true })).toBeVisible();

    logResult('FLW-57', {
      scenario: '"My tasks" on Home for the approver',
      actions: ['Submitter starts', "Check submitter's My tasks", 'Reviewer opens Home', 'Click the task', '"View all"', 'Complete the task'],
      expected: 'Only the reviewer lists the task once with its name and "tenant · waiting on Approvers"; the row and View all open the right pages; it disappears after completion',
      actual: `Task #${task.id} listed as "${taskTitle(task)}" (${mine!.tenant_name} · waiting on ${mine!.lane_name}); gone after completion`,
    });
  });
});
