import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openChangeElementMenu, selectElement } from './helpers/diagram';
import { SEED_USER_TASK_ELEMENT_ID } from './helpers/fixtures';

// Works on its own copy of the seeded "E2E Work From Home Request" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-callact', 'work-from-home');

/**
 * Call Activity and multi-instance constructs are now supported by the app.
 * Editing controls should remain available for both constructs. Tests here
 * assert that the modeler exposes them in the right selection context.
 */
test.describe('Process Modeler: Call Activity and multi-instance support', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('A task can be changed into a Call Activity', async ({ page }) => {
    const menu = await openChangeElementMenu(page, SEED_USER_TASK_ELEMENT_ID);
    const callActivityOption = menu.locator('[data-id="replace-with-call-activity"]');
    await expect(callActivityOption).toHaveCount(1);
    await expect(menu.locator('[data-id="replace-with-event-subprocess"]')).toHaveCount(0);
    await callActivityOption.click();
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-called_element"]')).toBeVisible();
    console.log('A task can be changed into a Call Activity and its Called Element settings are shown.');
  });

  test('Called Element settings are not shown on a regular task', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-called_element"]')).toHaveCount(0);
    console.log('Call Activity settings are hidden on a task.');
  });

  test('Parallel and sequential multi-instance options are offered', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await page.locator('.djs-context-pad .entry[data-action="replace"]').click();
    const menu = page.locator('.djs-popup').last();
    await menu.waitFor({ state: 'visible' });
    await expect(menu.locator('[data-id="toggle-parallel-mi"]')).toHaveCount(1);
    await expect(menu.locator('[data-id="toggle-sequential-mi"]')).toHaveCount(1);
    console.log('Parallel and sequential multi-instance options are offered.');
  });
});
