import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openChangeElementMenu, paletteEntry, selectElement } from './helpers/diagram';

/**
 * Data-store persist is dropped. Palette and replace menu must not offer a
 * data store; the properties group is stripped. The fixture is a persistable
 * data object (keep-scope) so we never PUT a DataStoreReference. The diagram
 * is the seeded "E2E Order Fulfilment" template (its "Sales order" data object).
 */
const GUARD_FILE = 'order-fulfilment.bpmn';
const DATA_OBJECT_ID = 'order_ref';

// Works on its own copy of the seeded "E2E Order Fulfilment" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-datastore', 'order-fulfilment');

test.describe('Process Modeler: Data Store is not available', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath(GUARD_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('The toolbar has the supported shapes and no Data Store', async ({ page }) => {
    await expect(paletteEntry(page, 'space-tool')).toBeVisible();
    await expect(paletteEntry(page, 'create.intermediate-event')).toBeVisible();
    await expect(paletteEntry(page, 'create.subprocess-expanded')).toBeVisible();
    await expect(paletteEntry(page, 'create.participant-expanded')).toBeVisible();
    await expect(paletteEntry(page, 'create.group')).toBeVisible();
    await expect(paletteEntry(page, 'create.data-store')).toHaveCount(0);
    console.log('Toolbar has the supported shapes and no Data Store.');
  });

  test('A data object cannot be changed into a Data Store', async ({ page }) => {
    const menu = await openChangeElementMenu(page, DATA_OBJECT_ID);
    await expect(menu.locator('[data-id="replace-with-data-store-reference"]')).toHaveCount(0);
    await expect(menu.getByText('Data store', { exact: true })).toHaveCount(0);
    console.log('A data object cannot be changed into a Data Store.');
  });

  test('Data Store settings are not shown on a task', async ({ page }) => {
    await selectElement(page, 'enter_order');
    await expect(
      page.locator('.bio-properties-panel-group[data-group-id="group-custom-datastore-properties"]'),
    ).toHaveCount(0);
    console.log('Data Store settings are hidden on a task.');
  });
});
