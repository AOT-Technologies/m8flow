import type { Browser, Page, TestType } from '@playwright/test';

import { editorCredentials, tenantAdminCredentials, useSession } from './auth';
import { backendFetch } from './backendApi';
import { seedBaselineOnce } from '../seed/seed';
import { modelFromSeededTemplate } from './seedCatalog';

/**
 * Groups, models and instances that a spec creates for itself (API helpers).
 *
 * Tests must not depend on, or change, the process groups/models that happen
 * to exist on an instance. Each spec creates the group/models it needs through
 * the backend API (models with files come from the seeded catalog templates,
 * helpers/seedCatalog.ts), works only on that, and deletes it afterwards.
 */

/** Description of every group and model a test creates (the seeded catalog has its own). */
export const E2E_DESCRIPTION = 'E2E mock data -- safe to delete';

function groupPath(groupId: string): string {
  return `/v1.0/m8flow/process-groups/${groupId.split('/').map(encodeURIComponent).join(':')}`;
}

function modelPath(routeId: string): string {
  return `/v1.0/m8flow/process-models/${routeId.split(':').map(encodeURIComponent).join(':')}`;
}

function ok(status: number, allowed: number[]): boolean {
  return (status >= 200 && status < 300) || allowed.includes(status);
}

export async function createMockGroup(
  page: Page,
  group: { id: string; display_name: string; description?: string },
): Promise<void> {
  const result = await backendFetch(page, '/v1.0/m8flow/process-groups', {
    method: 'POST',
    data: { description: E2E_DESCRIPTION, ...group },
  });
  if (!ok(result.status, [409])) {
    throw new Error(`createMockGroup(${group.id}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/** Creates a model and returns its route id (`group:model`). */
export async function createMockModel(
  page: Page,
  model: { group_id: string; id: string; display_name: string; description?: string },
): Promise<string> {
  const result = await backendFetch(page, '/v1.0/m8flow/process-models', {
    method: 'POST',
    data: { description: E2E_DESCRIPTION, ...model },
  });
  if (!ok(result.status, [409])) {
    throw new Error(`createMockModel(${model.id}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  return `${model.group_id.split('/').join(':')}:${model.id}`;
}

export async function setPrimaryFile(page: Page, routeId: string, fileName: string): Promise<void> {
  const result = await backendFetch(page, modelPath(routeId), {
    method: 'PUT',
    data: { primary_file_name: fileName },
  });
  if (!ok(result.status, [])) {
    throw new Error(`setPrimaryFile(${routeId}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/**
 * Every instance of a model, found through the instance list (paged), plus
 * the model's recent instances. Use a tenant admin page: since M8F-627 other
 * roles only see instances they started or have a task in.
 */
export async function listModelInstanceIds(page: Page, routeId: string): Promise<number[]> {
  const modelId = routeId.split(':').join('/');
  const ids = new Set<number>();
  for (let pageNo = 1; pageNo <= 50; pageNo += 1) {
    const result = await backendFetch(
      page,
      `/v1.0/m8flow/process-instances?search=${encodeURIComponent(modelId)}&per_page=100&page=${pageNo}`,
    ).catch(() => null);
    if (!result || result.status !== 200) break;
    const body = result.body as { results?: { id: number; process_model_identifier?: string }[]; pagination?: { pages?: number } };
    for (const row of body.results ?? []) {
      if (row.process_model_identifier === modelId) ids.add(row.id);
    }
    if (!body.results?.length || pageNo >= (body.pagination?.pages ?? 1)) break;
  }
  const detail = await backendFetch(page, modelPath(routeId)).catch(() => null);
  if (detail && detail.status === 200) {
    for (const row of (detail.body as { recent_instances?: { id: number }[] }).recent_instances ?? []) ids.add(row.id);
  }
  return [...ids];
}

/**
 * Removes a test model completely: deletes all its instances (terminating
 * running ones first), unpublishes it (back to Draft), then deletes it.
 * The server refuses to delete a model that still has instances (409), so
 * anything left is logged with the reason. Returns true when the model is gone.
 * Best effort: never fails a test.
 */
export async function removeMockModelCompletely(page: Page, routeId: string, extraIds: number[] = []): Promise<boolean> {
  await deleteInstanceIds(page, [...extraIds, ...(await listModelInstanceIds(page, routeId))]);
  await backendFetch(page, modelPath(routeId), { method: 'PUT', data: { status: 'draft' } }).catch(() => null);
  const result = await backendFetch(page, modelPath(routeId), { method: 'DELETE' }).catch(() => null);
  if (result && ok(result.status, [404])) return true;
  console.warn(`[cleanup] model ${routeId} not deleted: ${result?.status ?? 'no answer'} ${JSON.stringify(result?.body ?? '').slice(0, 200)}`);
  return false;
}

/**
 * Cleanup of a test model, used by every spec: deletes the instances this
 * page's user can see, unpublishes the model and deletes it (see
 * removeMockModelCompletely). Best effort: a problem is logged, never fails a test.
 */
export async function deleteMockModel(page: Page, routeId: string): Promise<void> {
  await removeMockModelCompletely(page, routeId);
}

/** Best effort: a cleanup problem is logged, never fails a test. */
export async function deleteMockGroup(page: Page, groupId: string): Promise<void> {
  const result = await backendFetch(page, groupPath(groupId), { method: 'DELETE' }).catch(() => null);
  if (result && !ok(result.status, [404])) {
    console.warn(`[cleanup] delete mock group ${groupId} skipped: ${result.status} ${JSON.stringify(result.body ?? '').slice(0, 200)}`);
  }
}

export type MockModelStatus = 'draft' | 'published' | 'paused';

/** Moves a model through its lifecycle (new models start as draft). */
export async function setModelStatus(page: Page, routeId: string, status: MockModelStatus): Promise<void> {
  const result = await backendFetch(page, modelPath(routeId), { method: 'PUT', data: { status } });
  if (!ok(result.status, [])) {
    throw new Error(`setModelStatus(${routeId}, ${status}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/** Starts an instance of a published model and returns its id. */
export async function startMockInstance(page: Page, routeId: string): Promise<number> {
  const result = await backendFetch(page, `${modelPath(routeId)}/start`, { method: 'POST' });
  if (!ok(result.status, [])) {
    throw new Error(`startMockInstance(${routeId}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  return (result.body as { id: number }).id;
}

/**
 * Best effort: terminates and deletes the given instances plus every recent
 * instance of the model, so the model itself can then be deleted.
 */
/** Terminates and deletes the instances listed on a model, plus any extra ids. */
export async function deleteMockInstances(page: Page, routeId: string, extraIds: number[] = []): Promise<void> {
  const ids = new Set(extraIds);
  const detail = await backendFetch(page, modelPath(routeId)).catch(() => null);
  if (detail && detail.status === 200) {
    for (const row of (detail.body as { recent_instances?: { id: number }[] }).recent_instances ?? []) {
      ids.add(row.id);
    }
  }
  await deleteInstanceIds(page, [...ids]);
}

/** Terminates and deletes instances by id. Best effort: problems are logged. */
export async function deleteInstanceIds(page: Page, ids: number[]): Promise<void> {
  for (const id of new Set(ids)) {
    await backendFetch(page, `/v1.0/m8flow/process-instances/${id}/terminate`, { method: 'POST' }).catch(() => null);
    const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`, { method: 'DELETE' }).catch(() => null);
    if (result && !ok(result.status, [404])) {
      console.warn(`[cleanup] delete mock instance ${id} skipped: ${result.status}`);
    }
  }
}

/** Best effort: a cleanup problem is logged, never fails a test. */
export async function deleteMockTemplate(page: Page, templateId: number): Promise<void> {
  const result = await backendFetch(page, `/v1.0/m8flow/templates/${templateId}`, { method: 'DELETE' }).catch(() => null);
  if (result && !ok(result.status, [404])) {
    console.warn(`[cleanup] delete mock template ${templateId} skipped: ${result.status}`);
  }
}

/**
 * The shared "E2E Mock Catalog" / "E2E Mock Model" that the Modeler specs used
 * before the seeded catalog (M8F-677). The seed removes it from older stacks.
 */
const LEGACY_MOCK_GROUP_ID = 'e2e-mock-catalog';

/** Rows of a list answer: a plain array, or a paginated { results: [...] } body. */
export function listRows<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[];
  const results = (body as { results?: unknown } | null)?.results;
  return Array.isArray(results) ? (results as T[]) : [];
}

export async function removeLegacyMockCatalog(page: Page): Promise<void> {
  const list = await backendFetch(page, `/v1.0/m8flow/process-models?group=${LEGACY_MOCK_GROUP_ID}`).catch(() => null);
  if (!list || list.status !== 200) return;
  for (const m of listRows<{ id: string }>(list.body)) await removeMockModelCompletely(page, m.id.replace(/\//g, ':'));
  await deleteMockGroup(page, LEGACY_MOCK_GROUP_ID);
}

// ---------------------------------------------------------------------------
// Leftovers from interrupted runs
// Every spec deletes its own data in afterAll, but a run that is stopped
// (Ctrl+C, the stack going down, a crashed worker) never gets there. The
// baseline seed (seed/seed.ts) deletes E2E data that earlier runs left behind
// (once per worker process; the suite runs one worker, so once per run):
// process groups (with their models and instances) and templates whose id
// starts with "e2e-" and carries a run time stamp older than
// E2E_LEFTOVER_MAX_AGE_MIN minutes (default 120). Old copies inside the seeded
// catalog are removed the same way (helpers/seedCatalog.ts). Recent data and
// data without a time stamp (the seeded catalog itself) are never touched, so
// another run that is still going on the same server is safe. Best effort:
// problems are logged, never fail a test.
// ---------------------------------------------------------------------------

const OLDEST_STAMP_MS = Date.UTC(2024, 0, 1);

/**
 * Run stamp for E2E ids: the time in base 36 (8 characters) and 3 random digits.
 * The digits make it tell apart from a word (e2eStampTime relies on that).
 */
export function newStamp(): string {
  return `${Date.now().toString(36)}${String(Math.floor(Math.random() * 1000)).padStart(3, '0')}`;
}

/** Run time encoded in an e2e id (base-36 or decimal Date.now()), or undefined. */
export function e2eStampTime(id: string): number | undefined {
  if (!/^e2e-/i.test(id)) return undefined;
  const tokens = id.toLowerCase().split(/[-/:_]/);
  for (const [index, token] of tokens.entries()) {
    let ms: number | undefined;
    if (/^\d{13}$/.test(token)) ms = Number(token);
    // Base-36 stamps mix letters and digits; plain words (e.g. "approval") are skipped.
    else if (/^[0-9a-z]{8,12}$/.test(token) && /[a-z]/.test(token) && /\d/.test(token)) ms = parseInt(token.slice(0, 8), 36);
    // Older stamps could be letters only ("mwbxmrahexu"): accepted only as the id's last
    // part and in the two stamp lengths (8, or 8 + 3), so a word inside an id is not read as one.
    else if (index === tokens.length - 1 && index > 1 && /^[a-z]{8}([a-z]{3})?$/.test(token)) ms = parseInt(token.slice(0, 8), 36);
    if (ms !== undefined && ms >= OLDEST_STAMP_MS && ms <= Date.now() + 86_400_000) return ms;
  }
  return undefined;
}

/** Age limit for leftovers: E2E_LEFTOVER_MAX_AGE_MIN minutes (default 120). */
export function leftoverMaxAgeMin(): number {
  return Number(process.env.E2E_LEFTOVER_MAX_AGE_MIN ?? 120);
}

function isOldE2eId(id: string, maxAgeMin: number): boolean {
  // Ids without a time stamp (e.g. the seed catalog group) are never old.
  const stamp = e2eStampTime(id);
  return stamp !== undefined && Date.now() - stamp > maxAgeMin * 60_000;
}

export type E2eDataRemoved = { groups: number; models: number; templates: number };

/**
 * Deletes E2E groups (with their models and instances) and templates whose id carries a
 * run time stamp older than `maxAgeMin` minutes (0 = every stamped one). Seeded data has no
 * stamp and is never touched. Errors are thrown; sweepLeftoverE2eData only logs them.
 */
export async function removeStampedE2eData(page: Page, maxAgeMin: number): Promise<E2eDataRemoved> {
  const groups = await backendFetch(page, '/v1.0/m8flow/process-groups');
  if (groups.status !== 200) throw new Error(`listing process groups failed: ${groups.status}`);
  const groupIds = listRows<{ id: string }>(groups.body)
    .map((g) => g.id)
    .filter((id) => isOldE2eId(id.split('/')[0], maxAgeMin));
  // Children first, so a parent group is empty when it is deleted.
  groupIds.sort((a, b) => b.split('/').length - a.split('/').length);
  let models = 0;
  for (const groupId of groupIds) {
    const list = await backendFetch(page, `/v1.0/m8flow/process-models?group=${encodeURIComponent(groupId)}`);
    for (const m of list.status === 200 ? listRows<{ id: string }>(list.body) : []) {
      if (await removeMockModelCompletely(page, m.id.replace(/\//g, ':'))) models += 1;
    }
    await deleteMockGroup(page, groupId);
  }
  const templates = await backendFetch(page, '/v1.0/m8flow/templates?per_page=200');
  if (templates.status !== 200) throw new Error(`listing templates failed: ${templates.status}`);
  const oldTemplates = listRows<{ id: number; templateKey?: string }>(templates.body).filter((t) => isOldE2eId(t.templateKey ?? '', maxAgeMin));
  for (const t of oldTemplates) await deleteMockTemplate(page, t.id);
  return { groups: groupIds.length, models, templates: oldTemplates.length };
}

/** Deletes old E2E groups, models, instances and templates left by stopped runs. */
export async function sweepLeftoverE2eData(page: Page): Promise<void> {
  try {
    const removed = await removeStampedE2eData(page, leftoverMaxAgeMin());
    if (removed.groups || removed.templates) {
      console.log(`[cleanup] Removed leftovers of earlier runs: ${removed.groups} group(s), ${removed.models} model(s), ${removed.templates} template(s).`);
    }
  } catch (error) {
    console.warn(`[cleanup] leftover sweep skipped: ${String(error).slice(0, 200)}`);
  }
}

let leftoversSwept = false;

/**
 * Runs sweepLeftoverE2eData at most once per worker process (module-level flag),
 * from the baseline seed. With the suite's single worker that is once per run;
 * with more workers each one would sweep once, before its first spec.
 */
export async function sweepLeftoversOnce(page: Page): Promise<void> {
  if (leftoversSwept) return;
  leftoversSwept = true;
  // Tenant admin: since M8F-627 only the starter or a tenant admin may delete
  // an instance, and leftovers were started by several users.
  const browser = page.context().browser();
  if (!browser) {
    await sweepLeftoverE2eData(page);
    return;
  }
  const admin = await browser.newPage();
  try {
    await useSession(admin, tenantAdminCredentials());
    await sweepLeftoverE2eData(admin);
  } catch (error) {
    console.warn(`[cleanup] leftover sweep skipped: ${String(error).slice(0, 200)}`);
  } finally {
    await admin.close();
  }
}

export async function withAdminPage(browser: Browser, action: (page: Page) => Promise<void>): Promise<void> {
  const page = await browser.newPage();
  try {
    await useSession(page, tenantAdminCredentials());
    await action(page);
  } finally {
    await page.close();
  }
}

export async function withEditorPage(browser: Browser, action: (page: Page) => Promise<void>): Promise<void> {
  const page = await browser.newPage();
  try {
    await useSession(page, editorCredentials());
    await action(page);
  } finally {
    await page.close();
  }
}

export type ActiveCatalogModel = {
  id: string;
  name: string;
  status: MockModelStatus;
  /**
   * Create the model from a seeded catalog template (its files; the template is not changed):
   * true = the work-from-home template, a string = that template key. false = an empty model.
   */
  files: boolean | string;
  /** Start one process instance (the model must be published). */
  instance: boolean;
};

/** Everything a spec creates on top of the catalog, so afterAll can remove it. */
export type ActiveCatalogTracker = {
  instances: number[];
  models: string[];
  groups: string[];
  templates: number[];
};

/**
 * A tenant with data: call once at the top of a spec file. Before the file's
 * tests it creates one group with the given models (from seeded catalog
 * templates, or empty; status and an optional running instance); after them it removes those models, anything
 * recorded in the returned tracker, and the group.
 */
export function useActiveCatalog(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  test: TestType<any, any>,
  group: { id: string; name: string },
  models: ActiveCatalogModel[],
): ActiveCatalogTracker {
  const tracker: ActiveCatalogTracker = { instances: [], models: [], groups: [], templates: [] };
  const route = (m: { id: string }) => `${group.id}:${m.id}`;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(480_000);
    await seedBaselineOnce(browser);
    await withEditorPage(browser, async (page) => {
      await createMockGroup(page, { id: group.id, display_name: group.name });
      for (const m of models) {
        if (m.files) {
          const template = typeof m.files === 'string' ? m.files : 'work-from-home';
          await modelFromSeededTemplate(page, template, { groupId: group.id, id: m.id, name: m.name, publish: false });
        } else {
          await createMockModel(page, { group_id: group.id, id: m.id, display_name: m.name });
        }
        if (m.status !== 'draft') await setModelStatus(page, route(m), 'published');
        if (m.status === 'paused') await setModelStatus(page, route(m), 'paused');
        if (m.instance) tracker.instances.push(await startMockInstance(page, route(m)));
      }
    });
  });

  test.afterAll(async ({ browser }) => {
    test.setTimeout(300_000);
    // Tenant admin: since M8F-627 only the starter or a tenant admin may delete
    // an instance. Each model loses all its instances, is unpublished, then deleted.
    await withAdminPage(browser, async (page) => {
      await deleteInstanceIds(page, tracker.instances);
      for (const r of [...models.map(route), ...tracker.models]) await removeMockModelCompletely(page, r);
      for (const id of tracker.templates) await deleteMockTemplate(page, id);
      for (const g of [...tracker.groups, group.id]) await deleteMockGroup(page, g);
    });
  });

  return tracker;
}
