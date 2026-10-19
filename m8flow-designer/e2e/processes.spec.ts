import { expect, test, type Page } from '@playwright/test';

import { editorCredentials, superAdminCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { createMockGroup, createMockModel, deleteMockGroup, deleteMockModel } from './helpers/mockCatalog';

/**
 * CHK-01..05, CHK-10 -- Processes list and Process Model Detail.
 *
 * Works on any instance: no groups/models, groups only, or groups with
 * models. Expected counts are read from the API at run time, and the tests
 * only act on mock data created here (a group with one model, plus an empty
 * group), which is deleted after the file runs. The instance's own process
 * groups and models are never changed.
 */

type ModelItem = { id: string; display_name: string; tenant_name?: string | null };
type GroupItem = { id: string };

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
const mock = {
  groupId: `e2e-catalog-${stamp}`,
  groupName: `E2E Catalog ${stamp}`,
  emptyGroupId: `e2e-catalog-empty-${stamp}`,
  emptyGroupName: `E2E Catalog Empty ${stamp}`,
  modelId: `e2e-catalog-model-${stamp}`,
  modelName: `E2E Catalog Model ${stamp}`,
  modelRouteId: '',
};

const countLabel = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;

async function apiList<T>(page: Page, path: string): Promise<T[]> {
  const result = await backendFetch(page, path);
  expect(result.status, `GET ${path}`).toBe(200);
  return result.body as T[];
}

/** Model rows of the Processes table (each row has an "Open" button). */
function modelRows(page: Page) {
  return page
    .getByRole('table')
    .getByRole('button')
    .filter({ has: page.getByRole('button', { name: 'Open', exact: true }) });
}

function modelRow(page: Page, name: string) {
  return modelRows(page).filter({ hasText: name });
}

test.describe('m8flow-designer Processes catalog', () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      await createMockGroup(page, { id: mock.groupId, display_name: mock.groupName });
      await createMockGroup(page, { id: mock.emptyGroupId, display_name: mock.emptyGroupName });
      mock.modelRouteId = await createMockModel(page, {
        group_id: mock.groupId,
        id: mock.modelId,
        display_name: mock.modelName,
      });
    } finally {
      await page.close();
    }
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, editorCredentials());
      if (mock.modelRouteId) await deleteMockModel(page, mock.modelRouteId);
      await deleteMockGroup(page, mock.groupId);
      await deleteMockGroup(page, mock.emptyGroupId);
    } finally {
      await page.close();
    }
  });

  test('CHK-01: editor sees the tenant-scoped process catalog', async ({ page }) => {
    await useSession(page, editorCredentials());
    const models = await apiList<ModelItem>(page, '/v1.0/m8flow/process-models');

    await page.goto('/processes');
    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toBeVisible();
    // Count matches whatever this instance holds (plus the mock model).
    await expect(page.getByText(countLabel(models.length, 'model'), { exact: true }).first()).toBeVisible();
    const row = modelRow(page, mock.modelName);
    await expect(row).toBeVisible();
    await expect(row).toContainText(mock.groupName);
    await expect(page.getByRole('alert')).toHaveCount(0);

    console.log(`[CHK-01] Editor sees the tenant's process catalog: ${countLabel(models.length, 'model')}, matching the API, including the mock model with its group.`);
  });

  test('CHK-02: search narrows the list and reports the empty state for no match', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    const models = await apiList<ModelItem>(page, '/v1.0/m8flow/process-models');
    await page.goto('/processes');

    const search = page.getByRole('searchbox', { name: 'Search process models' });
    await search.fill(mock.modelName);
    await expect(modelRows(page)).toHaveCount(1);
    await expect(modelRow(page, mock.modelName)).toBeVisible();

    await search.fill('no-such-process-model-xyz');
    await expect(page.getByText('No process models', { exact: true })).toBeVisible();
    await expect(page.getByText('Try a different search')).toBeVisible();
    await expect(modelRows(page)).toHaveCount(0);

    await search.fill('');
    await expect(page.getByText(countLabel(models.length, 'model'), { exact: true }).first()).toBeVisible();

    console.log('[CHK-02] Process search finds the mock model, shows the empty state when nothing matches, and restores the full list when cleared.');
  });

  test('CHK-03: All groups dropdown filters Processes by group and Clear resets it', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    const groups = await apiList<GroupItem>(page, '/v1.0/m8flow/process-groups');
    await page.goto('/processes');

    // Open the "All groups" dropdown: it lists every group in the tenant.
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Process groups' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(`${countLabel(groups.length, 'group')} in this tenant`)).toBeVisible();

    // Pick the mock group: only its model is listed.
    await dialog.getByRole('button').filter({ hasText: mock.groupName }).first().click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`[?&]group=${mock.groupId}`));
    await expect(page.getByRole('button', { name: 'All groups', exact: true })).toHaveCount(0);
    await expect(modelRows(page)).toHaveCount(1);
    await expect(modelRow(page, mock.modelName)).toBeVisible();

    // Clear resets the filter.
    await page.getByRole('button', { name: 'Clear', exact: true }).click();
    await expect(page).not.toHaveURL(/[?&]group=/);
    await expect(page.getByRole('button', { name: 'All groups', exact: true })).toBeVisible();

    // A group with no models shows its empty state; Clear filter resets it.
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    await dialog.getByRole('button').filter({ hasText: mock.emptyGroupName }).first().click();
    await expect(page.getByText('No models in this group', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Clear filter', exact: true }).click();
    await expect(page.getByRole('button', { name: 'All groups', exact: true })).toBeVisible();

    console.log('[CHK-03] All groups dropdown filtered the list to the selected group, showed the empty state for a group with no models, and Clear reset the filter.');
  });

  test('CHK-04: opening the first available process model shows its overview', async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto('/processes');

    // Whatever the first model on this instance is (the mock one at least exists).
    const firstRow = modelRows(page).first();
    await expect(firstRow).toBeVisible();
    const nameLines = (await firstRow.getByRole('cell').first().innerText())
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    const modelName = nameLines[0];

    await firstRow.getByRole('button', { name: 'Open', exact: true }).click();
    await expect(page).toHaveURL(/\/processes\/[^/?]+/);
    await expect(page.getByRole('heading', { name: modelName, exact: true })).toBeVisible();
    await expect(page.getByText(/^Files \(\d+\)$/)).toBeVisible();
    await expect(page.getByTestId('process-model-status')).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);

    console.log(`[CHK-04] Opened the first available process model "${modelName}"; its overview shows the name, status and files.`);
  });

  test('CHK-05: Process Model Detail reports not-found for an unknown model id', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());

    await page.goto('/processes/does-not-exist:nope');

    await expect(page.getByText('Process model not found.', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    console.log('[CHK-05] Unknown process model shows "Process model not found."');
  });

  test('CHK-10: super-admin sees processes of all tenants with tenant and group names', async ({
    page,
  }) => {
    await useSession(page, superAdminCredentials(), 'platformAdmin');
    // All-tenants read (no tenantId) -- what the page shows for "All tenants".
    const models = await apiList<ModelItem>(page, '/v1.0/m8flow/process-models');
    const mockItem = models.find((m) => m.display_name === mock.modelName);
    expect(mockItem, 'mock model in the all-tenants list').toBeTruthy();

    await page.goto('/processes');
    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toBeVisible();
    await expect(page.getByText('Choose a tenant')).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: 'Tenant', exact: true })).toBeVisible();
    await expect(page.getByText(countLabel(models.length, 'model'), { exact: true }).first()).toBeVisible();

    // The mock model row shows its tenant name and group name.
    const row = modelRow(page, mock.modelName);
    await expect(row).toBeVisible();
    if (mockItem?.tenant_name) {
      await expect(row.getByRole('cell').first()).toHaveText(mockItem.tenant_name);
    }
    await expect(row).toContainText(mock.groupName);

    // Every visible row shows a tenant name and a group.
    const rows = modelRows(page);
    const visible = await rows.count();
    for (let i = 0; i < visible; i += 1) {
      await expect(rows.nth(i).getByRole('cell').first()).not.toHaveText('');
      await expect(rows.nth(i).getByRole('cell').nth(1).getByRole('button').first()).toBeVisible();
    }

    console.log(`[CHK-10] Super admin sees ${countLabel(models.length, 'process model')} across all tenants without choosing a tenant; each row shows its tenant and group name.`);
  });
});
