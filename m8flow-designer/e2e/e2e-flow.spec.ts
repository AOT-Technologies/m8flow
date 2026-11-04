import { readFileSync } from 'node:fs';

import { expect, test, type Browser } from '@playwright/test';

import { editorCredentials, reviewerCredentials, submitterCredentials, useSession } from './helpers/auth';
import {
  LANE,
  completeTask,
  gotoHome,
  homeStats,
  instanceDetail,
  myTasks,
  shown,
  startInstance,
  statValue,
  tableRows,
  taskTitle,
  useFlowCatalog,
  utcDay,
  waitForStatus,
  waitForTask,
  withPage,
  type FlowModel,
} from './helpers/processFlow';
import { logResult } from './helpers/processesPage';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Start a process and complete its task (end-to-end flow).
 *
 * FLW-01  a submitter starts a published process from the process model page
 * FLW-02  the task appears in the approver's (reviewer's) Task Review inbox
 * FLW-03  the approver completes the task (required field checked first)
 * FLW-04  the instance shows Complete in Process Instances
 * FLW-05  Home counts update after completion
 *
 * Each test is independent: it starts its own instance (through the API when
 * the start is not what it checks) and uses the UI for the step under test.
 * Tests that check a list by model name use their own copy of the model.
 * The approval task is in the "Approvers" lane, so the seeded reviewer gets it.
 */

const APPROVAL_FORM = 'e2e-flow-review-schema.json';
const approvalForm = readFileSync(new URL(`./fixtures/e2e-flow/${APPROVAL_FORM}`, import.meta.url), 'utf-8');

const flow = useFlowCatalog(test, 'flow', {
  approval: {
    name: 'E2E Flow Approval',
    bpmn: { steps: [{ id: 'Activity_approve_request', name: 'E2E Approve Request', lane: LANE.approvers, form: APPROVAL_FORM }] },
    files: { [APPROVAL_FORM]: approvalForm },
  },
});

async function start(browser: Browser, model: FlowModel = flow.model('approval')): Promise<number> {
  return withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, model.route));
}

test.describe('Start a process and complete its task', { tag: ['@smoke', '@workflow'] }, () => {
  test('FLW-01: A submitter starts a published process from the process model page', { tag: '@counts' }, async ({ page }) => {
    const m = flow.model('approval');
    await useSession(page, submitterCredentials());
    const before = await homeStats(page);

    await page.goto(`/processes/${m.route}`);
    await expect(page.getByRole('heading', { name: m.name, exact: true })).toBeVisible();
    await expect(page.getByTestId('process-model-status')).toContainText('Published');
    await page.getByRole('button', { name: 'Start process' }).click();

    // Starting opens the new instance's page.
    await expect(page).toHaveURL((url) => /^\/process-instances\/\d+$/.test(url.pathname));
    const id = Number(new URL(page.url()).pathname.split('/').pop());
    flow.track.instances.push(id);

    // The instance waits at the approval task.
    const started = await waitForStatus(page, id, 'user_input_required');
    expect(started.process_model_display_name).toBe(m.name);
    // The task is in the Approvers lane, so it is not in the submitter's own inbox.
    expect((await myTasks(page)).some((t) => t.process_instance_id === id)).toBe(false);
    // One more active instance while it waits.
    const running = await homeStats(page);
    if (before.active_process_instances != null) {
      expect(running.active_process_instances).toBe(before.active_process_instances + 1);
    }

    logResult('FLW-01', {
      scenario: 'Submitter starts a published process',
      actions: ['Login to M8Flow as Submitter', `Open "${m.name}"`, 'Click "Start process"'],
      expected: 'The instance page opens; the instance waits at the approval task; the task is not given to the submitter',
      actual: `Instance #${id} "${started.status}"; not in the submitter's Task Review; active instances ${shown(before.active_process_instances)} -> ${shown(running.active_process_instances)}`,
    });
  });

  test("FLW-02: The task appears in the approver's Task Review inbox", { tag: '@counts' }, async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'approval');
    const id = await start(browser, m);
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    expect(task.process_model_display_name).toBe(m.name);

    await page.goto('/task-review');
    await expect(page.getByRole('heading', { name: 'Task Review', exact: true })).toBeVisible();
    const row = tableRows(page, m.name);
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(taskTitle(task));
    if (task.submitted_by) await expect(row).toContainText(task.submitted_by);

    // Home shows the same "Tasks waiting on me" count as the server.
    const stats = await homeStats(page);
    expect(stats.show_tasks_waiting_on_me).toBe(true);
    expect(stats.tasks_waiting_on_me ?? 0).toBeGreaterThanOrEqual(1);
    await gotoHome(page);
    await expect(statValue(page, 'Tasks waiting on me')).toHaveText(String(stats.tasks_waiting_on_me));

    logResult('FLW-02', {
      scenario: "Task reaches the approver's inbox",
      actions: ['Submitter starts (API)', 'Login to M8Flow as Reviewer', 'Open Task Review', 'Open Home'],
      expected: 'The inbox lists the task once with its process and submitter; Home shows the waiting count',
      actual: `"${taskTitle(task)}" (#${task.id}) listed for "${m.name}" (submitted by ${task.submitted_by ?? '—'}); Tasks waiting on me = ${stats.tasks_waiting_on_me}`,
    });
  });

  test('FLW-03: The approver completes the task', { tag: '@counts' }, async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'approval');
    const id = await start(browser, m);
    const approvalNote = `Approved by E2E ${flow.stamp}`;
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    const before = await homeStats(page);

    await page.goto('/task-review');
    await tableRows(page, m.name).click();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));
    await expect(page.getByRole('heading', { level: 1, name: taskTitle(task), exact: true })).toBeVisible();
    await expect(page.getByText('Awaiting your review', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Task Form', exact: true })).toBeVisible();

    // The required field blocks an empty submit.
    const submit = page.getByRole('button', { name: 'Submit', exact: true });
    await submit.click();
    const required = 'Approval note is required.';
    await expect(page.getByRole('alert').filter({ hasText: required })).toBeVisible();
    await expect(page).toHaveURL(urlPathEndsWith(`/task-review/${task.id}`));

    await page.getByLabel('Approval note').fill(approvalNote);
    await submit.click();

    // Back in the inbox, without the task.
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0);
    await expect(tableRows(page, m.name)).toHaveCount(0);
    await expect.poll(async () => (await myTasks(page)).some((t) => t.id === task.id), { timeout: 30_000 }).toBe(false);

    // One task fewer on Home.
    const after = await homeStats(page);
    expect(after.tasks_waiting_on_me).toBe(before.tasks_waiting_on_me! - 1);
    await gotoHome(page);
    await expect(statValue(page, 'Tasks waiting on me')).toHaveText(String(after.tasks_waiting_on_me));
    const done = await withPage(browser, editorCredentials(), (ed) => waitForStatus(ed, id, 'complete'));

    logResult('FLW-03', {
      scenario: 'Approver completes the task',
      actions: ['Open the task from Task Review', 'Submit with an empty Approval note', `Enter "${approvalNote}" and Submit`],
      expected: 'Empty submit is refused; a filled-in submit returns to the inbox without the task; waiting count goes down by 1',
      actual: `Task #${task.id} completed; instance #${id} "${done.status}"; Tasks waiting on me ${before.tasks_waiting_on_me} -> ${after.tasks_waiting_on_me}`,
      messages: [required],
    });
  });

  test('FLW-04: The instance shows Complete in Process Instances', async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'approval');
    const id = await start(browser, m);
    await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, id, { approval_note: 'Approved' }));
    await useSession(page, submitterCredentials());
    const done = await waitForStatus(page, id, 'complete');

    await page.goto('/process-instances');
    await page.getByRole('searchbox', { name: 'Search process instances' }).fill(m.name);
    const row = tableRows(page, m.name);
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(String(id));
    await expect(row).toContainText('Complete');
    await expect(row).toContainText(done.started_by);

    logResult('FLW-04', {
      scenario: 'Instance is complete after the task',
      actions: ['Submitter starts and reviewer approves (API)', 'Login to M8Flow as Submitter', 'Open Process Instances', `Search "${m.name}"`],
      expected: 'The instance is listed with status Complete',
      actual: `Instance #${id} shows "Complete" (started by ${done.started_by}); server status "${done.status}"`,
    });
  });

  test('FLW-05: Home counts update after completion', { tag: '@counts' }, async ({ page, browser }) => {
    await useSession(page, submitterCredentials());
    const day = utcDay();
    const before = await homeStats(page);
    const id = await start(browser);
    await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, id, { approval_note: 'Approved' }));
    await waitForStatus(page, id, 'complete');

    const after = await homeStats(page);
    // Started and completed: no longer active, and counted as completed today.
    // A count the role may not see stays "—".
    expect(after.active_process_instances).toBe(before.active_process_instances);
    if (day === utcDay()) {
      expect(after.completed_today).toBe(before.completed_today == null ? null : before.completed_today + 1);
    } else {
      test.info().annotations.push({ type: 'midnight', description: 'The run crossed midnight (UTC); the "Completed today" +1 check was skipped.' });
    }
    await gotoHome(page);
    await expect(statValue(page, 'Active process instances')).toHaveText(shown(after.active_process_instances));
    await expect(statValue(page, 'Completed today')).toHaveText(shown(after.completed_today));
    expect((await instanceDetail(page, id)).status).toBe('complete');

    logResult('FLW-05', {
      scenario: "Submitter's Home after an instance completes",
      actions: ['Read Home counts', 'Start and approve an instance (API)', 'Open Home'],
      expected: 'Active process instances back to the starting value; Completed today up by 1; cards match the server',
      actual: `Instance #${id}; active ${shown(before.active_process_instances)} -> ${shown(after.active_process_instances)}; completed today ${shown(before.completed_today)} -> ${shown(after.completed_today)}`,
    });
  });
});
