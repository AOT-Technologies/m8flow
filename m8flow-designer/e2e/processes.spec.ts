import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  selectSidebarTenant,
  signInAsPlatformAdmin,
  signInAsSharedRealmUser,
  superAdminCredentials,
} from './helpers/auth';
import {
  SEED_GROUP_NAME,
  SEED_MODEL_DETAIL_PATH,
  SEED_MODEL_NAME,
  SEED_TENANT_LABEL,
} from './helpers/fixtures';

/**
 * CHK-01..05, CHK-10 — Processes list and Process Model Detail journeys
 * through the live designer → backend → Keycloak seam. Fixture data is
 * real seed data confirmed live against the dev stack — see
 * .e2e-agent/research.md. Originally one process group/model
 * (`test-process-group`/`wfh-approval.bpmn`); a second group/model
 * (`element-coverage-sample`/`all-elements-sample.bpmn`) was added later
 * as a styling-verification fixture for the process-modeler-visual-
 * fidelity map — CHK-01/CHK-03's own group/model counts were updated to
 * match (2, not 1) when that addition broke them.
 */
test.describe('m8flow-designer Processes catalog', () => {
  test('CHK-01: editor sees the tenant-scoped process catalog', async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());

    await page.goto('/processes');

    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toBeVisible();
    // 2, not 1: the process-modeler-visual-fidelity map's own coverage
    // fixture (`element-coverage-sample:all-elements-sample`, seeded
    // alongside `wfh-approval.bpmn` under the same tenant) is real,
    // visible seed data now too — confirmed live via the actual page text
    // (not assumed) when this count broke after adding it.
    await expect(page.getByText('2 models', { exact: true }).first()).toBeVisible();
    const row = page.getByRole('button').filter({ hasText: SEED_MODEL_NAME });
    await expect(row).toBeVisible();
    await expect(row).toContainText(SEED_GROUP_NAME);
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  test('CHK-02: search narrows the list and reports the empty state for no match', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto('/processes');

    const search = page.getByRole('searchbox', { name: 'Search process models' });
    await expect(page.getByRole('button').filter({ hasText: SEED_MODEL_NAME })).toBeVisible();

    await search.fill('no-such-process-model-xyz');
    await expect(page.getByText('No process models', { exact: true })).toBeVisible();
    await expect(page.getByText('Try a different search')).toBeVisible();
    await expect(page.getByRole('button').filter({ hasText: SEED_MODEL_NAME })).toHaveCount(0);

    await search.fill('');
    await expect(page.getByRole('button').filter({ hasText: SEED_MODEL_NAME })).toBeVisible();
  });

  test('CHK-03: Browse groups filters Processes by group and Clear resets it', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto('/processes');

    await page.getByRole('button', { name: 'Browse groups', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Process groups' });
    await expect(dialog).toBeVisible();
    // 2, not 1 — same coverage-fixture seed group as CHK-01's model-count
    // update above.
    await expect(dialog.getByText(`2 groups in this tenant`)).toBeVisible();

    await dialog.getByText(SEED_GROUP_NAME, { exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(/[?&]group=test-process-group/);
    // exact: true, not a substring match — a model row's own accessible
    // name concatenates its cells (model name + group name + ...), so a
    // non-exact match against just the group name collides with any row
    // whose group happens to be this one (observed live: this model's own
    // row surfaced as a second match once enough sibling fixture files
    // accumulated in the shared seed model to shift its rendered content —
    // see seedFixture.ts's own note that file count only grows, never
    // shrinks, across this repo's e2e phases).
    await expect(page.getByRole('button', { name: SEED_GROUP_NAME, exact: true })).toBeVisible();
    await expect(page.getByRole('button').filter({ hasText: SEED_MODEL_NAME })).toBeVisible();

    await page.getByRole('button', { name: 'Clear', exact: true }).click();
    await expect(page).not.toHaveURL(/[?&]group=/);
    await expect(page.getByRole('button', { name: 'All groups' })).toBeVisible();
  });

  test('CHK-04: opening a process model navigates to its overview with real detail data', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto('/processes');

    await page.getByRole('button').filter({ hasText: SEED_MODEL_NAME }).click();

    await expect(page).toHaveURL(new RegExp(SEED_MODEL_DETAIL_PATH.replace(/:/g, '%3A|:')));
    await expect(page.getByRole('heading', { name: SEED_MODEL_NAME, exact: true })).toBeVisible();
    // At least 6, not exactly 6: the Task Configuration Parity plan's later
    // phases (modeler-business-rule-task.spec.ts onward) seed their own
    // fixture files into this same shared model via seedProcessModelFile
    // (there's no delete-file route for process models to clean up after —
    // only templates have one), so this model's real file count only grows
    // over time. The "real data, not a mock" intent this assertion protects
    // doesn't depend on the exact number, just that it's a real, plausible
    // one — hardcoding "6" here is what actually broke (CHK-04 started
    // failing the moment Phase 2's spec ran once against a live stack).
    const filesHeading = await page.getByText(/^Files \(\d+\)$/).textContent();
    const fileCount = Number(filesHeading?.match(/\((\d+)\)/)?.[1] ?? 0);
    expect(fileCount).toBeGreaterThanOrEqual(6);
    await expect(page.getByText('wfh-approval.bpmn', { exact: true })).toBeVisible();
    await expect(page.getByText('Primary', { exact: true })).toBeVisible();
    await expect(page.getByText('submitter', { exact: true })).toBeVisible();
    await expect(page.getByText('Complete', { exact: true })).toBeVisible();
  });

  test('CHK-05: Process Model Detail reports not-found for an unknown model id', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());

    await page.goto('/processes/does-not-exist:nope');

    await expect(page.getByText('Process model not found.', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  test('CHK-10: super-admin is tenant-gated on Processes and Detail until a tenant is picked', async ({
    page,
  }) => {
    await signInAsPlatformAdmin(page, superAdminCredentials());

    await page.goto('/processes');
    await expect(page.getByText('Choose a tenant', { exact: true })).toBeVisible();
    await expect(
      page.getByText('Process models are tenant-scoped. Select a concrete tenant'),
    ).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);

    await page.goto('/processes/does-not-exist:nope');
    await expect(page.getByText('Choose a tenant', { exact: true })).toBeVisible();

    await selectSidebarTenant(page, SEED_TENANT_LABEL);
    await page.goto('/processes');
    await expect(page.getByRole('button').filter({ hasText: SEED_MODEL_NAME })).toBeVisible();
    await expect(page.getByText('Choose a tenant')).toHaveCount(0);
  });
});
