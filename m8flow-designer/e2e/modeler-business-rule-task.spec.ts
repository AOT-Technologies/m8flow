import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Phase 2 — Business Rule Task / DMN wiring (phased Task Configuration
 * Parity plan, §Phase 2). Implemented: BpmnCanvas.tsx now answers
 * `spiff.dmn_files.requested` (from the process model's own file list,
 * filtered to `.dmn` — same pattern as Phase 1's JSON Schema Filename field)
 * and `spiff.dmn.edit` (navigates to the chosen .dmn file's own modeler
 * page — a genuine improvement over m8flow-frontend, whose one real
 * consumer leaves `onLaunchDmnEditor` a no-op).
 *
 * Files: travel-request.bpmn ("Decide approval level") and travel-policy.dmn of
 * the seeded "E2E Travel Request" template (e2e/seed/catalog/templates/travel-request/).
 */
const BPMN_FILE = 'travel-request.bpmn';
const DMN_FILE = 'travel-policy.dmn';
const BUSINESS_RULE_TASK_ID = 'decide_route';

// Works on its own copy of the seeded "E2E Travel Request" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-dmn', 'travel-request');

test.describe('Process Modeler: Business Rule Task (decision tables)', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath(BPMN_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, BUSINESS_RULE_TASK_ID);
  });

  test('The decision table list shows the decision tables in this process', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'business_rule_properties');
    const select = group.getByLabel('Select Decision Table');
    const optionLabels = await select.locator('option').allTextContents();
    expect(optionLabels).toContain(DMN_FILE);
    console.log('Decision table list shows the decision table from this process.');
  });

  test('Launch Editor opens the selected decision table', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'business_rule_properties');
    await group.getByLabel('Select Decision Table').selectOption(DMN_FILE);
    await group.getByRole('button', { name: 'Launch Editor' }).click();

    await expect(page).toHaveURL(urlPathEndsWith(`modeler/${DMN_FILE}`));
    // A real DMN diagram loaded, not just a URL change — dmn-js's own DRD
    // canvas renders the decision table shape.
    await expect(page.locator('.djs-container')).toBeVisible();
    await page.getByTitle('Zoom in').click();
    await page.getByTitle('Zoom out').click();
    await page.getByTitle('Fit to viewport').click();
    await expect(page.getByTitle('Zoom in')).toBeVisible();
    console.log('Launch Editor opened the selected decision table.');
  });
});
