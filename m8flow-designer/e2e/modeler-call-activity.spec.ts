import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useMockProcessModel } from './helpers/mockCatalog';
import { openChangeElementMenu, selectElement } from './helpers/diagram';
import { SEED_MODELER_PATH, SEED_USER_TASK_ELEMENT_ID } from './helpers/fixtures';

// Creates the mock process model before these tests and deletes it after.
useMockProcessModel(test);

/**
 * Call activity is dropped: catalog rejects `callActivity`; persist is not
 * restored. The pad cannot morph a task into a call activity, and the
 * called-element group is stripped. Do not assert Search / Launch Editor
 * persist — that would be re-enabling the dropped construct.
 */
test.describe('Process Modeler: Call Activity is not available', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('A task cannot be changed into a Call Activity', async ({ page }) => {
    const menu = await openChangeElementMenu(page, SEED_USER_TASK_ELEMENT_ID);
    await expect(menu.locator('[data-id="replace-with-call-activity"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="replace-with-event-subprocess"]')).toHaveCount(0);
    console.log('A task cannot be changed into a Call Activity.');
  });

  test('Call Activity settings are not shown on a task', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-called_element"]')).toHaveCount(0);
    console.log('Call Activity settings are hidden on a task.');
  });

  test('Multi-instance (repeat) options are not offered', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await page.locator('.djs-context-pad .entry[data-action="replace"]').click();
    const menu = page.locator('.djs-popup').last();
    await menu.waitFor({ state: 'visible' });
    await expect(menu.locator('[data-id="toggle-parallel-mi"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="toggle-sequential-mi"]')).toHaveCount(0);
    console.log('Multi-instance options are not offered.');
  });
});
