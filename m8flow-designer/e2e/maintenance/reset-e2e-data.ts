import { expect, test, type Page } from '@playwright/test';

import { tenantAdminCredentials, useSession } from '../helpers/auth';
import { backendFetch } from '../helpers/backendApi';
import { deleteMockTemplate, e2eStampTime, listRows, removeLegacyMockCatalog, removeStampedE2eData } from '../helpers/mockCatalog';
import { catalogGroup, seededTemplateId, sweepCatalogLeftovers, templateKey } from '../helpers/seedCatalog';
import { loadBaseline } from '../seed/seed';

/**
 * E2E reset: puts the stack back to the seeded baseline.
 *
 *   npx playwright test -c e2e/maintenance/reset.config.ts
 *
 * Removes, as the tenant admin:
 *   - every E2E group, model, instance and template whose id carries a run time stamp
 *     (data of earlier or stopped runs, whatever its age),
 *   - the old mock catalog group (before M8F-677),
 *   - every instance of the seeded catalog models, and stamped copies of them,
 *   - catalog templates no longer in baseline.json (e2e-<key> without a time stamp, e.g. after
 *     templates were merged).
 * Keeps the seeded baseline: users, tenants, catalog templates and catalog models.
 *
 * Do not run it while a test run is going on the same stack: it would remove that run's data.
 * It is never part of the suite (its own config, not a *.spec.ts file).
 */
test('Reset: remove E2E run data and keep the seeded baseline', async ({ page }) => {
  test.setTimeout(15 * 60_000);
  await useSession(page, tenantAdminCredentials());

  const removed = await removeStampedE2eData(page, 0);
  await removeLegacyMockCatalog(page);
  const catalog = await sweepCatalogLeftovers(page, 0);
  const retired = await removeRetiredCatalogTemplates(page);
  console.log(
    `Removed ${removed.groups} group(s), ${removed.models} model(s), ${removed.templates} template(s), ` +
      `${catalog.instances} catalog instance(s), ${catalog.copies} catalog copy(ies) and ` +
      `${retired.length} retired catalog template(s)${retired.length ? ` (${retired.join(', ')})` : ''}.`,
  );

  // A second pass finds nothing: the stack is clean.
  const again = await removeStampedE2eData(page, 0);
  const againCatalog = await sweepCatalogLeftovers(page, 0);
  const againRetired = (await removeRetiredCatalogTemplates(page)).length;
  expect({ ...again, ...againCatalog, retired: againRetired }, 'nothing is left after the reset').toEqual({
    groups: 0,
    models: 0,
    templates: 0,
    copies: 0,
    instances: 0,
    retired: 0,
  });

  // The seeded baseline is still there.
  const baseline = loadBaseline();
  const group = catalogGroup();
  for (const model of baseline.catalog.models) {
    const detail = await backendFetch(page, `/v1.0/m8flow/process-models/${encodeURIComponent(group.id)}:${encodeURIComponent(model.id)}`);
    expect(detail.status, `seeded model ${model.id} is kept`).toBe(200);
  }
  for (const template of baseline.catalog.templates ?? []) await seededTemplateId(page, template.key);
  console.log(`Seeded baseline kept: ${baseline.catalog.models.length} model(s), ${(baseline.catalog.templates ?? []).length} template(s).`);
});

/** Deletes e2e-<key> catalog templates (no run stamp) whose key is no longer in baseline.json. */
async function removeRetiredCatalogTemplates(page: Page): Promise<string[]> {
  const current = new Set((loadBaseline().catalog.templates ?? []).map((t) => templateKey(t.key)));
  const list = await backendFetch(page, '/v1.0/m8flow/templates?per_page=200');
  expect(list.status, 'GET /templates').toBe(200);
  const retired = listRows<{ id: number; templateKey?: string }>(list.body).filter((t) => {
    const key = t.templateKey ?? '';
    return key.startsWith('e2e-') && e2eStampTime(key) === undefined && !current.has(key);
  });
  for (const t of retired) await deleteMockTemplate(page, t.id);
  return [...new Set(retired.map((t) => t.templateKey ?? ''))];
}
