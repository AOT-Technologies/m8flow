import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';

import type { Page, TestType } from '@playwright/test';

import { backendFetch } from './backendApi';
import {
  createMockGroup,
  createMockModel,
  deleteInstanceIds,
  E2E_DESCRIPTION,
  e2eStampTime,
  leftoverMaxAgeMin,
  listRows,
  listModelInstanceIds,
  newStamp,
  removeMockModelCompletely,
  setModelStatus,
  setPrimaryFile,
  withAdminPage,
  withEditorPage,
} from './mockCatalog';
import { postMultipart, zipFiles } from './processFlow';
import { deleteProcessModelFile, readProcessModelFile, seedProcessModelFile } from './seedFixture';
import { loadBaseline, seedBaselineOnce, type CatalogModel } from '../seed/seed';

/**
 * Seeded process catalog (M8F-677).
 *
 * The baseline seed keeps the group, templates and models listed under
 * "catalog" in seed/baseline.json. Every process is a template with its own
 * folder seed/catalog/templates/<key>/; the model made from it uses that folder
 * (a model without a template would use seed/catalog/<model id>/). Each folder holds the diagram and
 * its supporting files (forms, decision tables) plus paths.json (the routes
 * through the process, not uploaded). Tests never change
 * them: a spec copies a seeded model (useSeededModelCopy), works on the copy
 * and deletes it afterwards. A copy left by a stopped run carries a time
 * stamp in its id, so the leftover sweep removes it later.
 */

const SEED_DESCRIPTION = 'E2E seed catalog: fixed test data that the tests copy. Safe to delete; the next run re-creates it.';

export function catalogGroup(): { id: string; name: string } {
  return loadBaseline().catalog.group;
}

function catalogModel(id: string): CatalogModel {
  const model = loadBaseline().catalog.models.find((m) => m.id === id);
  if (!model) throw new Error(`[seed catalog] baseline.json has no catalog model "${id}"`);
  return model;
}

/** Folder of a seeded model: its template's folder, or its own. */
export function catalogFolder(modelId: string): URL {
  const model = loadBaseline().catalog.models.find((m) => m.id === modelId);
  return model?.template ? templateFolder(model.template) : new URL(`../seed/catalog/${modelId}/`, import.meta.url);
}

function templateFolder(key: string): URL {
  return new URL(`../seed/catalog/templates/${key}/`, import.meta.url);
}

/** Not uploaded: the routes through the process (read by the tests and the validate script). */
const NOT_UPLOADED = new Set(['paths.json']);

function folderFiles(folder: URL): string[] {
  const isDiagram = (name: string) => name.toLowerCase().endsWith('.bpmn');
  return readdirSync(folder)
    .filter((name) => !name.startsWith('.') && !NOT_UPLOADED.has(name) && statSync(new URL(name, folder)).isFile())
    .sort((a, b) => Number(isDiagram(a)) - Number(isDiagram(b)) || a.localeCompare(b));
}

/**
 * Files of a seeded model: everything in seed/catalog/<model id>/. Diagrams
 * come last, so the decision tables and forms they point at already exist.
 */
export function catalogFiles(modelId: string): string[] {
  return folderFiles(catalogFolder(modelId));
}

/** Routes through a seeded model (its folder's paths.json), or none. */
export function catalogPaths(modelId: string): CatalogPath[] {
  const file = new URL('paths.json', catalogFolder(modelId));
  if (!existsSync(file)) return [];
  return (JSON.parse(readFileSync(file, 'utf-8')) as { paths: CatalogPath[] }).paths;
}

/**
 * Name -> BPMN id of the human tasks in a seeded model's primary diagram, and in
 * the diagrams its call activities run (other catalog templates, by process id).
 */
export function humanTaskIds(modelId: string): Map<string, string> {
  const xml = catalogFile(modelId, catalogModel(modelId).primary);
  const ids = new Map<string, string>();
  const add = (diagram: string) => {
    for (const m of diagram.matchAll(/<bpmn:(?:userTask|manualTask|task) id="([^"]+)"(?: name="([^"]+)")?/g)) {
      ids.set(m[1], m[1]);
      if (m[2]) ids.set(m[2].replace(/&amp;/g, '&').replace(/&quot;/g, '"'), m[1]);
    }
  };
  add(xml);
  for (const called of new Set([...xml.matchAll(/calledElement="([^"]+)"/g)].map((m) => m[1]))) {
    for (const template of loadBaseline().catalog.templates ?? []) {
      const diagram = templateFile(template.key, templatePrimary(template.key));
      if (diagram.includes(`<bpmn:process id="${called}"`)) add(diagram);
    }
  }
  return ids;
}

/** Every element drawn in a seeded model's primary diagram (BPMNShape / BPMNEdge bpmnElement ids). */
export function catalogDiagramIds(modelId: string): string[] {
  const xml = catalogFile(modelId, catalogModel(modelId).primary);
  return [...new Set([...xml.matchAll(/<bpmndi:BPMN(?:Shape|Edge) id="[^"]+" bpmnElement="([^"]+)"/g)].map((m) => m[1]))];
}

/** One route through a seeded process (see the $comment in any paths.json). */
export type CatalogPath = {
  id: string;
  title: string;
  answers: Record<string, Record<string, unknown> | Record<string, unknown>[]>;
  leave?: string[];
  expect?: 'complete' | 'service_error';
  failing_submit?: string;
  expect_tasks?: string[];
  expect_end?: string[];
  expect_completed?: string[];
  expect_not_reached?: string[];
  expect_data?: { at: string; values: Record<string, unknown>; absent?: string[] };
};

function catalogFile(modelId: string, name: string): string {
  return readFileSync(new URL(name, catalogFolder(modelId)), 'utf-8');
}

// ---------------------------------------------------------------------------
// Templates and the connector profile
// ---------------------------------------------------------------------------

type TemplateRow = { id: number; templateKey: string; tags?: string[] | null };

export function templateKey(key: string): string {
  return `e2e-${key}`;
}

/** A file of a catalog template folder (seed/catalog/templates/<key>/<name>). */
export function templateFile(key: string, name: string): string {
  return readFileSync(new URL(name, templateFolder(key)), 'utf-8');
}

/** The uploaded files of a catalog template, diagrams last (paths.json excluded). */
export function templateFiles(key: string): Record<string, string> {
  const folder = templateFolder(key);
  return Object.fromEntries(folderFiles(folder).map((name) => [name, readFileSync(new URL(name, folder), 'utf-8')]));
}

/** A file the app must refuse (seed/catalog/refused/<name>): diagrams for the upload guard tests, a broken BPMN test file. */
export function refusedFile(name: string): string {
  return readFileSync(new URL(`../seed/catalog/refused/${name}`, import.meta.url), 'utf-8');
}

/** Id of the latest imported version of the seeded template `key` (the seed imports it first). */
export async function seededTemplateId(page: Page, key: string): Promise<number> {
  const tkey = templateKey(key);
  const list = await backendFetch(page, `/v1.0/m8flow/templates?template_key=${encodeURIComponent(tkey)}`);
  const rows = ((list.body as { results?: TemplateRow[] } | null)?.results ?? []).filter((r) => r.templateKey === tkey);
  const latest = rows.sort((a, b) => b.id - a.id)[0];
  if (!latest) throw new Error(`[seed catalog] template ${tkey} is not in M8Flow; is "${key}" listed under catalog.templates in seed/baseline.json?`);
  return latest.id;
}

/**
 * Creates model `group:modelId` from the seeded template `key` (a copy of its
 * files; the template itself is not changed), sets its primary diagram and
 * publishes it unless `publish` is false. Returns the route.
 */
export async function modelFromSeededTemplate(
  page: Page,
  key: string,
  model: { groupId: string; id: string; name: string; publish?: boolean },
): Promise<string> {
  const templateId = await seededTemplateId(page, key);
  const route = `${model.groupId}:${model.id}`;
  const result = await backendFetch(page, `/v1.0/m8flow/templates/${templateId}/create-process-model`, {
    method: 'POST',
    data: { process_group_id: model.groupId, process_model_id: model.id, display_name: model.name, description: E2E_DESCRIPTION },
  });
  if (result.status >= 300) {
    throw new Error(`Creating ${route} from the seeded template ${key} failed: ${result.status} ${JSON.stringify(result.body).slice(0, 300)}`);
  }
  await setPrimaryFile(page, route, templatePrimary(key));
  // Exactly the template's files (in case the server adds a default diagram to a new model).
  const names = folderFiles(templateFolder(key));
  for (const extra of ((await readDetail(page, route)).files ?? []).filter((f) => !names.includes(f.name))) {
    await deleteProcessModelFile(page, extra.name, route);
  }
  if (model.publish !== false) await setModelStatus(page, route, 'published');
  return route;
}

/** The diagram of a catalog template (its only .bpmn file). */
export function templatePrimary(key: string): string {
  const bpmn = folderFiles(templateFolder(key)).filter((n) => n.toLowerCase().endsWith('.bpmn'));
  if (bpmn.length !== 1) throw new Error(`[seed catalog] template ${key} must have exactly one .bpmn file, found ${bpmn.join(', ') || 'none'}`);
  return bpmn[0];
}

/** The BPMN process id of a catalog template's diagram. */
export function templateProcessId(key: string): string {
  const m = templateFile(key, templatePrimary(key)).match(/<bpmn:process id="([^"]+)"/);
  if (!m) throw new Error(`[seed catalog] no process id in template ${key}`);
  return m[1];
}

/** File names of a template detail answer (GET /v1.0/m8flow/templates/{id}), sorted. */
export function templateFileNames(body: unknown): string[] {
  return ((body as { files?: { fileName?: string; name?: string }[] } | null)?.files ?? [])
    .map((f) => f.fileName ?? f.name ?? '')
    .sort();
}

/**
 * Imports each template of baseline.json once (key e2e-<key>). The ZIP of its
 * folder carries a build tag (hash of the files); when the files change, a new
 * template version is imported. Returns template id by key.
 */
export async function ensureTemplates(page: Page): Promise<{ ids: Record<string, number>; imported: string[] }> {
  const ids: Record<string, number> = {};
  const imported: string[] = [];
  for (const template of loadBaseline().catalog.templates ?? []) {
    const folder = templateFolder(template.key);
    const files: Record<string, Buffer> = {};
    for (const name of folderFiles(folder)) files[name] = readFileSync(new URL(name, folder));
    const zip = zipFiles(files);
    const hash = createHash('sha256');
    for (const name of Object.keys(files).sort()) hash.update(name).update(files[name]);
    const buildTag = `build-${hash.digest('hex').slice(0, 12)}`;
    const key = templateKey(template.key);
    const list = await backendFetch(page, `/v1.0/m8flow/templates?template_key=${encodeURIComponent(key)}`);
    const rows = ((list.body as { results?: TemplateRow[] } | null)?.results ?? []).filter((r) => r.templateKey === key);
    const latest = rows.sort((a, b) => b.id - a.id)[0];
    if (latest && (latest.tags ?? []).includes(buildTag)) {
      // Same version as the catalog: still check its files on the server (a file can be
      // deleted there by hand). Different files: import it again from the catalog.
      const detail = await backendFetch(page, `/v1.0/m8flow/templates/${latest.id}`);
      const served = detail.status === 200 ? templateFileNames(detail.body) : [];
      const expected = Object.keys(files).sort();
      if (JSON.stringify(served) === JSON.stringify(expected)) {
        ids[template.key] = latest.id;
        continue;
      }
      console.log(
        `[seed catalog] template ${key} on the server has ${detail.status === 200 ? `files ${served.join(', ') || 'none'}` : `no readable detail (${detail.status})`}, ` +
          `the catalog has ${expected.join(', ')}: importing it again.`,
      );
    }
    const created = await postMultipart(page, '/v1.0/m8flow/templates/import', { name: `${key}.zip`, mimeType: 'application/zip', buffer: zip }, {
      'X-Template-Key': key,
      'X-Template-Name': template.name,
      'X-Template-Visibility': 'TENANT',
      'X-Template-Is-Published': 'true',
      'X-Template-Category': template.category ?? 'E2E',
      'X-Template-Tags': JSON.stringify(['e2e', buildTag]),
    });
    if (created.status >= 300) {
      throw new Error(`[seed catalog] importing template ${key} failed: ${created.status} ${JSON.stringify(created.body).slice(0, 300)}`);
    }
    ids[template.key] = (created.body as { id: number }).id;
    imported.push(template.key);
  }
  return { ids, imported };
}

/** The repository .env (one folder above m8flow-designer), as key -> value; empty when missing. */
function repoEnv(): Record<string, string> {
  const file = new URL('../../../.env', import.meta.url);
  if (!existsSync(file)) return {};
  const env: Record<string, string> = {};
  for (const line of readFileSync(file, 'utf-8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
  return env;
}

/** Hosts of a stack on this machine (a throwaway test stack, as in the E2E gate). */
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

export type PostgresConnection = { dsn: string; source: string } | { dsn: null; reason: string };

/**
 * The database connection for the postgres steps of the templates, or why there is none.
 *
 * A DoSQL connector profile lets every process of the tenant run SQL with these
 * credentials, so the database owner's login is only used on a throwaway stack:
 * - M8FLOW_E2E_PG_DSN when set (use a database user that may only touch the e2e_* tables);
 * - else, only for a stack on this machine or in CI, POSTGRES_USER / POSTGRES_PASSWORD /
 *   POSTGRES_DB from the repository .env (or the environment) -- no built-in defaults.
 * Otherwise there is no connection: the profile is not created and the routes with a
 * postgres step are skipped. The password is never logged.
 */
export function postgresConnection(): PostgresConnection {
  if (process.env.M8FLOW_E2E_PG_DSN) return { dsn: process.env.M8FLOW_E2E_PG_DSN, source: 'M8FLOW_E2E_PG_DSN' };
  const host = new URL(process.env.M8FLOW_DESIGNER_BASE_URL ?? 'http://localhost:6853').hostname;
  if (!LOCAL_HOSTS.has(host) && process.env.CI !== 'true') {
    return { dsn: null, reason: `the stack at ${host} is not a local or CI stack and M8FLOW_E2E_PG_DSN is not set` };
  }
  const env = { ...repoEnv(), ...process.env } as Record<string, string | undefined>;
  if (!env.POSTGRES_USER || !env.POSTGRES_PASSWORD) {
    return { dsn: null, reason: 'POSTGRES_USER / POSTGRES_PASSWORD are not in the repository .env and M8FLOW_E2E_PG_DSN is not set' };
  }
  return {
    dsn: `host=m8flow-db port=5432 dbname=${env.POSTGRES_DB ?? env.POSTGRES_USER} user=${env.POSTGRES_USER} password=${env.POSTGRES_PASSWORD}`,
    source: 'the local stack (.env)',
  };
}

/**
 * Creates the connector profiles of baseline.json when missing (needs a tenant admin page).
 * Returns what was created and what was left out (with the reason, never the credentials).
 */
export async function ensureConnectorProfiles(page: Page): Promise<{ created: string[]; skipped: string[] }> {
  const created: string[] = [];
  const skipped: string[] = [];
  for (const profile of loadBaseline().connectorProfiles ?? []) {
    const name = `${profile.connector_type}/${profile.profile_name}`;
    const list = await backendFetch(page, `/v1.0/m8flow/connector-profiles?connector_type=${encodeURIComponent(profile.connector_type)}`);
    const body = list.body as { profile_name?: string }[] | { results?: { profile_name?: string }[] } | null;
    const rows = Array.isArray(body) ? body : body?.results ?? [];
    if (rows.some((r) => r.profile_name === profile.profile_name)) continue;
    let config: Record<string, string> = {};
    if (profile.connector_type === 'postgres_v2') {
      const connection = postgresConnection();
      if (connection.dsn === null) {
        skipped.push(`${name} (${connection.reason})`);
        continue;
      }
      config = { database_connection_str: connection.dsn };
    }
    const result = await backendFetch(page, '/v1.0/m8flow/connector-profiles', {
      method: 'POST',
      data: {
        connector_type: profile.connector_type,
        profile_name: profile.profile_name,
        display_name: profile.display_name,
        description: profile.description,
        config,
      },
    });
    if (result.status >= 300 && result.status !== 409) {
      throw new Error(`[seed catalog] creating connector profile ${name} failed: ${result.status} ${JSON.stringify(result.body).slice(0, 300)}`);
    }
    created.push(name);
  }
  return { created, skipped };
}

/** True when the tenant has the connector profile the postgres steps use (read as the given user). */
export async function hasPostgresProfile(page: Page): Promise<boolean> {
  const profile = (loadBaseline().connectorProfiles ?? []).find((p) => p.connector_type === 'postgres_v2');
  if (!profile) return false;
  const list = await backendFetch(page, `/v1.0/m8flow/connector-profiles?connector_type=postgres_v2`);
  if (list.status !== 200) return false;
  const body = list.body as { profile_name?: string }[] | { results?: { profile_name?: string }[] } | null;
  const rows = Array.isArray(body) ? body : body?.results ?? [];
  return rows.some((r) => r.profile_name === profile.profile_name);
}

/** True when a seeded model's diagram has a postgres step (needs the e2e connector profile). */
export function usesPostgres(modelId: string): boolean {
  return catalogFile(modelId, catalogModel(modelId).primary).includes('postgres_v2/');
}

function modelPath(routeId: string): string {
  return `/v1.0/m8flow/process-models/${routeId.split(':').map(encodeURIComponent).join(':')}`;
}

type ModelDetail = { status?: string; files?: { name: string; primary?: boolean }[] };

/**
 * Makes the seeded catalog match baseline.json: creates what is missing,
 * re-uploads a file only when its content differs, sets the primary diagram,
 * removes files that are not listed (e.g. the default diagram the server adds
 * to a new model) and gives each model its "status" (draft, published or
 * paused; back to draft while its files change). Returns how many files it had to write.
 */
export async function ensureSeedCatalog(
  page: Page,
): Promise<{ models: string[]; filesWritten: number; templatesImported: string[] }> {
  const { group, models } = loadBaseline().catalog;
  await createMockGroup(page, { id: group.id, display_name: group.name, description: SEED_DESCRIPTION });
  const templates = await ensureTemplates(page);
  let filesWritten = 0;
  for (const model of models) {
    const route = `${group.id}:${model.id}`;
    if (model.template) {
      if ((await backendFetch(page, modelPath(route))).status === 404) {
        const result = await backendFetch(page, `/v1.0/m8flow/templates/${templates.ids[model.template]}/create-process-model`, {
          method: 'POST',
          data: { process_group_id: group.id, process_model_id: model.id, display_name: model.name, description: SEED_DESCRIPTION },
        });
        if (result.status >= 300) {
          throw new Error(`[seed catalog] creating ${route} from template ${model.template} failed: ${result.status} ${JSON.stringify(result.body).slice(0, 300)}`);
        }
      }
    } else {
      await createMockModel(page, { group_id: group.id, id: model.id, display_name: model.name, description: SEED_DESCRIPTION });
    }
    const names = catalogFiles(model.id);
    const changed: string[] = [];
    for (const name of names) {
      if ((await readProcessModelFile(page, name, route)) !== catalogFile(model.id, name)) changed.push(name);
    }
    let detail = await readDetail(page, route);
    const extras = (detail.files ?? []).filter((f) => !names.includes(f.name));
    const primaryOk = (detail.files ?? []).some((f) => f.name === model.primary && f.primary);
    if ((changed.length || extras.length || !primaryOk) && detail.status !== 'draft') {
      await setModelStatus(page, route, 'draft');
    }
    for (const name of changed) await seedProcessModelFile(page, name, catalogFile(model.id, name), route);
    filesWritten += changed.length;
    if (!primaryOk) await setPrimaryFile(page, route, model.primary);
    for (const extra of extras) await deleteProcessModelFile(page, extra.name, route);
    detail = await readDetail(page, route);
    // Paused is reached through published (a draft cannot be paused).
    if (detail.status !== model.status) {
      if (model.status === 'paused' && detail.status === 'draft') await setModelStatus(page, route, 'published');
      await setModelStatus(page, route, model.status);
    }
  }
  return { models: models.map((m) => m.id), filesWritten, templatesImported: templates.imported };
}

async function readDetail(page: Page, route: string): Promise<ModelDetail> {
  const detail = await backendFetch(page, modelPath(route));
  if (detail.status !== 200) throw new Error(`[seed catalog] GET ${route} answered ${detail.status}`);
  return detail.body as ModelDetail;
}

/** A seeded model used as it is (tests that only start and run it need no copy). */
export function seededModel(id: string): SeededModelCopy {
  const model = catalogModel(id);
  const route = `${catalogGroup().id}:${model.id}`;
  return {
    route,
    name: model.name,
    primaryFile: model.primary,
    detailPath: `/processes/${route}`,
    modelerPath: (fileName = model.primary) => `/processes/${route}/modeler/${fileName}`,
  };
}

/**
 * Leftovers in the seeded catalog, removed by the seed (as tenant admin):
 * instances of the seeded models (a run deletes its own; these are from stopped
 * runs) and copies older than E2E_LEFTOVER_MAX_AGE_MIN (same rule as the other leftovers).
 */
export async function sweepCatalogLeftovers(page: Page, maxAgeMin = leftoverMaxAgeMin()): Promise<{ copies: number; instances: number }> {
  const group = catalogGroup();
  let instances = 0;
  for (const model of loadBaseline().catalog.models) {
    const ids = await listModelInstanceIds(page, `${group.id}:${model.id}`).catch(() => [] as number[]);
    await deleteInstanceIds(page, ids);
    instances += ids.length;
  }
  const seeded = new Set(loadBaseline().catalog.models.map((m) => m.id));
  const list = await backendFetch(page, `/v1.0/m8flow/process-models?group=${encodeURIComponent(group.id)}`);
  let removed = 0;
  for (const m of list.status === 200 ? listRows<{ id: string }>(list.body) : []) {
    const leaf = m.id.split('/').pop() ?? '';
    const stamp = e2eStampTime(leaf);
    if (seeded.has(leaf) || stamp === undefined || Date.now() - stamp <= maxAgeMin * 60_000) continue;
    if (await removeMockModelCompletely(page, m.id.replace(/\//g, ':'))) removed += 1;
  }
  return { copies: removed, instances };
}

export type SeededModelCopy = {
  /** `group:model` route id of the copy (set before the first test). */
  readonly route: string;
  readonly name: string;
  /** The primary diagram of the seeded model. */
  readonly primaryFile: string;
  /** /processes/<route> */
  readonly detailPath: string;
  /** Modeler page of a file in the copy (the primary diagram by default). */
  modelerPath(fileName?: string): string;
};

/**
 * Call once at the top of a spec file: before its tests the editor copies the
 * seeded model `sourceId` (copies start as draft and have all its files);
 * after them a tenant admin deletes the copy with any instances.
 * `label` (letters, digits, dashes) names the copy: e2e-<label>-<time stamp>.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useSeededModelCopy(test: TestType<any, any>, label: string, sourceId: string): SeededModelCopy {
  const source = catalogModel(sourceId);
  const group = catalogGroup();
  const stamp = newStamp();
  const id = `e2e-${label}-${stamp}`;
  const route = `${group.id}:${id}`;
  const name = `E2E ${label} ${stamp}`;
  let ready = false;

  test.beforeAll(async ({ browser }) => {
    // The seed alone can take up to ~3 minutes (all users sign in, templates checked); the copy is made after it.
    test.setTimeout(480_000);
    await seedBaselineOnce(browser);
    await withEditorPage(browser, async (page) => {
      const result = await backendFetch(page, `${modelPath(`${group.id}:${source.id}`)}/copy`, {
        method: 'POST',
        data: { id, display_name: name },
      });
      if (result.status !== 201 && result.status !== 409) {
        throw new Error(`Copying the seeded model "${source.id}" failed: ${result.status} ${JSON.stringify(result.body).slice(0, 300)}`);
      }
    });
    ready = true;
  });

  test.afterAll(async ({ browser }) => {
    // Tenant admin: since M8F-627 only the starter or a tenant admin may delete an instance.
    if (!ready) return;
    await withAdminPage(browser, async (page) => {
      await removeMockModelCompletely(page, route);
    });
  });

  return {
    route,
    name,
    primaryFile: source.primary,
    detailPath: `/processes/${route}`,
    modelerPath: (fileName = source.primary) => `/processes/${route}/modeler/${fileName}`,
  };
}
