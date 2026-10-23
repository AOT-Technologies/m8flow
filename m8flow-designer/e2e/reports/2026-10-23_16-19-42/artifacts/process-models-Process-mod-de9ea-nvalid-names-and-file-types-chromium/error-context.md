# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: process-models.spec.ts >> Process model page for a tenant with data >> PRC-38: Add file trims names, adds the right extension and refuses invalid names and file types
- Location: e2e\process-models.spec.ts:746:3

# Error details

```
Error: locator.fill: Target page, context or browser has been closed
Call log:
  - waiting for getByRole('dialog', { name: 'Add file' }).getByLabel('File name')

```

```
Error: browserContext.close: Target page, context or browser has been closed
```

```
Error: browser.newPage: Target page, context or browser has been closed
```

# Test source

```ts
  83  |     throw new Error(`setPrimaryFile(${routeId}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  84  |   }
  85  | }
  86  | 
  87  | /** Best effort: a cleanup problem is logged, never fails a test. */
  88  | export async function deleteMockModel(page: Page, routeId: string): Promise<void> {
  89  |   const result = await backendFetch(page, modelPath(routeId), { method: 'DELETE' }).catch(() => null);
  90  |   if (result && !ok(result.status, [404])) {
  91  |     console.warn(`[cleanup] delete mock model ${routeId} skipped: ${result.status}`);
  92  |   }
  93  | }
  94  | 
  95  | /** Best effort: a cleanup problem is logged, never fails a test. */
  96  | export async function deleteMockGroup(page: Page, groupId: string): Promise<void> {
  97  |   const result = await backendFetch(page, groupPath(groupId), { method: 'DELETE' }).catch(() => null);
  98  |   if (result && !ok(result.status, [404])) {
  99  |     console.warn(`[cleanup] delete mock group ${groupId} skipped: ${result.status}`);
  100 |   }
  101 | }
  102 | 
  103 | /**
  104 |  * The shared mock model the Modeler specs use (SEED_* in fixtures.ts):
  105 |  * group "E2E Mock Catalog" / model "E2E Mock Model" with a user-task BPMN
  106 |  * (primary) and mock form schema files. Re-uploading the files resets any
  107 |  * edit a previous run left behind.
  108 |  */
  109 | export async function ensureMockProcessModel(page: Page): Promise<void> {
  110 |   await createMockGroup(page, { id: SEED_GROUP_ID, display_name: SEED_GROUP_NAME });
  111 |   await createMockModel(page, { group_id: SEED_GROUP_ID, id: SEED_MODEL_ID, display_name: SEED_MODEL_NAME });
  112 |   await seedMockModelFiles(page, SEED_MODEL_ROUTE_ID);
  113 | }
  114 | 
  115 | /** Uploads the mock files (user-task BPMN + form schemas) and sets the BPMN as primary. */
  116 | export async function seedMockModelFiles(page: Page, routeId: string): Promise<void> {
  117 |   for (const name of MOCK_FILES) {
  118 |     await seedProcessModelFile(page, name, mockFile(name), routeId);
  119 |   }
  120 |   await setPrimaryFile(page, routeId, SEED_PRIMARY_FILE);
  121 | }
  122 | 
  123 | export type MockModelStatus = 'draft' | 'published' | 'paused';
  124 | 
  125 | /** Moves a model through its lifecycle (new models start as draft). */
  126 | export async function setModelStatus(page: Page, routeId: string, status: MockModelStatus): Promise<void> {
  127 |   const result = await backendFetch(page, modelPath(routeId), { method: 'PUT', data: { status } });
  128 |   if (!ok(result.status, [])) {
  129 |     throw new Error(`setModelStatus(${routeId}, ${status}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  130 |   }
  131 | }
  132 | 
  133 | /** Starts an instance of a published model and returns its id. */
  134 | export async function startMockInstance(page: Page, routeId: string): Promise<number> {
  135 |   const result = await backendFetch(page, `${modelPath(routeId)}/start`, { method: 'POST' });
  136 |   if (!ok(result.status, [])) {
  137 |     throw new Error(`startMockInstance(${routeId}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  138 |   }
  139 |   return (result.body as { id: number }).id;
  140 | }
  141 | 
  142 | /**
  143 |  * Best effort: terminates and deletes the given instances plus every recent
  144 |  * instance of the model, so the model itself can then be deleted.
  145 |  */
  146 | /** Terminates and deletes the instances listed on a model, plus any extra ids. */
  147 | export async function deleteMockInstances(page: Page, routeId: string, extraIds: number[] = []): Promise<void> {
  148 |   const ids = new Set(extraIds);
  149 |   const detail = await backendFetch(page, modelPath(routeId)).catch(() => null);
  150 |   if (detail && detail.status === 200) {
  151 |     for (const row of (detail.body as { recent_instances?: { id: number }[] }).recent_instances ?? []) {
  152 |       ids.add(row.id);
  153 |     }
  154 |   }
  155 |   await deleteInstanceIds(page, [...ids]);
  156 | }
  157 | 
  158 | /** Terminates and deletes instances by id. Best effort: problems are logged. */
  159 | export async function deleteInstanceIds(page: Page, ids: number[]): Promise<void> {
  160 |   for (const id of new Set(ids)) {
  161 |     await backendFetch(page, `/v1.0/m8flow/process-instances/${id}/terminate`, { method: 'POST' }).catch(() => null);
  162 |     const result = await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`, { method: 'DELETE' }).catch(() => null);
  163 |     if (result && !ok(result.status, [404])) {
  164 |       console.warn(`[cleanup] delete mock instance ${id} skipped: ${result.status}`);
  165 |     }
  166 |   }
  167 | }
  168 | 
  169 | /** Best effort: a cleanup problem is logged, never fails a test. */
  170 | export async function deleteMockTemplate(page: Page, templateId: number): Promise<void> {
  171 |   const result = await backendFetch(page, `/v1.0/m8flow/templates/${templateId}`, { method: 'DELETE' }).catch(() => null);
  172 |   if (result && !ok(result.status, [404])) {
  173 |     console.warn(`[cleanup] delete mock template ${templateId} skipped: ${result.status}`);
  174 |   }
  175 | }
  176 | 
  177 | export async function removeMockProcessModel(page: Page): Promise<void> {
  178 |   await deleteMockModel(page, SEED_MODEL_ROUTE_ID);
  179 |   await deleteMockGroup(page, SEED_GROUP_ID);
  180 | }
  181 | 
  182 | async function withEditorPage(browser: Browser, action: (page: Page) => Promise<void>): Promise<void> {
> 183 |   const page = await browser.newPage();
      |                              ^ Error: browser.newPage: Target page, context or browser has been closed
  184 |   try {
  185 |     await useSession(page, editorCredentials());
  186 |     await action(page);
  187 |   } finally {
  188 |     await page.close();
  189 |   }
  190 | }
  191 | 
  192 | /**
  193 |  * Call once at the top of a spec file: creates the mock process model before
  194 |  * the file's tests and deletes it after them.
  195 |  */
  196 | // eslint-disable-next-line @typescript-eslint/no-explicit-any
  197 | export function useMockProcessModel(test: TestType<any, any>): void {
  198 |   test.beforeAll(async ({ browser }) => {
  199 |     await withEditorPage(browser, ensureMockProcessModel);
  200 |   });
  201 |   test.afterAll(async ({ browser }) => {
  202 |     await withEditorPage(browser, removeMockProcessModel);
  203 |   });
  204 | }
  205 | 
  206 | export type ActiveCatalogModel = {
  207 |   id: string;
  208 |   name: string;
  209 |   status: MockModelStatus;
  210 |   /** Upload the mock user-task BPMN + form files and set the BPMN as primary. */
  211 |   files: boolean;
  212 |   /** Start one process instance (the model must be published). */
  213 |   instance: boolean;
  214 | };
  215 | 
  216 | /** Everything a spec creates on top of the catalog, so afterAll can remove it. */
  217 | export type ActiveCatalogTracker = {
  218 |   instances: number[];
  219 |   models: string[];
  220 |   groups: string[];
  221 |   templates: number[];
  222 | };
  223 | 
  224 | /**
  225 |  * A tenant with data: call once at the top of a spec file. Before the file's
  226 |  * tests it creates one mock group with the given models (status, files and an
  227 |  * optional running instance); after them it removes those models, anything
  228 |  * recorded in the returned tracker, and the group.
  229 |  */
  230 | export function useActiveCatalog(
  231 |   // eslint-disable-next-line @typescript-eslint/no-explicit-any
  232 |   test: TestType<any, any>,
  233 |   group: { id: string; name: string },
  234 |   models: ActiveCatalogModel[],
  235 | ): ActiveCatalogTracker {
  236 |   const tracker: ActiveCatalogTracker = { instances: [], models: [], groups: [], templates: [] };
  237 |   const route = (m: { id: string }) => `${group.id}:${m.id}`;
  238 | 
  239 |   test.beforeAll(async ({ browser }) => {
  240 |     test.setTimeout(240_000);
  241 |     await withEditorPage(browser, async (page) => {
  242 |       await createMockGroup(page, { id: group.id, display_name: group.name });
  243 |       for (const m of models) {
  244 |         await createMockModel(page, { group_id: group.id, id: m.id, display_name: m.name });
  245 |         if (m.files) await seedMockModelFiles(page, route(m));
  246 |         if (m.status !== 'draft') await setModelStatus(page, route(m), 'published');
  247 |         if (m.status === 'paused') await setModelStatus(page, route(m), 'paused');
  248 |         if (m.instance) tracker.instances.push(await startMockInstance(page, route(m)));
  249 |       }
  250 |     });
  251 |   });
  252 | 
  253 |   test.afterAll(async ({ browser }) => {
  254 |     test.setTimeout(240_000);
  255 |     await withEditorPage(browser, async (page) => {
  256 |       const routes = [...models.map(route), ...tracker.models];
  257 |       // 1. Instances the tests started (tracked by id, whatever model they belong to).
  258 |       await deleteInstanceIds(page, tracker.instances);
  259 |       // 2. Per model: any instance still listed on it, then the model itself.
  260 |       for (const r of routes) {
  261 |         await deleteMockInstances(page, r);
  262 |         await deleteMockModel(page, r);
  263 |       }
  264 |       for (const id of tracker.templates) await deleteMockTemplate(page, id);
  265 |       for (const g of [...tracker.groups, group.id]) await deleteMockGroup(page, g);
  266 |     });
  267 |   });
  268 | 
  269 |   return tracker;
  270 | }
  271 | 
```