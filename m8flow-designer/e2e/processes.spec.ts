import { expect, test } from '@playwright/test';

import { editorCredentials, submitterCredentials, superAdminCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import {
  createMockGroup,
  createMockModel,
  deleteMockGroup,
  deleteMockModel,
  setModelStatus,
  useActiveCatalog,
  type ActiveCatalogModel,
  type MockModelStatus,
} from './helpers/mockCatalog';
import {
  closeMenu,
  apiList,
  chooseDropdown,
  countLabel,
  expectGroupForm,
  expectModelForm,
  expectProcessesToolbar,
  expectStatusOptionCount,
  GROUP_CREATE_HINT,
  GROUP_DELETE_HINT,
  GROUP_EDIT_HINT,
  GROUP_PICKER_HINT,
  isValueMissing,
  listedModelNames,
  logResult,
  menuItemLabels,
  mockApi,
  mockEmptyCatalog,
  MODEL_ID_HELP,
  modelRow,
  nameOfLength,
  modelRows,
  openRowMenu,
  STATUS_OPTIONS,
  type GroupItem,
  type ModelItem,
  type OwnerOption,
} from './helpers/processesPage';
import { urlGroupIs, urlPathEndsWith, urlPathHas } from './helpers/urls';

/**
 * Processes page (the list of process groups and process models).
 *
 * CHK-01..04, CHK-10  list basics: count, search, group filter, open a model, super-admin.
 * PRC-01..04, 25, 26 new tenant with no data (list calls mocked to return nothing):
 *                     empty page, page and dialog text, guided first group, load errors,
 *                     group form validation and boundary names.
 * PRC-05..15, 27..32, 40..48, PRC-24  tenant with data: create group and model, duplicate
 *                     names and ids, model form validation and boundary names, filters, sort,
 *                     list actions, edit/delete group, page text, server refusals and errors,
 *                     unusual characters, search and filter combinations, group search,
 *                     more than 25 models, nested groups, row click, role check.
 *
 * The process model page (opened from this list) is covered in process-models.spec.ts.
 * Tests act only on mock data created here, which is deleted afterwards.
 */

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

test.describe('Processes list', () => {
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

  test('CHK-01: An editor sees only their own tenant\'s processes', async ({ page }) => {
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

    console.log(`[CHK-01] Editor sees their tenant's processes: ${countLabel(models.length, 'model')}, including the test process and its group.`);
  });

  test('CHK-02: Search finds matching processes and shows a message when nothing matches', async ({
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

  test('CHK-03: The group filter shows only that group\'s processes, and Clear shows all again', async ({
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
    await expect(page).toHaveURL(urlGroupIs(mock.groupId));
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

  test('CHK-04: Opening a process shows its details', async ({ page }) => {
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

    console.log(`[CHK-04] Opened the first available process model "${modelName}"; its details show the name, status and files.`);
  });

  test('CHK-10: Super admin sees processes from all tenants, with tenant and group names', async ({
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

// ===========================================================================
// PRC-01..04, PRC-25..26 -- new tenant with no process groups or models.
// The list calls are mocked to return nothing, as for a brand-new tenant;
// writes still reach the real backend and are cleaned up.
// ===========================================================================
test.describe('Processes for a new tenant with no data (mocked API)', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await mockEmptyCatalog(page);
  });

  test('PRC-01: A new editor with no processes sees the empty page and the create buttons', async ({
    page,
  }) => {
    await page.goto('/processes');
    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toBeVisible();

    await expect(page.getByText('No process models', { exact: true })).toBeVisible();
    await expect(page.getByText('No models are available for this tenant yet.')).toBeVisible();
    await expect(page.getByText('0 models', { exact: true }).first()).toBeVisible();
    await expect(modelRows(page)).toHaveCount(0);
    await expect(page.getByTestId('processes-new-group-button')).toBeVisible();
    await expect(page.getByTestId('processes-new-group-button')).toBeEnabled();
    await expect(page.getByTestId('processes-new-group-button')).toHaveText('New process group');
    // Header button + empty-state button.
    await expect(page.getByRole('button', { name: 'New process model', exact: true })).toHaveCount(2);
    for (const button of await page.getByRole('button', { name: 'New process model', exact: true }).all()) {
      await expect(button).toBeEnabled();
    }
    await expectProcessesToolbar(page, { scope: 'All groups', models: 0 });
    await expect(page.getByRole('button', { name: 'Clear', exact: true })).toHaveCount(0);

    // Every status count is 0 and the Owner list only has "All".
    await page.getByRole('button', { name: 'Status: All' }).click();
    for (const option of ['all', 'published', 'draft', 'paused'] as const) {
      await expectStatusOptionCount(page, option, 0);
    }
    await closeMenu(page);
    await page.getByRole('button', { name: 'Owner: All' }).click();
    await expect(page.getByRole('menuitemradio')).toHaveCount(1);
    await closeMenu(page);

    // Searching an empty tenant gives the search hint.
    await page.getByRole('searchbox', { name: 'Search process models' }).fill('anything');
    const hint = 'Try a different search, or clear the search box.';
    await expect(page.getByText(hint)).toBeVisible();

    logResult('PRC-01', {
      scenario: 'New tenant, no process groups or models',
      actions: ['Open Processes', 'Open Status and Owner filters', 'Search "anything"'],
      expected: 'Empty state with create buttons; all status counts 0; Owner has only "All"; search hint shown',
      actual: '0 models, empty state shown, New process group + New process model visible and enabled, toolbar labels correct, filters empty',
      messages: ['No process models', 'No models are available for this tenant yet.', hint],
    });
  });

  test('PRC-02: The group list of a new tenant is empty and offers "New group"', async ({ page }) => {
    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();

    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await expect(picker).toBeVisible();
    await expect(picker.getByText('0 groups in this tenant')).toBeVisible();
    await expect(picker.getByRole('searchbox', { name: 'Search groups' })).toHaveAttribute(
      'placeholder',
      'Search 0 groups',
    );
    await expect(picker.getByRole('button', { name: /^All groups\s*0$/ })).toBeVisible();
    await expect(picker.getByText(GROUP_PICKER_HINT)).toBeVisible();
    await expect(picker.getByRole('button', { name: 'Close', exact: true })).toBeEnabled();
    await expect(picker.getByRole('button', { name: 'New group', exact: true })).toBeEnabled();

    await picker.getByRole('button', { name: 'New group', exact: true }).click();
    const create = page.getByRole('dialog', { name: 'New process group' });
    await expectGroupForm(create, 'create');
    await expect(create.getByRole('button', { name: 'Create group' })).toBeDisabled();
    await create.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Process groups' })).toBeVisible();
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    logResult('PRC-02', {
      scenario: 'New tenant opens the group list',
      actions: ['Click "All groups"', 'Click "New group"', 'Cancel', 'Close'],
      expected: '0 groups, "All groups 0", "New group" opens an empty create form with Create disabled',
      actual: 'Group list empty; create form shows its labels, placeholders and hint; "Create group" disabled; Cancel and Close worked',
      messages: ['0 groups in this tenant', GROUP_PICKER_HINT, GROUP_CREATE_HINT],
    });
  });

  test('PRC-03: A new editor is guided to create a process group first, then lands in it', async ({ page }) => {
    const group = { id: `e2e-first-group-${stamp}`, name: `E2E First Group ${stamp}` };
    try {
      await page.goto('/processes');
      await page.getByRole('button', { name: 'New process model', exact: true }).last().click();

      const dialog = page.getByRole('dialog', { name: 'New process model' });
      const noGroups = 'No process groups exist yet, and a model has to live in one.';
      await expect(dialog.getByText(noGroups)).toBeVisible();
      await expectModelForm(dialog);
      await expect(dialog.getByRole('combobox', { name: 'Process group' })).toHaveCount(0);
      await expect(dialog.getByTestId('create-process-model-new-group-button')).toHaveText('New process group');
      await expect(dialog.getByRole('button', { name: 'Create process model' })).toBeDisabled();
      await dialog.getByTestId('create-process-model-new-group-button').click();

      const picker = page.getByRole('dialog', { name: 'New process group' });
      await expect(picker).toBeVisible();
      await picker.getByLabel('Process group display name').fill(group.name);
      await expect(picker.getByLabel('Process group id')).not.toHaveValue('');
      await picker.getByLabel('Process group id').fill(group.id);
      await picker.getByRole('button', { name: 'Create group' }).click();

      await expect(picker).toHaveCount(0);
      await expect(page).toHaveURL(urlGroupIs(group.id));
      await expect(page.getByRole('button', { name: group.name, exact: true })).toBeVisible();
      await expect(page.getByText('No models in this group', { exact: true })).toBeVisible();
      const emptyHint = 'Create a model here, or clear the filter to see all 0 models.';
      await expect(page.getByText(emptyHint)).toBeVisible();
      const groups = await apiList<GroupItem>(page, '/v1.0/m8flow/process-groups');
      expect(groups.map((g) => g.id), 'new group exists on the server').toContain(group.id);

      logResult('PRC-03', {
        scenario: 'New tenant clicks "New process model" before any group exists',
        actions: ['Click "New process model"', 'Click "New process group"', `Create group "${group.name}"`],
        expected: 'Dialog explains a group is needed; after creating it the list is filtered to the new, empty group',
        actual: `Group "${group.name}" created; list filtered to it and shows the empty-group state`,
        messages: [noGroups, 'No models in this group', emptyHint],
      });
    } finally {
      await deleteMockGroup(page, group.id);
    }
  });

  test('PRC-04: Load errors are shown when the process list or group list cannot be loaded', async ({
    page,
  }) => {
    await mockApi(page, { method: 'GET', path: '/v1.0/m8flow/process-models' }, 500, {});
    await mockApi(page, { method: 'GET', path: '/v1.0/m8flow/process-groups' }, 500, {});

    await page.goto('/processes');
    const listError = page.getByRole('alert').filter({ hasText: /process-models.*failed: 500/ });
    await expect(listError).toBeVisible();
    await expect(modelRows(page)).toHaveCount(0);
    await expect(page.getByText('No process models', { exact: true })).toHaveCount(0);
    const listMessage = await listError.innerText();

    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    const groupsMessage = 'Couldn’t load process groups. Close this dialog and try again.';
    await expect(dialog.getByRole('alert')).toHaveText(groupsMessage);
    await expect(dialog.getByRole('button', { name: 'Create process model' })).toBeDisabled();
    await expect(dialog.getByTestId('create-process-model-new-group-button')).toHaveCount(0);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await expect(picker.getByRole('alert')).toContainText('failed: 500');

    logResult('PRC-04', {
      scenario: 'Process list and group list requests fail (mocked 500)',
      actions: ['Open Processes', 'Click "New process model"', 'Open "All groups"'],
      expected: 'Error message on the page, in the New process model dialog and in the group list; no rows; Create disabled',
      actual: 'All three error messages shown; no rows; Create process model disabled; no "New process group" offered',
      messages: [listMessage, groupsMessage],
    });
  });

  test('PRC-25: The New process group form blocks empty and invalid values', async ({ page }) => {
    let groupPosts = 0;
    page.on('request', (r) => {
      if (r.method() === 'POST' && new URL(r.url()).pathname === '/v1.0/m8flow/process-groups') groupPosts += 1;
    });
    await page.goto('/processes');
    await page.getByTestId('processes-new-group-button').click();
    const form = page.getByRole('dialog', { name: 'New process group' });
    const name = form.getByLabel('Process group display name');
    const id = form.getByLabel('Process group id');
    const create = form.getByRole('button', { name: 'Create group' });
    const checks: string[] = [];

    await expect(name).toHaveValue('');
    await expect(id).toHaveValue('');
    await expect(create).toBeDisabled();
    checks.push('empty form: Create disabled');

    // Only spaces or only special characters give no id, so Create stays disabled.
    for (const value of ['     ', '@#$%^&*()!']) {
      await name.fill(value);
      await expect(id).toHaveValue('');
      await expect(create).toBeDisabled();
      checks.push(`"${value}": no id, Create disabled`);
    }

    // The id drops leading/trailing spaces and keeps only a-z, 0-9, "-" and "_".
    const slugs: [string, string][] = [
      ['  Finance Team  ', 'finance-team'],
      ['Finance 2024 & Ops #1', 'finance-2024-ops-1'],
      ['Ops_Team-42', 'ops_team-42'],
    ];
    for (const [value, expected] of slugs) {
      await name.fill(value);
      await expect(id).toHaveValue(expected);
      await expect(create).toBeEnabled();
      checks.push(`"${value}" -> id "${expected}"`);
    }

    // Display name is required: with only an id, the browser blocks the form and nothing is sent.
    await name.fill('');
    await id.fill(`e2e-noname-${stamp}`);
    await create.click();
    expect(await isValueMissing(name)).toBe(true);
    await expect(page.getByRole('dialog', { name: 'New process group' })).toBeVisible();
    expect(groupPosts).toBe(0);
    checks.push('no display name: blocked by the browser, no request sent');

    // Ids the server does not accept.
    const invalid = 'Invalid process group identifier';
    for (const bad of ['Bad Id!', '-starts-with-dash', 'has:colon', 'has space']) {
      await name.fill('E2E Invalid');
      await id.fill(bad);
      await create.click();
      await expect(form.getByRole('alert')).toHaveText(invalid);
      await expect(page.getByRole('dialog', { name: 'New process group' })).toBeVisible();
      checks.push(`id "${bad}": refused`);
    }
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Process groups' })).toBeVisible();

    logResult('PRC-25', {
      scenario: 'New process group form with empty and invalid values (new tenant)',
      actions: ['Empty form', 'Spaces only', 'Special characters only', 'Mixed names', 'No display name', 'Invalid ids'],
      expected: 'Create disabled without an id; id built from letters/numbers only; no display name blocked; invalid ids refused with a message',
      actual: checks.join('; '),
      messages: [invalid],
    });
  });

  test('PRC-26: A process group is created with boundary names, and names are saved without extra spaces', async ({
    page,
  }) => {
    const cases = [
      { label: '1 character', name: 'Q', id: `e2e-min-${stamp}`, saved: 'Q' },
      { label: '120 characters', name: nameOfLength(`E2E Long ${stamp} `, 120), id: `e2e-long-${stamp}`, saved: '' },
      { label: 'leading/trailing spaces', name: `   E2E Trim ${stamp}   `, id: `e2e-trim-${stamp}`, saved: `E2E Trim ${stamp}` },
      { label: 'numbers and special characters', name: `E2E #1 & (Ops) ${stamp}`, id: `e2e-mixed-${stamp}`, saved: '' },
    ].map((c) => ({ ...c, saved: c.saved || c.name }));
    const results: string[] = [];
    try {
      for (const c of cases) {
        await page.goto('/processes');
        await page.getByTestId('processes-new-group-button').click();
        const form = page.getByRole('dialog', { name: 'New process group' });
        await form.getByLabel('Process group display name').fill(c.name);
        await form.getByLabel('Process group id').fill(c.id);
        await form.getByLabel('Process group description').fill('  E2E mock data -- safe to delete  ');
        await form.getByRole('button', { name: 'Create group' }).click();

        await expect(form).toHaveCount(0);
        await expect(page).toHaveURL(urlGroupIs(c.id));
        await expect(page.getByRole('button', { name: c.saved, exact: true })).toBeVisible();
        await expect(page.getByText('No models in this group', { exact: true })).toBeVisible();
        const saved = (await apiList<GroupItem & { description: string }>(page, '/v1.0/m8flow/process-groups')).find(
          (g) => g.id === c.id,
        );
        expect(saved?.display_name).toBe(c.saved);
        expect(saved?.description).toBe('E2E mock data -- safe to delete');
        results.push(`${c.label}: created as "${c.saved.length > 30 ? `${c.saved.slice(0, 30)}…` : c.saved}" (${c.saved.length} chars)`);
      }
    } finally {
      for (const c of cases) await deleteMockGroup(page, c.id);
    }

    logResult('PRC-26', {
      scenario: 'Create process groups with boundary names (new tenant)',
      actions: cases.map((c) => `Create group (${c.label})`),
      expected: 'Each group is created and selected; the saved name and description have no leading/trailing spaces',
      actual: results.join('; '),
    });
  });
});

// ===========================================================================
// PRC-05..15, PRC-27..32, PRC-40..48, PRC-24 -- tenant with data. A mock group with draft, published
// and paused models (one with a running instance) is created before the tests
// and deleted after them.
// ===========================================================================
const active = {
  groupId: `e2e-proc-${stamp}`,
  groupName: `E2E Proc ${stamp}`,
  models: {
    live: { id: `e2e-live-${stamp}`, name: `E2E Live ${stamp}`, status: 'published', files: true, instance: true },
    draft: { id: `e2e-draft-${stamp}`, name: `E2E Draft ${stamp}`, status: 'draft', files: true, instance: false },
    paused: { id: `e2e-paused-${stamp}`, name: `E2E Paused ${stamp}`, status: 'paused', files: true, instance: false },
    cycle: { id: `e2e-cycle-${stamp}`, name: `E2E Cycle ${stamp}`, status: 'published', files: true, instance: false },
    doomed: { id: `e2e-doomed-${stamp}`, name: `E2E Doomed ${stamp}`, status: 'draft', files: false, instance: false },
  } satisfies Record<string, ActiveCatalogModel>,
};
const M = active.models;
const allNames = Object.values(M).map((m) => m.name);
const route = (m: { id: string }) => `${active.groupId}:${m.id}`;
const groupPage = `/processes?group=${encodeURIComponent(active.groupId)}`;
const groupModelsApi = `/v1.0/m8flow/process-models?group=${encodeURIComponent(active.groupId)}`;
const STATUS_LABEL: Record<MockModelStatus, string> = { published: 'Published', draft: 'Draft', paused: 'Paused' };

test.describe('Processes for a tenant with data', () => {
  const created = useActiveCatalog(test, { id: active.groupId, name: active.groupName }, Object.values(M));

  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
  });

  // ---------------- Create group and process model ----------------

  test('PRC-05: An editor creates a process group and a process model from the Processes page', async ({
    page,
  }) => {
    const group = { id: `e2e-new-group-${stamp}`, name: `E2E New Group ${stamp}` };
    const model = { id: `e2e-new-model-${stamp}`, name: `E2E New Model ${stamp}` };
    created.groups.push(group.id);
    created.models.push(`${group.id}:${model.id}`);

    await page.goto('/processes');
    await page.getByTestId('processes-new-group-button').click();
    const picker = page.getByRole('dialog', { name: 'New process group' });
    const pickerHint = 'The id is generated from the display name. Edit it to nest with parent/child.';
    await expect(picker.getByText(pickerHint)).toBeVisible();
    await expect(picker.getByRole('button', { name: 'Create group' })).toBeDisabled();
    await picker.getByLabel('Process group display name').fill(group.name);
    await expect(picker.getByLabel('Process group id')).not.toHaveValue('');
    await picker.getByLabel('Process group id').fill(group.id);
    await picker.getByLabel('Process group description').fill('E2E mock data -- safe to delete');
    await picker.getByRole('button', { name: 'Create group' }).click();

    await expect(picker).toHaveCount(0);
    await expect(page).toHaveURL(urlGroupIs(group.id));
    await expect(page.getByText('No models in this group', { exact: true })).toBeVisible();

    // New process model from the empty group: the new group is preselected.
    await page.getByRole('button', { name: 'New process model', exact: true }).last().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await expect(
      dialog.getByText('Creates a model under a process group and a default BPMN you can open in the modeler.'),
    ).toBeVisible();
    await expect(dialog.getByRole('combobox', { name: 'Process group' })).toContainText(group.name);
    const submit = dialog.getByRole('button', { name: 'Create process model' });
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Display name').fill(model.name);
    await expect(dialog.getByLabel('Identifier')).not.toHaveValue('');
    await dialog.getByLabel('Identifier').fill(model.id);
    await dialog.getByLabel('Description (optional)').fill('E2E mock data -- safe to delete');
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page).toHaveURL(urlPathEndsWith(`/processes/${group.id}:${model.id}`));
    await expect(page.getByRole('heading', { name: model.name, exact: true })).toBeVisible();
    const status = page.getByTestId('process-model-status');
    await expect(status).toContainText('Draft');
    await expect(status).toContainText('Not published yet. Publish it to start instances.');
    await expect(page.getByRole('button', { name: 'Publish', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start process' })).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
    const saved = await backendFetch(page, `/v1.0/m8flow/process-models/${group.id}:${model.id}`);
    expect(saved.status, 'new model exists on the server').toBe(200);

    logResult('PRC-05', {
      scenario: 'Editor creates a new group, then a new model in it',
      actions: ['Click "New process group"', `Create "${group.name}"`, 'Click "New process model"', `Create "${model.name}"`],
      expected: 'Group created and selected; model created in it as Draft; its details page opens',
      actual: `Model page opened at /processes/${group.id}:${model.id} with status Draft, Publish shown, no Start`,
      messages: [pickerHint, 'No models in this group', 'Not published yet. Publish it to start instances.'],
    });
  });

  test('PRC-06: A process group or model with an id that is already used is not created', async ({ page }) => {
    const before = await apiList<ModelItem>(page, groupModelsApi);

    await page.goto('/processes');
    await page.getByTestId('processes-new-group-button').click();
    const picker = page.getByRole('dialog', { name: 'New process group' });
    await picker.getByLabel('Process group display name').fill(`${active.groupName} again`);
    await picker.getByLabel('Process group id').fill(active.groupId);
    await picker.getByRole('button', { name: 'Create group' }).click();
    const groupError = picker.getByRole('alert');
    await expect(groupError).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'New process group' })).toBeVisible();
    const groupMessage = await groupError.innerText();
    await picker.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Close', exact: true }).click();

    await page.goto(groupPage);
    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await expect(dialog.getByRole('combobox', { name: 'Process group' })).toContainText(active.groupName);
    await dialog.getByLabel('Display name').fill(`E2E Duplicate ${stamp}`);
    await dialog.getByLabel('Identifier').fill(M.draft.id);
    await dialog.getByRole('button', { name: 'Create process model' }).click();
    const modelError = dialog.getByRole('alert');
    await expect(modelError).toBeVisible();
    await expect(page).toHaveURL(/\/processes\?/);
    const modelMessage = await modelError.innerText();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

    const after = await apiList<ModelItem>(page, groupModelsApi);
    expect(after.length).toBe(before.length);

    logResult('PRC-06', {
      scenario: 'Create a group and a model with ids that already exist',
      actions: [`Create group with id "${active.groupId}"`, `Create model with id "${M.draft.id}"`],
      expected: 'Both are refused with an error message; the dialogs stay open; nothing new is created',
      actual: `Both refused; model count in the group stayed ${after.length}`,
      messages: [groupMessage, modelMessage],
    });
  });

  // ---------------- Filters and sorting ----------------

  test('PRC-07: The Status filter shows only Published, Draft or Paused process models', async ({ page }) => {
    const models = await apiList<ModelItem>(page, groupModelsApi);
    const names = (s: MockModelStatus) =>
      models.filter((m) => (m.status ?? 'published') === s).map((m) => m.display_name);

    await page.goto(groupPage);
    await expect(page.getByText(countLabel(models.length, 'model'), { exact: true }).first()).toBeVisible();
    await page.getByRole('button', { name: 'Status: All' }).click();
    await expectStatusOptionCount(page, 'all', models.length);
    for (const s of ['published', 'draft', 'paused'] as const) {
      await expectStatusOptionCount(page, s, names(s).length);
    }
    await closeMenu(page);

    const seen: string[] = [];
    for (const s of ['published', 'draft', 'paused'] as const) {
      await chooseDropdown(page, 'Status', STATUS_OPTIONS[s].name);
      await expect(page.getByRole('button', { name: `Status: ${STATUS_LABEL[s]}` })).toBeVisible();
      await expect(modelRows(page)).toHaveCount(names(s).length);
      for (const name of names(s)) {
        await expect(modelRow(page, name)).toContainText(STATUS_LABEL[s]);
      }
      seen.push(`${STATUS_LABEL[s]} ${names(s).length}`);
    }
    await expect(modelRow(page, M.live.name)).toHaveCount(0);
    await chooseDropdown(page, 'Status', /^All\b/);
    await expect(modelRows(page)).toHaveCount(models.length);

    logResult('PRC-07', {
      scenario: 'Filter the mock group by status',
      actions: ['Open Status', 'Choose Published, Draft, Paused', 'Choose All'],
      expected: 'Counts match the data; each choice lists only models with that status; All lists every model',
      actual: `Counts and rows matched: ${seen.join(', ')}; All ${models.length}`,
    });
  });

  test('PRC-08: The Owner filter shows only process models with instances started by that user', async ({
    page,
  }) => {
    const owners = (await backendFetch(page, '/v1.0/m8flow/process-instances/owners')).body as {
      owner_options?: OwnerOption[];
    };
    const me = owners.owner_options?.find((o) => o.username === editorCredentials().username);
    expect(me, 'editor is listed as an owner (it started the mock instance)').toBeTruthy();
    const mine = await apiList<ModelItem>(page, `${groupModelsApi}&started_by_id=${me!.id}`);
    const all = await apiList<ModelItem>(page, groupModelsApi);

    await page.goto(groupPage);
    await page.getByRole('button', { name: 'Owner: All' }).click();
    await expect(page.getByRole('menuitemradio', { name: 'All', exact: true })).toBeVisible();
    await expect(page.getByRole('menuitemradio', { name: me!.username, exact: true })).toBeVisible();
    await closeMenu(page);

    await chooseDropdown(page, 'Owner', me!.username);
    await expect(page.getByRole('button', { name: `Owner: ${me!.username}` })).toBeVisible();
    await expect(modelRows(page)).toHaveCount(mine.length);
    await expect(modelRow(page, M.live.name)).toBeVisible();
    await expect(modelRow(page, M.draft.name)).toHaveCount(0);

    await chooseDropdown(page, 'Owner', 'All');
    await expect(modelRows(page)).toHaveCount(all.length);

    logResult('PRC-08', {
      scenario: 'Filter the mock group by the user who started instances',
      actions: ['Open Owner', `Choose "${me!.username}"`, 'Choose All'],
      expected: 'Only models with an instance started by that user; All shows every model again',
      actual: `${countLabel(mine.length, 'model')} for ${me!.username} (includes "${M.live.name}", not "${M.draft.name}"); All ${all.length}`,
    });
  });

  test('PRC-09: Sorting by Newest first and Oldest first orders process models by their last run', async ({
    page,
  }) => {
    await page.goto(groupPage);
    await expect(page.getByRole('button', { name: 'Sort: Newest first' })).toBeVisible();
    await expect(modelRow(page, M.draft.name)).toBeVisible();
    const newest = await listedModelNames(page, allNames);
    expect(newest.indexOf(M.live.name)).toBeLessThan(newest.indexOf(M.draft.name));

    await chooseDropdown(page, 'Sort', 'Oldest first');
    await expect(page.getByRole('button', { name: 'Sort: Oldest first' })).toBeVisible();
    const oldest = await listedModelNames(page, allNames);
    expect(oldest.indexOf(M.live.name)).toBeGreaterThan(oldest.indexOf(M.draft.name));

    await chooseDropdown(page, 'Sort', 'Newest first');

    logResult('PRC-09', {
      scenario: 'Sort the mock group by last run',
      actions: ['Check default sort', 'Choose "Oldest first"', 'Choose "Newest first"'],
      expected: 'Newest first lists the model that ran before models that never ran; Oldest first reverses it',
      actual: `Newest first: "${M.live.name}" at #${newest.indexOf(M.live.name) + 1}; Oldest first: at #${oldest.indexOf(M.live.name) + 1}`,
    });
  });

  // ---------------- Process model actions in the list ----------------

  test('PRC-10: Start and Open work from the list; Start is only offered for published models', async ({
    page,
  }) => {
    await page.goto(groupPage);
    const start = (name: string) => modelRow(page, name).getByRole('button', { name: 'Start', exact: true });
    await expect(start(M.live.name)).toBeVisible();
    await expect(start(M.draft.name)).toHaveCount(0);
    await expect(start(M.paused.name)).toHaveCount(0);

    await modelRow(page, M.live.name).getByRole('button', { name: 'Open', exact: true }).click();
    await expect(page).toHaveURL(urlPathHas(`/processes/${route(M.live)}`));
    await expect(page.getByRole('heading', { name: M.live.name, exact: true })).toBeVisible();

    await page.goto(groupPage);
    const menu = await openRowMenu(page, M.draft.name);
    await menu.getByRole('menuitem', { name: 'Open', exact: true }).click();
    await expect(page.getByRole('heading', { name: M.draft.name, exact: true })).toBeVisible();

    await page.goto(groupPage);
    await start(M.live.name).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    created.instances.push(instanceId);

    logResult('PRC-10', {
      scenario: 'Start and Open process models from the list',
      actions: ['Check Start buttons', 'Open (button)', 'Open (menu)', `Start "${M.live.name}"`],
      expected: 'Start only on published models; Open shows the details page; Start opens the new instance',
      actual: `Start hidden for Draft and Paused; both Open paths worked; instance ${instanceId} opened`,
    });
  });

  test('PRC-11: A process that cannot be started shows the reason', async ({ page }) => {
    const startPath = /\/v1\.0\/m8flow\/process-models\/[^/]+\/start$/;
    await mockApi(page, { method: 'POST', path: startPath }, 422, {});
    await page.goto(groupPage);
    await modelRow(page, M.live.name).getByRole('button', { name: 'Start', exact: true }).click();
    const invalid = `“${M.live.name}” can’t be started — its diagram may be missing a start event.`;
    await expect(page.getByRole('alert')).toHaveText(invalid);
    await expect(page).toHaveURL(/\/processes\?/);

    await mockApi(page, { method: 'POST', path: startPath }, 403, {});
    await modelRow(page, M.live.name).getByRole('button', { name: 'Start', exact: true }).click();
    const denied = `You don’t have permission to start “${M.live.name}”.`;
    await expect(page.getByRole('alert')).toHaveText(denied);

    logResult('PRC-11', {
      scenario: 'Start is refused by the server (mocked 422 and 403)',
      actions: ['Click Start (422)', 'Click Start (403)'],
      expected: 'A clear reason is shown and the user stays on the list',
      actual: 'Both reasons shown; still on the Processes list',
      messages: [invalid, denied],
    });
  });

  test('PRC-12: Pause, Resume, Unpublish and Publish from the list change the status', async ({ page }) => {
    await page.goto(groupPage);
    const row = modelRow(page, M.cycle.name);
    const steps: string[] = [];
    const expectStatus = async (label: string, startShown: boolean) => {
      await expect(row.getByText(label, { exact: true })).toBeVisible();
      await expect(row.getByRole('button', { name: 'Start', exact: true })).toHaveCount(startShown ? 1 : 0);
    };
    const act = async (item: string, expectedItems: string[]) => {
      const menu = await openRowMenu(page, M.cycle.name);
      expect(await menuItemLabels(menu)).toEqual(expectedItems);
      await menu.getByRole('menuitem', { name: item, exact: true }).click();
      steps.push(item);
    };

    await expectStatus('Published', true);
    await act('Pause', ['Open', 'Pause', 'Unpublish', 'Delete']);
    await expectStatus('Paused', false);
    await act('Resume', ['Open', 'Resume', 'Unpublish', 'Delete']);
    await expectStatus('Published', true);
    await act('Unpublish', ['Open', 'Pause', 'Unpublish', 'Delete']);
    await expectStatus('Draft', false);
    await act('Publish', ['Open', 'Publish', 'Delete']);
    await expectStatus('Published', true);
    await expect(page.getByRole('alert')).toHaveCount(0);
    const saved = await backendFetch(page, `/v1.0/m8flow/process-models/${route(M.cycle)}`);
    expect((saved.body as { status: string }).status).toBe('published');

    logResult('PRC-12', {
      scenario: 'Move a model through its lifecycle from the row menu',
      actions: steps,
      expected: 'Each step changes the status pill, the menu offers only allowed steps, Start only when Published',
      actual: 'Published -> Paused -> Published -> Draft -> Published; menus and Start matched each status; saved as published',
    });
  });

  test('PRC-13: A status change refused by the server shows the reason', async ({ page }) => {
    const reason = 'Status changes are not allowed right now';
    await mockApi(page, { method: 'PUT', path: /\/v1\.0\/m8flow\/process-models\/[^/]+$/ }, 400, { message: reason });
    await page.goto(groupPage);
    const menu = await openRowMenu(page, M.cycle.name);
    await menu.getByRole('menuitem', { name: 'Pause', exact: true }).click();
    const message = `${M.cycle.name}: ${reason}`;
    await expect(page.getByRole('alert')).toHaveText(message);
    await expect(modelRow(page, M.cycle.name).getByText('Published', { exact: true })).toBeVisible();

    logResult('PRC-13', {
      scenario: 'Pause is refused by the server (mocked 400)',
      actions: ['Row menu -> Pause'],
      expected: 'Error names the model and the reason; the status does not change',
      actual: 'Error shown; status still Published',
      messages: [message],
    });
  });

  test('PRC-14: Delete asks for confirmation, Cancel keeps the model, Delete removes it', async ({ page }) => {
    await page.goto(groupPage);
    const confirm = page.getByRole('alertdialog', { name: 'Delete process model?' });
    const warning = `This permanently deletes ${M.doomed.name} and its files. This can’t be undone.`;

    let menu = await openRowMenu(page, M.doomed.name);
    await menu.getByRole('menuitem', { name: 'Delete', exact: true }).click();
    await expect(confirm).toContainText(warning);
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(confirm).toHaveCount(0);
    await expect(modelRow(page, M.doomed.name)).toBeVisible();

    menu = await openRowMenu(page, M.doomed.name);
    await menu.getByRole('menuitem', { name: 'Delete', exact: true }).click();
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(confirm).toHaveCount(0);
    await expect(modelRow(page, M.doomed.name)).toHaveCount(0);
    const gone = await backendFetch(page, `/v1.0/m8flow/process-models/${route(M.doomed)}`);
    expect(gone.status).toBe(404);

    logResult('PRC-14', {
      scenario: 'Delete a draft model with no instances',
      actions: ['Row menu -> Delete', 'Cancel', 'Row menu -> Delete', 'Delete'],
      expected: 'Confirmation names the model; Cancel keeps it; Delete removes it from the list and the server',
      actual: `"${M.doomed.name}" kept after Cancel, removed after Delete (server returns 404)`,
      messages: [warning],
    });
  });

  test('PRC-15: A process model with instances cannot be deleted', async ({ page }) => {
    await page.goto(groupPage);
    const menu = await openRowMenu(page, M.live.name);
    await menu.getByRole('menuitem', { name: 'Delete', exact: true }).click();
    const confirm = page.getByRole('alertdialog', { name: 'Delete process model?' });
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    const blocked =
      'This process model still has process instances and can’t be deleted. Remove or finish its instances first.';
    await expect(confirm.getByRole('alert')).toHaveText(blocked);
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(modelRow(page, M.live.name)).toBeVisible();

    logResult('PRC-15', {
      scenario: 'Delete a model that still has a process instance',
      actions: ['Row menu -> Delete', 'Delete', 'Cancel'],
      expected: 'Delete is refused with a clear message and the model stays',
      actual: `"${M.live.name}" not deleted; message shown in the confirmation`,
      messages: [blocked],
    });
  });

  // ---------------- Form validation (tenant with data) ----------------

  test('PRC-27: A name already used gives a new id for a group, and is refused for a model', async ({ page }) => {
    const before = await apiList<ModelItem>(page, groupModelsApi);

    // Open the list first so the existing groups are loaded before typing.
    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await expect(picker.getByRole('button').filter({ hasText: active.groupName }).first()).toBeVisible();
    await picker.getByRole('button', { name: 'New group', exact: true }).click();
    const form = page.getByRole('dialog', { name: 'New process group' });
    await form.getByLabel('Process group display name').fill(active.groupName);
    const suggested = `${active.groupId}-2`;
    await expect(form.getByLabel('Process group id')).toHaveValue(suggested);
    await expect(form.getByRole('button', { name: 'Create group' })).toBeEnabled();
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Close', exact: true }).click();

    // Same display name as an existing model in the group: same identifier, refused.
    await page.goto(groupPage);
    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await dialog.getByLabel('Display name').fill(M.draft.name);
    await expect(dialog.getByLabel('Identifier')).toHaveValue(M.draft.id);
    await dialog.getByRole('button', { name: 'Create process model' }).click();
    const error = dialog.getByRole('alert');
    await expect(error).toContainText('failed: 409');
    await expect(page).toHaveURL(/\/processes\?/);
    const message = await error.innerText();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    expect((await apiList<ModelItem>(page, groupModelsApi)).length).toBe(before.length);

    logResult('PRC-27', {
      scenario: 'Reuse the name of an existing group and of an existing model',
      actions: [`Type group name "${active.groupName}"`, `Type model name "${M.draft.name}" and Create`],
      expected: 'Group form suggests a free id ending in "-2"; the model is refused because its id is already used',
      actual: `Suggested group id "${suggested}"; model refused; model count stayed ${before.length}`,
      messages: [message],
    });
  });

  test('PRC-28: The New process model form blocks empty and invalid values', async ({ page }) => {
    const before = await apiList<ModelItem>(page, groupModelsApi);
    await page.goto(groupPage);
    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await expectModelForm(dialog);
    const group = dialog.getByRole('combobox', { name: 'Process group' });
    await expect(group).toContainText(active.groupName);
    await group.click();
    const groupOption = page.getByRole('option', { name: active.groupName, exact: true });
    await expect(groupOption).toBeVisible();
    // Close the list by picking the same group. Escape can close the whole
    // dialog when the list has already closed (seen in CI).
    await groupOption.click();
    await expect(groupOption).toHaveCount(0);
    await expect(dialog).toBeVisible();
    await expect(group).toContainText(active.groupName);

    const name = dialog.getByLabel('Display name');
    const id = dialog.getByLabel('Identifier');
    const create = dialog.getByRole('button', { name: 'Create process model' });
    const checks: string[] = [];
    await expect(create).toBeDisabled();
    checks.push('empty form: Create disabled');

    for (const value of ['     ', '@#$%^&*()!']) {
      await name.fill(value);
      await expect(id).toHaveValue('');
      await expect(create).toBeDisabled();
      checks.push(`"${value}": no identifier, Create disabled`);
    }
    const slugs: [string, string][] = [
      ['  Invoice Approval  ', 'invoice-approval'],
      ['Invoice 2024 & Q4 #1', 'invoice-2024-q4-1'],
    ];
    for (const [value, expected] of slugs) {
      await name.fill(value);
      await expect(id).toHaveValue(expected);
      checks.push(`"${value}" -> "${expected}"`);
    }

    // An identifier typed by the user is kept when the name changes.
    await id.fill('my-custom-id');
    await name.fill('Another Name');
    await expect(id).toHaveValue('my-custom-id');
    checks.push('typed identifier kept when the name changes');

    // Empty or space-only identifier disables Create.
    for (const value of ['', '   ']) {
      await id.fill(value);
      await expect(create).toBeDisabled();
    }
    checks.push('empty / space-only identifier: Create disabled');

    // Identifiers the server does not accept.
    for (const bad of ['Bad Id!', 'a/b', '-starts-with-dash']) {
      await id.fill(bad);
      await create.click();
      await expect(dialog.getByRole('alert')).toContainText('failed: 400');
      await expect(page).toHaveURL(/\/processes\?/);
      checks.push(`identifier "${bad}": refused`);
    }
    const message = await dialog.getByRole('alert').innerText();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect((await apiList<ModelItem>(page, groupModelsApi)).length).toBe(before.length);

    logResult('PRC-28', {
      scenario: 'New process model form with empty and invalid values',
      actions: ['Check labels and group list', 'Spaces / special characters', 'Mixed names', 'Edit identifier', 'Invalid identifiers'],
      expected: 'Create disabled without a name or identifier; identifier built from letters/numbers; typed identifier kept; invalid identifiers refused; nothing created',
      actual: checks.join('; '),
      messages: [MODEL_ID_HELP, message],
    });
  });

  test('PRC-29: A process model is created with boundary names, and names are saved without extra spaces', async ({
    page,
  }) => {
    const cases = [
      { label: '1 character', name: 'Q', id: `e2e-q-${stamp}`, saved: 'Q' },
      { label: '150 characters', name: nameOfLength(`E2E Long Model ${stamp} `, 150), id: `e2e-long-model-${stamp}`, saved: '' },
      { label: 'spaces, numbers and special characters', name: `  E2E Mixed #1 & Co ${stamp}  `, id: '', saved: `E2E Mixed #1 & Co ${stamp}` },
    ].map((c) => ({ ...c, saved: c.saved || c.name }));
    const results: string[] = [];
    for (const c of cases) {
      const expectedId = c.id || `e2e-mixed-1-co-${stamp}`;
      created.models.push(`${active.groupId}:${expectedId}`);
      await page.goto(groupPage);
      await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
      const dialog = page.getByRole('dialog', { name: 'New process model' });
      await dialog.getByLabel('Display name').fill(c.name);
      if (c.id) await dialog.getByLabel('Identifier').fill(c.id);
      await expect(dialog.getByLabel('Identifier')).toHaveValue(expectedId);
      await dialog.getByRole('button', { name: 'Create process model' }).click();

      await expect(page).toHaveURL(urlPathEndsWith(`/processes/${active.groupId}:${expectedId}`));
      await expect(page.getByRole('heading', { name: c.saved, exact: true })).toBeVisible();
      await expect(page.getByTestId('process-model-status')).toContainText('Draft');
      const saved = await backendFetch(page, `/v1.0/m8flow/process-models/${active.groupId}:${expectedId}`);
      expect((saved.body as { display_name: string }).display_name).toBe(c.saved);
      results.push(`${c.label}: created as "${expectedId}" (${c.saved.length}-char name)`);
    }

    logResult('PRC-29', {
      scenario: 'Create process models with boundary names',
      actions: cases.map((c) => `Create model (${c.label})`),
      expected: 'Each model is created as Draft and its page opens; the saved name has no leading/trailing spaces',
      actual: results.join('; '),
    });
  });

  // ---------------- Edit and delete process groups ----------------

  test('PRC-30: A process group can be renamed; the id cannot change and the name is required', async ({ page }) => {
    const group = { id: `e2e-edit-group-${stamp}`, name: `E2E Edit Group ${stamp}` };
    const renamed = `E2E Edited ${stamp}`;
    created.groups.push(group.id);
    await createMockGroup(page, { id: group.id, display_name: group.name });

    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await picker.getByRole('button', { name: `Edit ${group.name}`, exact: true }).click();
    const form = page.getByRole('dialog', { name: 'Edit process group' });
    await expectGroupForm(form, 'edit');
    await expect(form.getByLabel('Process group id')).toHaveValue(group.id);
    await expect(form.getByLabel('Process group display name')).toHaveValue(group.name);
    await expect(form.getByRole('button', { name: 'Save group' })).toBeEnabled();

    // Cancel keeps the old name.
    await form.getByLabel('Process group display name').fill('Not saved');
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(picker.getByRole('button', { name: `Edit ${group.name}`, exact: true })).toBeVisible();

    // Empty name is blocked.
    await picker.getByRole('button', { name: `Edit ${group.name}`, exact: true }).click();
    await form.getByLabel('Process group display name').fill('');
    await form.getByRole('button', { name: 'Save group' }).click();
    expect(await isValueMissing(form.getByLabel('Process group display name'))).toBe(true);
    await expect(page.getByRole('dialog', { name: 'Edit process group' })).toBeVisible();

    // Save trims the name and description.
    await form.getByLabel('Process group display name').fill(`  ${renamed}  `);
    await form.getByLabel('Process group description').fill('  Renamed by E2E  ');
    await form.getByRole('button', { name: 'Save group' }).click();
    await expect(page.getByRole('dialog', { name: 'Process groups' })).toBeVisible();
    const row = picker.getByRole('button').filter({ hasText: renamed }).first();
    await expect(row).toContainText('Renamed by E2E');
    const saved = (await apiList<GroupItem>(page, '/v1.0/m8flow/process-groups')).find((g) => g.id === group.id);
    expect(saved?.display_name).toBe(renamed);

    logResult('PRC-30', {
      scenario: 'Rename a process group from the group list',
      actions: ['Pencil -> Cancel', 'Pencil -> empty name -> Save', 'Pencil -> new name with spaces -> Save'],
      expected: 'Edit form shows the id read-only; Cancel keeps the name; empty name blocked; saved name and description trimmed',
      actual: `Id "${group.id}" read-only; Cancel kept "${group.name}"; empty name blocked; renamed to "${renamed}"`,
      messages: [GROUP_EDIT_HINT],
    });
  });

  test('PRC-31: Deleting a process group asks first, removes an empty group, and is blocked while it has instances', async ({
    page,
  }) => {
    const group = { id: `e2e-delete-group-${stamp}`, name: `E2E Delete Group ${stamp}` };
    created.groups.push(group.id);
    await createMockGroup(page, { id: group.id, display_name: group.name });
    const before = await apiList<GroupItem>(page, '/v1.0/m8flow/process-groups');

    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await expect(picker.getByText(`${countLabel(before.length, 'group')} in this tenant`)).toBeVisible();

    await picker.getByRole('button', { name: `Delete ${group.name}`, exact: true }).click();
    const confirm = page.getByRole('dialog', { name: 'Delete process group' });
    const question = `Delete “${group.name}”? This removes the folder and its process models from the catalog.`;
    await expect(confirm.getByText(GROUP_DELETE_HINT)).toBeVisible();
    await expect(confirm.getByText(question)).toBeVisible();
    await expect(confirm.getByRole('button', { name: 'Delete group' })).toBeEnabled();
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(picker.getByRole('button', { name: `Delete ${group.name}`, exact: true })).toBeVisible();

    await picker.getByRole('button', { name: `Delete ${group.name}`, exact: true }).click();
    await confirm.getByRole('button', { name: 'Delete group' }).click();
    await expect(page.getByRole('dialog', { name: 'Process groups' })).toBeVisible();
    await expect(picker.getByRole('button', { name: `Delete ${group.name}`, exact: true })).toHaveCount(0);
    await expect(picker.getByText(`${countLabel(before.length - 1, 'group')} in this tenant`)).toBeVisible();

    // The mock group has a model with a running instance.
    await picker.getByRole('button', { name: `Delete ${active.groupName}`, exact: true }).click();
    await confirm.getByRole('button', { name: 'Delete group' }).click();
    const blocked =
      'This process group still has process instances and can’t be deleted. Remove or finish its instances first.';
    await expect(confirm.getByRole('alert')).toHaveText(blocked);
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(picker.getByRole('button', { name: `Delete ${active.groupName}`, exact: true })).toBeVisible();

    logResult('PRC-31', {
      scenario: 'Delete process groups from the group list',
      actions: ['Trash -> Cancel', 'Trash -> Delete group (empty group)', 'Trash -> Delete group (group with an instance)'],
      expected: 'Confirmation names the group; Cancel keeps it; an empty group is removed; a group with instances is refused',
      actual: `"${group.name}" kept on Cancel then removed (${before.length} -> ${before.length - 1} groups); "${active.groupName}" refused`,
      messages: [GROUP_DELETE_HINT, question, blocked],
    });
  });

  // ---------------- Page text and controls ----------------

  test('PRC-32: The Processes page with data shows its labels, columns and row buttons', async ({ page }) => {
    const models = await apiList<ModelItem>(page, groupModelsApi);
    await page.goto(groupPage);
    await expectProcessesToolbar(page, { scope: active.groupName, models: models.length });
    await expect(page.getByRole('button', { name: 'Clear', exact: true })).toBeEnabled();
    await expect(page.getByTestId('processes-new-group-button')).toBeEnabled();
    await expect(page.getByRole('button', { name: 'New process model', exact: true })).toBeEnabled();

    for (const header of ['Process model', 'Status', 'Runs 30d', 'Last run', 'Actions']) {
      await expect(page.getByRole('columnheader', { name: header, exact: true })).toBeVisible();
    }
    await expect(page.getByText('Rows per page: 25')).toBeVisible();
    await expect(page.getByText(`1–${models.length}`, { exact: true })).toBeVisible();

    const live = modelRow(page, M.live.name);
    await expect(live.getByRole('button', { name: 'Start', exact: true })).toBeEnabled();
    await expect(live.getByRole('button', { name: 'Open', exact: true })).toBeEnabled();
    await expect(live.getByRole('button', { name: 'More actions', exact: true })).toBeEnabled();
    await expect(live.getByText('Published', { exact: true })).toBeVisible();
    await expect(modelRow(page, M.draft.name).getByText('—', { exact: true })).toBeVisible();

    // The group name under a model filters the list to that group.
    await page.goto('/processes');
    await modelRow(page, M.live.name).getByRole('button', { name: active.groupName, exact: true }).click();
    await expect(page).toHaveURL(urlGroupIs(active.groupId));
    await expect(modelRows(page)).toHaveCount(models.length);

    logResult('PRC-32', {
      scenario: 'Labels and controls of the Processes page with data',
      actions: ['Open the mock group', 'Check toolbar, columns, footer and row buttons', 'Click a group name under a model'],
      expected: 'Toolbar, column headers and footer shown; row buttons enabled; group name filters the list',
      actual: `${countLabel(models.length, 'model')}; all labels and buttons shown; group link filtered to "${active.groupName}"`,
      messages: ['Rows per page: 25'],
    });
  });

  // ---------------- More edge cases ----------------

  test('PRC-40: The server refuses to start a draft or paused model, also when the list is out of date', async ({
    page,
  }) => {
    const replies: string[] = [];
    for (const [m, status] of [[M.draft, 'draft'], [M.paused, 'paused']] as const) {
      const result = await backendFetch(page, `/v1.0/m8flow/process-models/${route(m)}/start`, { method: 'POST' });
      expect(result.status, `start ${status} model`).toBe(409);
      const message = (result.body as { message?: string }).message;
      expect(message).toBe(`Process model is ${status} and cannot be started. Publish it first.`);
      replies.push(message!);
    }

    // The list still shows Start, but the model was paused in the meantime (another tab or user).
    const pausedMessage = 'Process model is paused and cannot be started. Publish it first.';
    try {
      await setModelStatus(page, route(M.cycle), 'published');
      await page.goto(groupPage);
      const start = modelRow(page, M.cycle.name).getByRole('button', { name: 'Start', exact: true });
      await expect(start).toBeVisible();
      await setModelStatus(page, route(M.cycle), 'paused');
      await start.click();
      await expect(page.getByRole('alert')).toHaveText(pausedMessage);
      await expect(page).toHaveURL(/\/processes\?/);
    } finally {
      await setModelStatus(page, route(M.cycle), 'published');
    }

    logResult('PRC-40', {
      scenario: 'Start a draft or paused model (direct server call and an out-of-date list)',
      actions: ['POST start for the draft model', 'POST start for the paused model', 'Pause a model after the list loaded, then click Start'],
      expected: 'The server refuses both (409) with a clear reason; the page shows the reason and stays on the list',
      actual: 'Both refused with 409; the page showed the server reason',
      messages: [...replies, pausedMessage],
    });
  });

  test('PRC-42: Search ignores upper/lower case, finds by name, id or group, and Escape and Ctrl+K work', async ({
    page,
  }) => {
    const inGroup = await apiList<ModelItem>(page, groupModelsApi);
    await page.goto('/processes');
    const search = page.getByRole('searchbox', { name: 'Search process models' });
    const checks: string[] = [];

    await search.fill(M.live.name.toUpperCase());
    await expect(modelRows(page)).toHaveCount(1);
    await expect(modelRow(page, M.live.name)).toBeVisible();
    checks.push('upper-case name: 1 row');

    await search.fill(`cycle-${stamp}`);
    await expect(modelRows(page)).toHaveCount(1);
    await expect(modelRow(page, M.cycle.name)).toBeVisible();
    checks.push('part of the id: 1 row');

    await search.fill(active.groupName);
    await expect(modelRows(page)).toHaveCount(inGroup.length);
    checks.push(`group name: ${inGroup.length} rows`);

    await search.fill('%$#@!');
    await expect(page.getByText('No process models', { exact: true })).toBeVisible();
    await expect(page.getByText('Try a different search, or clear the search box.')).toBeVisible();
    checks.push('special characters: empty state');

    await search.press('Escape');
    await expect(search).toHaveValue('');
    await expect(search).not.toBeFocused();
    await expect(modelRow(page, M.live.name)).toBeVisible();
    checks.push('Escape: search cleared');

    await page.getByRole('heading', { name: 'Processes', exact: true }).click();
    await page.keyboard.press('Control+k');
    await expect(search).toBeFocused();
    checks.push('Ctrl+K: search focused');

    logResult('PRC-42', {
      scenario: 'Search edge cases and keyboard shortcuts',
      actions: ['Upper-case name', 'Part of an id', 'Group name', 'Special characters', 'Escape', 'Ctrl+K'],
      expected: 'Search is not case sensitive and matches name, id and group; no match shows the hint; Escape clears; Ctrl+K focuses search',
      actual: checks.join('; '),
      messages: ['Try a different search, or clear the search box.'],
    });
  });

  test('PRC-43: Status, Owner and search can be combined, and an empty combination shows a message', async ({
    page,
  }) => {
    await page.goto(groupPage);
    const checks: string[] = [];

    // Draft models never ran, so Draft + Owner "editor" is empty.
    await chooseDropdown(page, 'Status', /^Draft\b/);
    await chooseDropdown(page, 'Owner', editorCredentials().username);
    await expect(modelRows(page)).toHaveCount(0);
    await expect(page.getByText('No models in this group', { exact: true })).toBeVisible();
    const hint = page.getByText(/^Create a model here, or clear the filter to see all \d+ models\.$/);
    await expect(hint).toBeVisible();
    const hintText = await hint.innerText();
    checks.push('Draft + editor: empty state');
    await chooseDropdown(page, 'Owner', 'All');

    await chooseDropdown(page, 'Status', /^Paused\b/);
    const search = page.getByRole('searchbox', { name: 'Search process models' });
    await search.fill(M.paused.name);
    await expect(modelRows(page)).toHaveCount(1);
    await search.fill(M.live.name);
    await expect(modelRows(page)).toHaveCount(0);
    checks.push('Paused + search: only paused names match');

    await chooseDropdown(page, 'Status', /^Published\b/);
    await search.fill(`cycle-${stamp}`);
    await expect(modelRows(page)).toHaveCount(1);
    await expect(modelRow(page, M.cycle.name)).toContainText('Published');
    checks.push('Published + search: 1 row');

    await search.fill('');
    await chooseDropdown(page, 'Status', /^All\b/);
    await expect(modelRow(page, M.draft.name)).toBeVisible();

    logResult('PRC-43', {
      scenario: 'Combine Status, Owner and search in the mock group',
      actions: ['Draft + Owner editor', 'Paused + search', 'Published + search', 'Reset'],
      expected: 'Only models matching every filter are listed; no match shows the empty-group message',
      actual: checks.join('; '),
      messages: ['No models in this group', hintText],
    });
  });

  test('PRC-44: The group list search finds groups by name or id, not case sensitive', async ({ page }) => {
    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    const search = picker.getByRole('searchbox', { name: 'Search groups' });
    const groupRows = picker.getByRole('button', { name: /^Edit / });
    const checks: string[] = [];

    for (const value of [active.groupName, active.groupName.toUpperCase(), active.groupId]) {
      await search.fill(value);
      await expect(groupRows).toHaveCount(1);
      await expect(picker.getByRole('button', { name: `Edit ${active.groupName}`, exact: true })).toBeVisible();
      checks.push(`"${value}": 1 group`);
    }
    await search.fill('no-such-group-xyz');
    await expect(groupRows).toHaveCount(0);
    await expect(picker.getByRole('button', { name: /^All groups/ })).toBeVisible();
    checks.push('no match: only "All groups" left');

    logResult('PRC-44', {
      scenario: 'Search inside the group list',
      actions: ['Search by name', 'Search in upper case', 'Search by id', 'Search with no match'],
      expected: 'Matching group shown for name, upper-case name and id; no match leaves only "All groups"',
      actual: checks.join('; '),
    });
  });

  test('PRC-45: A group with more than 25 models lists all of them', async ({ page }) => {
    test.setTimeout(180_000);
    const big = { id: `e2e-many-${stamp}`, name: `E2E Many ${stamp}` };
    const total = 27;
    created.groups.push(big.id);
    await createMockGroup(page, { id: big.id, display_name: big.name });
    for (let i = 1; i <= total; i += 1) {
      const id = `e2e-many-${String(i).padStart(2, '0')}-${stamp}`;
      created.models.push(await createMockModel(page, { group_id: big.id, id, display_name: `E2E Many ${i} ${stamp}` }));
    }

    await page.goto(`/processes?group=${encodeURIComponent(big.id)}`);
    await expect(modelRows(page)).toHaveCount(total);
    await expect(page.getByText(countLabel(total, 'model'), { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Rows per page: 25')).toBeVisible();
    await expect(page.getByText(`1–${total}`, { exact: true })).toBeVisible();

    logResult('PRC-45', {
      scenario: 'Group with more models than one page',
      actions: [`Create ${total} models`, 'Open the group'],
      expected: 'Every model can be reached',
      actual: `${total} rows listed; footer shows "Rows per page: 25" and "1–${total}" (all rows on one page, no page buttons)`,
      messages: ['Rows per page: 25'],
    });
  });

  test('PRC-46: Server errors while creating, renaming or deleting are shown and nothing changes', async ({ page }) => {
    const reason = 'Service unavailable';
    const groupItem = /^\/v1\.0\/m8flow\/process-groups\/.+$/;
    await mockApi(page, { method: 'POST', path: '/v1.0/m8flow/process-groups' }, 500, { message: reason });
    await mockApi(page, { method: 'PUT', path: groupItem }, 500, { message: reason });
    await mockApi(page, { method: 'DELETE', path: groupItem }, 500, { message: reason });
    await mockApi(page, { method: 'POST', path: '/v1.0/m8flow/process-models' }, 500, {});
    await mockApi(page, { method: 'DELETE', path: /^\/v1\.0\/m8flow\/process-models\/[^/]+$/ }, 500, {});
    const checks: string[] = [];

    await page.goto('/processes');
    await page.getByRole('button', { name: 'All groups', exact: true }).click();
    const picker = page.getByRole('dialog', { name: 'Process groups' });
    await picker.getByRole('button', { name: 'New group', exact: true }).click();
    let form = page.getByRole('dialog', { name: 'New process group' });
    await form.getByLabel('Process group display name').fill(`E2E Fail ${stamp}`);
    await form.getByRole('button', { name: 'Create group' }).click();
    await expect(form.getByRole('alert')).toHaveText(reason);
    checks.push('create group: error shown');
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();

    await picker.getByRole('button', { name: `Edit ${active.groupName}`, exact: true }).click();
    form = page.getByRole('dialog', { name: 'Edit process group' });
    await form.getByLabel('Process group display name').fill('Not saved');
    await form.getByRole('button', { name: 'Save group' }).click();
    await expect(form.getByRole('alert')).toHaveText(reason);
    checks.push('rename group: error shown');
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();

    await picker.getByRole('button', { name: `Delete ${active.groupName}`, exact: true }).click();
    form = page.getByRole('dialog', { name: 'Delete process group' });
    await form.getByRole('button', { name: 'Delete group' }).click();
    await expect(form.getByRole('alert')).toHaveText(reason);
    checks.push('delete group: error shown');
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Close', exact: true }).click();

    await page.goto(groupPage);
    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await dialog.getByLabel('Display name').fill(`E2E Fail Model ${stamp}`);
    await dialog.getByRole('button', { name: 'Create process model' }).click();
    await expect(dialog.getByRole('alert')).toContainText('failed: 500');
    checks.push('create model: error shown');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

    const menu = await openRowMenu(page, M.draft.name);
    await menu.getByRole('menuitem', { name: 'Delete', exact: true }).click();
    const confirm = page.getByRole('alertdialog', { name: 'Delete process model?' });
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(confirm.getByRole('alert')).toContainText('failed: 500');
    checks.push('delete model: error shown');
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(modelRow(page, M.draft.name)).toBeVisible();

    const groups = await apiList<GroupItem>(page, '/v1.0/m8flow/process-groups');
    expect(groups.find((g) => g.id === active.groupId)?.display_name).toBe(active.groupName);
    expect(groups.some((g) => g.display_name === `E2E Fail ${stamp}`)).toBe(false);

    logResult('PRC-46', {
      scenario: 'The server fails (mocked 500) for group and model changes',
      actions: ['Create group', 'Rename group', 'Delete group', 'Create model', 'Delete model'],
      expected: 'Each form shows an error and stays open; nothing is created, renamed or deleted',
      actual: `${checks.join('; ')}; server data unchanged`,
      messages: [reason, 'POST /v1.0/m8flow/process-models failed: 500'],
    });
  });

  test('PRC-47: Nested process groups (parent/child) can be created and used; broken paths are refused', async ({
    page,
  }) => {
    const parent = { id: `e2e-parent-${stamp}`, name: `E2E Parent ${stamp}` };
    const child = { id: `${parent.id}/child`, name: `E2E Child ${stamp}` };
    const model = { id: `e2e-nested-model-${stamp}`, name: `E2E Nested Model ${stamp}` };
    created.groups.push(child.id, parent.id);
    created.models.push(`${parent.id}:child:${model.id}`);

    const newGroup = async (name: string, id: string) => {
      await page.goto('/processes');
      await page.getByTestId('processes-new-group-button').click();
      const form = page.getByRole('dialog', { name: 'New process group' });
      await form.getByLabel('Process group display name').fill(name);
      await form.getByLabel('Process group id').fill(id);
      await form.getByRole('button', { name: 'Create group' }).click();
      return form;
    };

    await newGroup(parent.name, parent.id);
    await expect(page.getByRole('button', { name: parent.name, exact: true }).first()).toBeVisible();
    await newGroup(child.name, child.id);
    await expect(page.getByRole('button', { name: child.name, exact: true }).first()).toBeVisible();
    expect(decodeURIComponent(page.url())).toContain(`group=${child.id}`);

    await page.getByRole('button', { name: 'New process model', exact: true }).last().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await expect(dialog.getByRole('combobox', { name: 'Process group' })).toContainText(child.name);
    await dialog.getByLabel('Display name').fill(model.name);
    await dialog.getByLabel('Identifier').fill(model.id);
    await dialog.getByRole('button', { name: 'Create process model' }).click();
    await expect(page).toHaveURL(urlPathEndsWith(`/processes/${parent.id}:child:${model.id}`));
    await expect(page.getByText(`${child.id}/${model.id}`, { exact: true })).toBeVisible();

    const invalid = 'Invalid process group identifier';
    for (const bad of [`${parent.id}//child2`, `${parent.id}/-bad`]) {
      const form = await newGroup('E2E Broken Path', bad);
      await expect(form.getByRole('alert')).toHaveText(invalid);
    }

    logResult('PRC-47', {
      scenario: 'Nested process groups',
      actions: [`Create "${parent.id}"`, `Create "${child.id}"`, 'Create a model in the child group', 'Ids with an empty or invalid part'],
      expected: 'Child group created and selected; model created under parent/child; broken paths refused',
      actual: `Model "${child.id}/${model.id}" created; "//" and "/-bad" refused`,
      messages: [invalid],
    });
  });

  test('PRC-48: Clicking anywhere on a row opens the process model', async ({ page }) => {
    await page.goto(groupPage);
    await modelRow(page, M.live.name).getByText(M.live.name, { exact: true }).click();
    await expect(page).toHaveURL(urlPathHas(`/processes/${route(M.live)}`));
    await expect(page.getByRole('heading', { name: M.live.name, exact: true })).toBeVisible();

    await page.goto(groupPage);
    await modelRow(page, M.draft.name).getByRole('cell').nth(2).click();
    await expect(page.getByRole('heading', { name: M.draft.name, exact: true })).toBeVisible();

    logResult('PRC-48', {
      scenario: 'Open a model by clicking its row',
      actions: ['Click the model name', 'Click the Runs 30d cell of another row'],
      expected: 'Both clicks open the model page',
      actual: `"${M.live.name}" and "${M.draft.name}" opened from their rows`,
    });
  });

  // ---------------- Roles ----------------

  test('PRC-24: A submitter cannot create or manage process models', async ({ page }) => {
    await useSession(page, submitterCredentials());
    await page.goto(groupPage);
    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toBeVisible();
    await expect(page.getByText('Loading process models…')).toHaveCount(0);
    await expect(page.getByTestId('processes-new-group-button')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'New process model', exact: true })).toHaveCount(0);

    let menuNote = 'no rows visible to the submitter';
    if (await modelRow(page, M.live.name).isVisible()) {
      const labels = await menuItemLabels(await openRowMenu(page, M.live.name));
      for (const forbidden of ['Delete', 'Pause', 'Unpublish', 'Publish']) {
        expect(labels).not.toContain(forbidden);
      }
      menuNote = `row menu offers only: ${labels.join(', ')}`;
      await closeMenu(page);
    }

    logResult('PRC-24', {
      scenario: 'Submitter opens the Processes page',
      actions: ['Log in as Submitter', 'Open the mock group', 'Open a row menu'],
      expected: 'No New process group / New process model buttons; no Delete or status actions',
      actual: `Create buttons hidden; ${menuNote}`,
    });
  });
});
