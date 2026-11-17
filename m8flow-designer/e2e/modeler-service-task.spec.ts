import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openChangeElementMenu, openPropertiesPanelGroup, selectElement } from './helpers/diagram';

/**
 * Service Task connector wiring. BpmnCanvas answers
 * `spiff.service_tasks.requested` from `GET /connectors-grouped`, flattened
 * to `{id, parameters}[]`. An empty catalog is an honest Action-tab empty
 * state (not a blank Connector <select>); a live HTTP V2 catalog still
 * round-trips into the Parameters tab. The diagram is the seeded "E2E Invoice
 * Approval" template ("Check vendor registry", set to http/GetRequestV2).
 */
const SERVICE_TASK_FILE = 'invoice-approval.bpmn';
const SERVICE_TASK_ID = 'check_vendor';
/** A manual step of the same diagram, turned into a new (empty) service step by one test. */
const NEW_SERVICE_FROM_ID = 'schedule_payment';

/** How many total operations the live backend currently offers, across every connector. */
async function fetchRealOperationCount(page: import('@playwright/test').Page): Promise<number> {
  const response = await page.request.get('/v1.0/m8flow/connectors-grouped');
  const groups: Array<{ operations: unknown[] }> = await response.json();
  return groups.reduce((sum, g) => sum + g.operations.length, 0);
}

// Works on its own copy of the seeded "E2E Invoice Approval" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-service', 'invoice-approval');

test.describe('Process Modeler: Service Task connectors', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath(SERVICE_TASK_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, SERVICE_TASK_ID);
  });

  test('Connector settings appear right after General settings', async ({ page }) => {
    const groupIds = await page
      .locator('.bio-properties-panel-group')
      .evaluateAll((groups) => groups.map((g) => g.getAttribute('data-group-id')));
    const general = groupIds.indexOf('group-general');
    expect(general).toBeGreaterThanOrEqual(0);
    expect(groupIds[general + 1]).toBe('group-service_task_properties');
    await expect(
      page.locator('[data-group-id="group-service_task_properties"] .bio-properties-panel-group-header-title'),
    ).toHaveText('Connector');
    console.log('Connector settings appear right after General settings.');
  });

  test('Connector action cannot be chosen until a connector is picked', async ({ page }) => {
    test.skip((await fetchRealOperationCount(page)) === 0, 'connector-proxy catalog is empty in this environment');
    // A new service step has no connector yet: turn the manual step 'Schedule payment'
    // into a service step (in the editor only; nothing is saved) and open its settings.
    const menu = await openChangeElementMenu(page, NEW_SERVICE_FROM_ID);
    await menu.locator('[data-id="replace-with-service-task"]').click();
    // The editor selects the new service step itself; click it only if it did not.
    const connector = page.locator('.bio-properties-panel-group[data-group-id="group-service_task_properties"]');
    if (!(await connector.waitFor({ state: 'visible', timeout: 5_000 }).then(() => true, () => false))) {
      await selectElement(page, NEW_SERVICE_FROM_ID);
    }
    const group = await openPropertiesPanelGroup(page, 'service_task_properties');
    await expect(group.getByLabel('Connector', { exact: true })).toHaveValue('');
    await expect(group.getByLabel('Connector action')).toBeDisabled();
    console.log('Connector action cannot be chosen until a connector is picked.');
  });

  test('The Action list shows the connectors and actions set up in the system', async ({ page }) => {
    const expectedCount = await fetchRealOperationCount(page);
    const group = await openPropertiesPanelGroup(page, 'service_task_properties');

    if (expectedCount === 0) {
      await expect(
        group.getByText(/no connectors configured/i),
      ).toBeVisible();
      await expect(group.getByRole('link', { name: 'Setup → Connectors' })).toHaveAttribute(
        'href',
        '/connectors',
      );
      await expect(group.getByLabel('Connector', { exact: true })).toHaveCount(0);
      console.log('No connectors configured: empty state with the Setup → Connectors link is shown.');
      return;
    }

    // Connector → Connector action: summed per-connector actions (minus the
    // blank placeholder) equal the flat catalog size.
    const connector = group.getByLabel('Connector', { exact: true });
    const action = group.getByLabel('Connector action');
    await expect(connector).toBeVisible();
    const connectorIds = await nonEmptyOptionValues(connector);
    let total = 0;
    for (const id of connectorIds) {
      await connector.selectOption(id);
      total += (await nonEmptyOptionValues(action)).length;
    }
    expect(total).toBe(expectedCount);
    console.log('Connector actions match the connectors set up in the system.');
  });

  test('Choosing a connector action shows the fields for that action', async ({ page }) => {
    const expectedCount = await fetchRealOperationCount(page);
    test.skip(expectedCount === 0, 'connector-proxy catalog is empty in this environment');

    const group = await openPropertiesPanelGroup(page, 'service_task_properties');
    const connector = group.getByLabel('Connector', { exact: true });
    await expect(connector).toBeVisible();
    const [connectorId] = await nonEmptyOptionValues(connector);
    await connector.selectOption(connectorId);
    const action = group.getByLabel('Connector action');
    const [operatorId] = await nonEmptyOptionValues(action);
    expect(operatorId).toBeTruthy();
    await action.selectOption(operatorId);
    await group.getByRole('tab', { name: 'Parameters' }).click();
    await expect(group.locator('.m8flow-service-task-param-row')).not.toHaveCount(0);
    console.log('Selecting a connector action shows its parameter fields.');
  });

  test('Connector settings stay open while the connector list loads', async ({
    page,
  }) => {
    // `open` lives on the group's *header* element, not the group root
    // itself (confirmed live — @bpmn-io/properties-panel's own DOM, same
    // convention openPropertiesPanelGroup's internal check already uses).
    const group = await openPropertiesPanelGroup(page, 'service_task_properties');
    await page.waitForTimeout(500);
    await expect(group.locator(':scope > .bio-properties-panel-group-header')).toHaveClass(/open/);
    console.log('Connector settings stay open after the connector list loads.');
  });
});

async function nonEmptyOptionValues(select: import('@playwright/test').Locator): Promise<string[]> {
  return select.locator('option').evaluateAll((opts) =>
    opts.map((option) => (option as HTMLOptionElement).value).filter((value) => value !== ''),
  );
}
