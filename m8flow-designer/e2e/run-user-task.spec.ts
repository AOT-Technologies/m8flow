import { expect, test, type Page } from '@playwright/test';

import { submitterCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { useFlowCatalog, waitForInstancePage, waitForTask } from './helpers/processFlow';
import { logResult, modelRow } from './helpers/processesPage';

/**
 * Running a process: a submitter starts a published model, finds the user task
 * it created under "My tasks" on Home, fills in the task form and submits it,
 * and the instance finishes as Complete.
 *
 * The model is made from the seeded template flow-wfh-self-service (one task,
 * "Submit WFH Request", Submitters lane) in a group of this file, and deleted
 * afterwards. The task link is picked by its task id, so tasks of other
 * processes with the same name never get in the way.
 */
const TASK_NAME = 'Submit WFH Request';

const flow = useFlowCatalog(test, 'runu', {
  wfh: { name: 'E2E WFH Request', template: 'flow-wfh-self-service' },
});

type InstanceDetail = { id: number; status: string };

async function instanceStatus(page: Page, id: number): Promise<string> {
  const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`);
  expect(result.status, `GET process instance ${id}`).toBe(200);
  return (result.body as InstanceDetail).status;
}

/** Starts the model from the Processes list (as the logged-in submitter); returns the instance id. */
async function startFromList(page: Page): Promise<number> {
  await page.goto(`/processes?group=${encodeURIComponent(flow.groupId)}`);
  await modelRow(page, flow.model('wfh').name).getByRole('button', { name: 'Start', exact: true }).click();
  const instanceId = await waitForInstancePage(page);
  flow.track.instances.push(instanceId);
  return instanceId;
}

/** Selector of the Home link to this instance's task (by task id, not by name). */
async function taskLinkSelector(page: Page, instanceId: number): Promise<string> {
  const task = await waitForTask(page, instanceId, TASK_NAME);
  return `a[href$="/task-review/${task.id}"]`;
}

test.describe('Running a process: user task', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, submitterCredentials());
  });

  test('RUN-01: A submitter starts a process, completes its task from Home, and the instance is Complete', async ({
    page,
  }) => {
    const instanceId = await startFromList(page);
    expect(await instanceStatus(page, instanceId)).toBe('user_input_required');

    const linkSelector = await taskLinkSelector(page, instanceId);
    await page.goto('/');
    const myTasks = page.locator('section, div').filter({
      has: page.getByRole('heading', { name: 'My tasks', exact: true }),
    });
    await myTasks.locator(linkSelector).first().click();
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
    await expect(page.locator(linkSelector)).toHaveCount(0);

    logResult('RUN-01', {
      scenario: 'Start a published process and complete its user task from Home',
      actions: ['Start from Processes', `Open "${TASK_NAME}" on Home`, 'Fill the form', 'Submit'],
      expected: 'Instance goes from User Input Required to Complete; the task leaves Home',
      actual: `Instance ${instanceId} is complete; task gone from My tasks`,
    });
  });

  test('RUN-02: The task form refuses a submit without its required fields', async ({ page }) => {
    const instanceId = await startFromList(page);

    const linkSelector = await taskLinkSelector(page, instanceId);
    await page.goto('/');
    await page.locator(linkSelector).first().click();
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
