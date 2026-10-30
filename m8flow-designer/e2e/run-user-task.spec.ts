import { readFileSync } from 'node:fs';

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
 * Running a process: a submitter starts a published model, finds the user task
 * it created under "My tasks" on Home, fills in the task form and submits it,
 * and the instance finishes as Complete.
 *
 * An editor publishes the model; the run itself is a submitter's job (editors
 * have no "My tasks" on Home). The model is mock data owned by this file:
 * created before, deleted after.
 */
const GROUP = { id: 'e2e-run-user-task', display_name: 'E2E Run User Task' };
const MODEL = { group_id: GROUP.id, id: 'e2e-wfh-request', display_name: 'E2E WFH Request' };
const ROUTE_ID = `${GROUP.id}:${MODEL.id}`;
const BPMN_FILE = 'run-user-task.bpmn';
const FORM_FILE = 'wfh-form-schema.json';

// Unique per run, so this run's task is the one picked on Home even if an
// earlier run left a task behind.
const TASK_NAME = `Submit WFH Request ${Date.now().toString(36)}`;

const DIAGRAM_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
                  id="Definitions_run_user_task" targetNamespace="http://m8flow.org/e2e/run-user-task">
  <bpmn:process id="Process_e2e_run_user_task" name="E2E WFH Request" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:userTask id="Activity_submit_wfh" name="${TASK_NAME}">
      <bpmn:extensionElements>
        <spiffworkflow:properties>
          <spiffworkflow:property name="formJsonSchemaFilename" value="${FORM_FILE}" />
        </spiffworkflow:properties>
      </bpmn:extensionElements>
    </bpmn:userTask>
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Activity_submit_wfh" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Activity_submit_wfh" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>`;

function formSchema(): string {
  return readFileSync(new URL(`./fixtures/mock-model/${FORM_FILE}`, import.meta.url), 'utf-8');
}

type InstanceDetail = { id: number; status: string };

async function instanceStatus(page: Page, id: number): Promise<string> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`);
  expect(result.status, `GET process instance ${id}`).toBe(200);
  return (result.body as InstanceDetail).status;
}

const createdInstances: number[] = [];

test.describe('Running a process: user task', () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      await createMockGroup(page, GROUP);
      await createMockModel(page, MODEL);
      await seedProcessModelFile(page, FORM_FILE, formSchema(), ROUTE_ID);
      await seedProcessModelFile(page, BPMN_FILE, DIAGRAM_XML, ROUTE_ID);
      await setPrimaryFile(page, ROUTE_ID, BPMN_FILE);
      await setModelStatus(page, ROUTE_ID, 'published');
    } finally {
      await page.close();
    }
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      await deleteInstanceIds(page, createdInstances);
      await deleteMockModel(page, ROUTE_ID);
      await deleteMockGroup(page, GROUP.id);
    } finally {
      await page.close();
    }
  });

  test.beforeEach(async ({ page }) => {
    await useSession(page, submitterCredentials());
  });

  test('RUN-01: A submitter starts a process, completes its task from Home, and the instance is Complete', async ({
    page,
  }) => {
    await page.goto(`/processes?group=${encodeURIComponent(GROUP.id)}`);
    await modelRow(page, MODEL.display_name).getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    createdInstances.push(instanceId);
    expect(await instanceStatus(page, instanceId)).toBe('user_input_required');

    await page.goto('/');
    const myTasks = page.locator('section, div').filter({
      has: page.getByRole('heading', { name: 'My tasks', exact: true }),
    });
    await myTasks.getByRole('link', { name: TASK_NAME }).first().click();
    await expect(page).toHaveURL(/\/task-review\/\d+/);
    await expect(page.getByRole('heading', { name: 'Task Form', exact: true })).toBeVisible();

    await page.getByLabel('Start date').fill('2026-11-02');
    await page.getByLabel('End date').fill('2026-11-06');
    await page.getByLabel('Reason').fill('Home renovation week');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(/\/task-review$/);

    await page.goto(`/process-instances/${instanceId}`);
    await expect(page.getByText('Complete', { exact: true }).first()).toBeVisible();
    expect(await instanceStatus(page, instanceId)).toBe('complete');

    // The finished task no longer waits on Home.
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'My tasks', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: TASK_NAME })).toHaveCount(0);

    logResult('RUN-01', {
      scenario: 'Start a published process and complete its user task from Home',
      actions: ['Start from Processes', `Open "${TASK_NAME}" on Home`, 'Fill the form', 'Submit'],
      expected: 'Instance goes from User Input Required to Complete; the task leaves Home',
      actual: `Instance ${instanceId} is complete; task gone from My tasks`,
    });
  });

  test('RUN-02: The task form refuses a submit without its required fields', async ({ page }) => {
    await page.goto(`/processes?group=${encodeURIComponent(GROUP.id)}`);
    await modelRow(page, MODEL.display_name).getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    createdInstances.push(instanceId);

    await page.goto('/');
    await page.getByRole('link', { name: TASK_NAME }).first().click();
    await expect(page).toHaveURL(/\/task-review\/\d+/);
    const taskUrl = page.url();

    await page.getByLabel('End date').fill('2026-11-06');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();

    await expect(page.getByText('Start date is required.', { exact: true })).toBeVisible();
    await expect(page.getByText('Reason is required.', { exact: true })).toBeVisible();
    await expect(page.getByLabel('End date')).toHaveValue('2026-11-06');
    await expect(page).toHaveURL(taskUrl);
    expect(await instanceStatus(page, instanceId)).toBe('user_input_required');

    logResult('RUN-02', {
      scenario: 'Submit the task form with required fields (Start date, Reason) empty',
      actions: ['Start from Processes', 'Open the task', 'Fill only End date', 'Submit'],
      expected: 'The task stays open and the instance still waits for input',
      actual: `Instance ${instanceId} still user_input_required; stayed on the task`,
    });
  });
});
