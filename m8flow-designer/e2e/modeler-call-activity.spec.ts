import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openChangeElementMenu, selectElement } from './helpers/diagram';
import { SEED_MODELER_PATH, SEED_USER_TASK_ELEMENT_ID } from './helpers/fixtures';

/**
 * Call activity is dropped: catalog rejects `callActivity`; persist is not
 * restored. The pad cannot morph a task into a call activity, and the
 * called-element group is stripped. Do not assert Search / Launch Editor
 * persist — that would be re-enabling the dropped construct.
 */
test.describe('m8flow-designer Process Modeler — Call Activity guard', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('Change element does not offer Call activity', async ({ page }) => {
    const menu = await openChangeElementMenu(page, SEED_USER_TASK_ELEMENT_ID);
    await expect(menu.locator('[data-id="replace-with-call-activity"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="replace-with-event-subprocess"]')).toHaveCount(0);
  });

  test('Call Activity properties group is not shown on a task', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-called_element"]')).toHaveCount(0);
  });

  test('inactive multi-instance markers are not offered on the pad header', async ({ page }) => {
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    await page.locator('.djs-context-pad .entry[data-action="replace"]').click();
    const menu = page.locator('.djs-popup').last();
    await menu.waitFor({ state: 'visible' });
    await expect(menu.locator('[data-id="toggle-parallel-mi"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="toggle-sequential-mi"]')).toHaveCount(0);
  });
});
