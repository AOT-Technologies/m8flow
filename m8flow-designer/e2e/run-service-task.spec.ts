import { expect, test, type Page } from '@playwright/test';

import { editorCredentials, submitterCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import {
  createMockGroup,
  createMockModel,
  deleteInstanceIds,
  deleteMockGroup,
  deleteMockModel,
  setModelStatus,
  setPrimaryFile,
} from './helpers/mockCatalog';
import { logResult, modelRow } from './helpers/processesPage';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * Running a process whose HTTP service task cannot reach its API.
 *
 * The call goes backend -> m8flow-node-wire-proxy -> http_generic for real. Its
 * URL is the cloud metadata address, which the proxy's SSRF guard refuses, so
 * the failure is deterministic and needs no internet. A failed service task
 * rolls back the step that reached it: the user is told, and nothing is left
 * half-done. (Successful and TLS calls are covered by the proxy's own
 * integration tests: m8flow-node-wire-proxy/tests/test_outbound_http_integration.py.)
 *
 * An editor publishes the models; a submitter runs them.
 */
const GROUP = { id: 'e2e-run-service-task', display_name: 'E2E Run Service Task' };
const BLOCKED_URL = 'http://169.254.169.254/latest/meta-data/';
const BPMN_FILE = 'run-service-task.bpmn';
// http_generic reports an SSRF refusal as an input validation failure.
const CONNECTOR_REFUSAL = 'Input validation failed';

const SERVICE_TASK = `
    <bpmn:serviceTask id="Activity_fetch_profile" name="Fetch profile">
      <bpmn:extensionElements>
        <spiffworkflow:serviceTaskOperator id="http/GetRequestV2">
          <spiffworkflow:parameters>
            <spiffworkflow:parameter id="url" type="str" value="${BLOCKED_URL}" />
          </spiffworkflow:parameters>
        </spiffworkflow:serviceTaskOperator>
      </bpmn:extensionElements>
    </bpmn:serviceTask>`;

function diagram(processId: string, steps: string, flows: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
                  id="Definitions_${processId}" targetNamespace="http://m8flow.org/e2e/run-service-task">
  <bpmn:process id="${processId}" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />${steps}
    <bpmn:endEvent id="EndEvent_1" />${flows}
  </bpmn:process>
</bpmn:definitions>`;
}

const flow = (id: string, from: string, to: string) =>
  `\n    <bpmn:sequenceFlow id="${id}" sourceRef="${from}" targetRef="${to}" />`;

/** Start -> HTTP call -> end. */
const CALL_FIRST = {
  model: { group_id: GROUP.id, id: 'e2e-call-first', display_name: 'E2E Call First' },
  xml: diagram(
    'Process_e2e_call_first',
    SERVICE_TASK,
    flow('Flow_1', 'StartEvent_1', 'Activity_fetch_profile') + flow('Flow_2', 'Activity_fetch_profile', 'EndEvent_1'),
  ),
};

// Unique per run, so this run's task is the one picked on Home.
const APPROVAL_TASK_NAME = `Approve profile sync ${Date.now().toString(36)}`;

/** Start -> approval (user task) -> HTTP call -> end. */
const APPROVE_THEN_CALL = {
  model: { group_id: GROUP.id, id: 'e2e-approve-then-call', display_name: 'E2E Approve Then Call' },
  xml: diagram(
    'Process_e2e_approve_then_call',
    `\n    <bpmn:userTask id="Activity_approve" name="${APPROVAL_TASK_NAME}" />${SERVICE_TASK}`,
    flow('Flow_1', 'StartEvent_1', 'Activity_approve') +
      flow('Flow_2', 'Activity_approve', 'Activity_fetch_profile') +
      flow('Flow_3', 'Activity_fetch_profile', 'EndEvent_1'),
  ),
};

const MODELS = [CALL_FIRST, APPROVE_THEN_CALL];
const routeId = (model: { group_id: string; id: string }) => `${model.group_id}:${model.id}`;

type RecentInstance = { id: number };

async function recentInstanceIds(page: Page, model: { group_id: string; id: string }): Promise<number[]> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-models/${routeId(model)}`);
  expect(result.status, `GET process model ${routeId(model)}`).toBe(200);
  return ((result.body as { recent_instances?: RecentInstance[] }).recent_instances ?? []).map((row) => row.id);
}

async function instanceStatus(page: Page, id: number): Promise<string> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`);
  expect(result.status, `GET process instance ${id}`).toBe(200);
  return (result.body as { status: string }).status;
}

const createdInstances: number[] = [];

test.describe('Running a process: HTTP service task that cannot reach its API', () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      await createMockGroup(page, GROUP);
      for (const { model, xml } of MODELS) {
        await createMockModel(page, model);
        await seedProcessModelFile(page, BPMN_FILE, xml, routeId(model));
        await setPrimaryFile(page, routeId(model), BPMN_FILE);
        await setModelStatus(page, routeId(model), 'published');
      }
    } finally {
      await page.close();
    }
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      for (const { model } of MODELS) {
        await deleteInstanceIds(page, [...createdInstances, ...(await recentInstanceIds(page, model))]);
        await deleteMockModel(page, routeId(model));
      }
      await deleteMockGroup(page, GROUP.id);
    } finally {
      await page.close();
    }
  });

  test.beforeEach(async ({ page }) => {
    await useSession(page, submitterCredentials());
  });

  test('SVC-01: Starting a process whose first step is a refused HTTP call shows the error and creates no instance', async ({
    page,
  }) => {
    const { model } = CALL_FIRST;
    const editor = await page.context().browser()!.newPage();
    await useSession(editor, editorCredentials());
    const before = await recentInstanceIds(editor, model);

    await page.goto(`/processes?group=${encodeURIComponent(GROUP.id)}`);
    await modelRow(page, model.display_name).getByRole('button', { name: 'Start', exact: true }).click();

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
      actions: [`Start "${model.display_name}"`],
      expected: 'An error names the failed HTTP call; the user stays on the list; no instance is created',
      actual: 'Error shown; still on Processes; instance count unchanged',
      messages: [message],
    });
  });

  test('SVC-02: Approving a task whose next step is a refused HTTP call shows the error and keeps the task open', async ({
    page,
  }) => {
    const { model } = APPROVE_THEN_CALL;
    await page.goto(`/processes?group=${encodeURIComponent(GROUP.id)}`);
    await modelRow(page, model.display_name).getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    createdInstances.push(instanceId);

    await page.goto('/');
    await page.getByRole('link', { name: APPROVAL_TASK_NAME }).first().click();
    await expect(page).toHaveURL(/\/task-review\/\d+/);
    const taskUrl = page.url();
    await page.getByRole('button', { name: /^(Submit|Continue)$/ }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('http/GetRequestV2');
    // Text from the connector itself: the call reached the proxy and was refused there.
    await expect(alert).toContainText(CONNECTOR_REFUSAL);
    await expect(page).toHaveURL(taskUrl);
    expect(await instanceStatus(page, instanceId)).toBe('user_input_required');
    const message = (await alert.innerText()).trim();

    // The approval rolled back with the failed call: it still waits on Home.
    await page.goto('/');
    await expect(page.getByRole('link', { name: APPROVAL_TASK_NAME })).toHaveCount(1);

    logResult('SVC-02', {
      scenario: 'Approve a task whose next step calls a blocked address',
      actions: ['Start from Processes', `Open "${APPROVAL_TASK_NAME}" on Home`, 'Submit'],
      expected: 'An error names the failed HTTP call; the task stays open; the instance still waits for input',
      actual: `Instance ${instanceId} still user_input_required; task still on Home`,
      messages: [message],
    });
  });
});
