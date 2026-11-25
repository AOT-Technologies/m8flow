import { expect, test } from '@playwright/test';

import { editorCredentials, useSession } from './helpers/auth';
import {
  openChangeElementMenu,
  openPropertiesPanelGroup,
  selectElement,
} from './helpers/diagram';
import { useSeededModelCopy } from './helpers/seedCatalog';

// Use an isolated copy so the test can change its start event and clean it up afterward.
const model = useSeededModelCopy(test, 'modeler-timer-start', 'work-from-home');
const START_EVENT_ID = 'start_wfh';
// BPMN tFormalExpression is evaluated by the Python expression engine; quote
// the ISO-8601 cycle so it evaluates to a string rather than a Python name.
const TIMER_CYCLE = "'R/PT5M'";

test.describe('Process Modeler: recurring timer start event', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(page.locator('.djs-container')).toBeVisible();
  });

  test('creates a timer start cycle and preserves it after save and reload', async ({ page }) => {
    const replaceMenu = await openChangeElementMenu(page, START_EVENT_ID);
    await expect(replaceMenu.locator('[data-id="replace-with-timer-start"]')).toBeVisible();
    await replaceMenu.locator('[data-id="replace-with-timer-start"]').click();

    const timerGroup = await openPropertiesPanelGroup(page, 'timer');
    const timerType = timerGroup.getByRole('combobox', { name: 'Type' });
    await timerType.selectOption('timeCycle');
    await timerGroup.getByRole('textbox', { name: 'Value' }).fill(TIMER_CYCLE);

    const saveResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === 'PUT' &&
        url.pathname.includes('/files/') &&
        url.pathname.endsWith(`/${model.primaryFile}`)
      );
    });
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    const saveResponse = await saveResponsePromise;
    expect(
      saveResponse.ok(),
      `Saving the timer-start BPMN failed: ${saveResponse.status()} ${await saveResponse.text()}`,
    ).toBe(true);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    // Reload forces the browser to fetch and re-import the saved BPMN from the
    // backend; checking the properties panel proves the moddle value round-trips.
    await page.reload();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, START_EVENT_ID);
    const reloadedTimerGroup = await openPropertiesPanelGroup(page, 'timer');
    await expect(reloadedTimerGroup.getByRole('combobox', { name: 'Type' })).toHaveValue('timeCycle');
    await expect(reloadedTimerGroup.getByRole('textbox', { name: 'Value' })).toHaveValue(TIMER_CYCLE);
  });
});
