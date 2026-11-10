import { expect, test, type Page } from '@playwright/test';

import { editorCredentials, submitterCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { useFlowCatalog, waitForTask, type FlowModel } from './helpers/processFlow';
import { logResult, modelRow } from './helpers/processesPage';

/**
 * Running a process whose HTTP service task cannot reach its API.
 *
 * The call goes backend -> m8flow-node-wire-proxy -> http_generic for real. Its
 * URL is the cloud metadata address, which the proxy's SSRF guard refuses, so
 * the failure is deterministic and needs no internet. When process start fails,
 * no instance is created. When an automatic step fails after a user task is
 * submitted, that submission is committed and the process is marked Error.
 * (Successful and TLS calls are covered by the proxy's own
 * integration tests: m8flow-node-wire-proxy/tests/test_outbound_http_integration.py.)
 *
 * The models are made from the seeded templates flow-call-first (start -> HTTP
 * call) and flow-approve-then-call (start -> "Approve profile sync" -> HTTP
 * call) in a group of this file and deleted afterwards. A submitter runs them.
 */
// http_generic reports an SSRF refusal as an input validation failure.
const CONNECTOR_REFUSAL = 'Input validation failed';
const APPROVAL_TASK_NAME = 'Approve profile sync';

const flow = useFlowCatalog(test, 'runs', {
  callFirst: { name: 'E2E Call First', template: 'flow-call-first' },
  approveThenCall: { name: 'E2E Approve Then Call', template: 'flow-approve-then-call' },
});

type RecentInstance = { id: number };

async function recentInstanceIds(page: Page, model: FlowModel): Promise<number[]> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-models/${model.route}`);
  expect(result.status, `GET process model ${model.route}`).toBe(200);
  return ((result.body as { recent_instances?: RecentInstance[] }).recent_instances ?? []).map((row) => row.id);
}

async function instanceStatus(page: Page, id: number): Promise<string> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`);
  expect(result.status, `GET process instance ${id}`).toBe(200);
  return (result.body as { status: string }).status;
}

test.describe('Running a process: HTTP service task that cannot reach its API', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, submitterCredentials());
  });

  test('SVC-01: Starting a process whose first step is a refused HTTP call shows the error and creates no instance', async ({
    page,
  }) => {
    const model = flow.model('callFirst');
    const editor = await page.context().browser()!.newPage();
    await useSession(editor, editorCredentials());
    const before = await recentInstanceIds(editor, model);

    await page.goto(`/processes?group=${encodeURIComponent(flow.groupId)}`);
    await modelRow(page, model.name).getByRole('button', { name: 'Start', exact: true }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('http/GetRequestV2');
    // Text from the connector itself: the call reached the proxy and was refused there.
    await expect(alert).toContainText(CONNECTOR_REFUSAL);
    await expect(page).toHaveURL(/\/processes\?/);
    expect(await recentInstanceIds(editor, model)).toEqual(before);
    const message = (await alert.innerText()).trim();
    await editor.close();

    logResult('SVC-01', {
      scenario: 'Start a process whose first step calls a blocked address',
      actions: [`Start "${model.name}"`],
      expected: 'An error names the failed HTTP call; the user stays on the list; no instance is created',
      actual: 'Error shown; still on Processes; instance count unchanged',
      messages: [message],
    });
  });

  test('SVC-02: Approving a task whose next step is a refused HTTP call shows the error and saves the submission', async ({
    page,
  }) => {
    const model = flow.model('approveThenCall');
    await page.goto(`/processes?group=${encodeURIComponent(flow.groupId)}`);
    await modelRow(page, model.name).getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    flow.track.instances.push(instanceId);

    // The Home link of this instance's task (by task id, not by name).
    const task = await waitForTask(page, instanceId, APPROVAL_TASK_NAME);
    const linkSelector = `a[href$="/task-review/${task.id}"]`;
    await page.goto('/');
    await page.locator(linkSelector).first().click();
    await expect(page).toHaveURL(/\/task-review\/\d+/);
    const taskUrl = page.url();
    await page.getByRole('button', { name: /^(Submit|Continue)$/ }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('The task was submitted, but the next automatic step failed');
    await expect(alert).toContainText('http/GetRequestV2');
    // Text from the connector itself: the call reached the proxy and was refused there.
    await expect(alert).toContainText(CONNECTOR_REFUSAL);
    await expect(page).toHaveURL(taskUrl);
    expect(await instanceStatus(page, instanceId)).toBe('error');
    const message = (await alert.innerText()).trim();

    // The submission is saved; the failed automatic step leaves the instance
    // in Error and removes the completed task from Home.
    await page.goto('/');
    await expect(page.locator(linkSelector)).toHaveCount(0);

    logResult('SVC-02', {
      scenario: 'Approve a task whose next step calls a blocked address',
      actions: ['Start from Processes', `Open "${APPROVAL_TASK_NAME}" on Home`, 'Submit'],
      expected: 'An error explains the task was submitted, names the failed HTTP call, and shows the process instance in Error',
      actual: `Instance ${instanceId} is error; the submitted task is no longer on Home`,
      messages: [message],
    });
  });
});
