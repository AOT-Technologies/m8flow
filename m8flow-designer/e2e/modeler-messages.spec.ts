import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openChangeElementMenu, openPropertiesPanelGroup, selectElement } from './helpers/diagram';

/**
 * Message events and process-level message models are dropped. Send/Receive
 * Task still keep the element-level `messages` group (catalog allows those
 * task types). Do not assert message-model persist, Add Message, or schema
 * Launch Editor for a message. The diagram is the seeded "E2E Travel Request"
 * template ("Send itinerary" send task).
 */
const SEND_TASK_FILE = 'travel-request.bpmn';
const SEND_TASK_ID = 'send_itinerary';

// Works on its own copy of the seeded "E2E Travel Request" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-messages', 'travel-request');

test.describe('Process Modeler: Message settings', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath(SEND_TASK_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('A start event cannot be changed into a message start event', async ({ page }) => {
    const menu = await openChangeElementMenu(page, 'start_trip');
    await expect(menu.locator('[data-id="replace-with-message-start"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="replace-with-non-interrupting-message-start"]')).toHaveCount(0);
    console.log('Start event cannot be changed into a message start event.');
  });

  test('Process-wide Messages and Correlation settings are not shown', async ({ page }) => {
    await page.locator('.djs-container').click({ position: { x: 8, y: 8 } });
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-messages"]')).toHaveCount(0);
    await expect(
      page.locator('.bio-properties-panel-group[data-group-id="group-correlation_properties"]'),
    ).toHaveCount(0);
    console.log('Process-wide Messages and Correlation settings are hidden.');
  });

  test('A Send Task still shows its Messages settings', async ({ page }) => {
    await selectElement(page, SEND_TASK_ID);
    const group = await openPropertiesPanelGroup(page, 'messages');
    await expect(group).toBeVisible();
    console.log('Send Task still shows its Messages settings.');
  });
});
