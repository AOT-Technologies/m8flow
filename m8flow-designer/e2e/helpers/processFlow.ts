import { expect, test, type Browser, type Locator, type Page, type TestInfo, type TestType } from '@playwright/test';

import {
  continueInTenant,
  cookieValue,
  editorCredentials,
  reviewerCredentials,
  submitterCredentials,
  tenantAdminCredentials,
  useSession,
  type DesignerPersona,
} from './auth';
import { backendFetch } from './backendApi';
import {
  createMockGroup,
  createMockModel,
  deleteInstanceIds,
  deleteMockGroup,
  deleteMockTemplate,
  setModelStatus,
  setPrimaryFile,
  startMockInstance,
  removeMockModelCompletely,
  sweepLeftoversOnce,
} from './mockCatalog';
import { seedProcessModelFile } from './seedFixture';

/**
 * Shared helpers for the process-flow specs (e2e-flow*.spec.ts): build test
 * BPMN/forms in code, create/clean the test catalog, run tasks through the
 * API, and wait for asynchronous workflow changes without fixed sleeps.
 *
 * Lane names are Keycloak organization groups of the seeded users:
 *   Submitters -> submitter, Approvers -> reviewer, Administrators -> admin,
 *   Designers -> editor, Viewers -> viewer, Support -> integrator.
 */

export const LANE = {
  submitters: 'Submitters',
  approvers: 'Approvers',
  administrators: 'Administrators',
  designers: 'Designers',
} as const;

export function newStamp(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

// ---------------------------------------------------------------------------
// BPMN and form builders
// ---------------------------------------------------------------------------

export type FlowStep = {
  /** BPMN element id, e.g. "Activity_step1". */
  id: string;
  /** Task name shown in Task Review. */
  name: string;
  /** Lane (group) name; null puts it in an unnamed lane. */
  lane: string | null;
  /** Form schema file name (must be uploaded with the model). */
  form?: string;
};

export type FlowGateway =
  /** After step `afterStep`: "Approve" (outcome == 'approve') continues, "Reject" ends. */
  | { kind: 'outcome'; afterStep: number }
  /** After step `afterStep`: field > threshold continues, otherwise ends. */
  | { kind: 'amount'; afterStep: number; field: string; threshold: number };

export type FlowOptions = {
  processId: string;
  name: string;
  steps: FlowStep[];
  gateway?: FlowGateway;
  /** Add a script task after the last step that always fails (instance goes to Error). */
  failingScript?: boolean;
};

const xml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** A BPMN process built from steps; ids are stable, the process id must be unique per model. */
export function flowBpmn(o: FlowOptions): string {
  type Node = { id: string; tag: string; name?: string; lane: string | null; inner?: string; attrs?: string };
  const nodes: Node[] = [];
  const flows: string[] = [];
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  let flowNo = 0;
  let pending: { name: string; condition: string } | undefined;

  const node = (n: Node) => nodes.push(n);
  const connect = (from: string, to: string) => {
    const id = `Flow_${++flowNo}`;
    const cond = pending;
    pending = undefined;
    flows.push(
      `    <bpmn:sequenceFlow id="${id}" sourceRef="${from}" targetRef="${to}"${cond ? ` name="${xml(cond.name)}"` : ''}>` +
        (cond ? `<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">${xml(cond.condition)}</bpmn:conditionExpression>` : '') +
        `</bpmn:sequenceFlow>`,
    );
    outgoing.set(from, [...(outgoing.get(from) ?? []), id]);
    incoming.set(to, [...(incoming.get(to) ?? []), id]);
  };

  node({ id: 'StartEvent_1', tag: 'startEvent', lane: null });
  let prev = 'StartEvent_1';
  let lastLane: string | null = null;
  const endOther = 'EndEvent_other';
  let needOtherEnd = false;

  o.steps.forEach((step, i) => {
    node({
      id: step.id,
      tag: 'userTask',
      name: step.name,
      lane: step.lane,
      inner: step.form
        ? `<bpmn:extensionElements><spiffworkflow:properties><spiffworkflow:property name="formJsonSchemaFilename" value="${xml(step.form)}" /></spiffworkflow:properties></bpmn:extensionElements>`
        : undefined,
    });
    connect(prev, step.id);
    prev = step.id;
    lastLane = step.lane;
    if (o.gateway && o.gateway.afterStep === i) {
      const gw = 'Gateway_decision';
      node({ id: gw, tag: 'exclusiveGateway', name: 'Decision', lane: step.lane });
      connect(prev, gw);
      needOtherEnd = true;
      if (o.gateway.kind === 'outcome') {
        pending = { name: 'Reject', condition: "outcome == 'reject'" };
        connect(gw, endOther);
        pending = { name: 'Approve', condition: "outcome == 'approve'" };
      } else {
        pending = { name: 'Below limit', condition: `${o.gateway.field} <= ${o.gateway.threshold}` };
        connect(gw, endOther);
        pending = { name: 'Above limit', condition: `${o.gateway.field} > ${o.gateway.threshold}` };
      }
      prev = gw;
    }
  });

  if (o.failingScript) {
    node({
      id: 'Activity_fail',
      tag: 'scriptTask',
      name: 'E2E Failing Step',
      lane: lastLane,
      attrs: ' scriptFormat="python"',
      inner: '<bpmn:script>e2e_result = e2e_undefined_variable + 1</bpmn:script>',
    });
    connect(prev, 'Activity_fail');
    prev = 'Activity_fail';
  }
  node({ id: 'EndEvent_1', tag: 'endEvent', name: 'Done', lane: lastLane });
  connect(prev, 'EndEvent_1');
  if (needOtherEnd) node({ id: endOther, tag: 'endEvent', name: 'Ended early', lane: lastLane });

  const lanes = new Map<string, string[]>();
  for (const n of nodes) lanes.set(n.lane ?? '', [...(lanes.get(n.lane ?? '') ?? []), n.id]);
  const useLanes = [...lanes.keys()].some((k) => k !== '');

  const body = nodes
    .map((n) => {
      const ins = (incoming.get(n.id) ?? []).map((f) => `<bpmn:incoming>${f}</bpmn:incoming>`).join('');
      const outs = (outgoing.get(n.id) ?? []).map((f) => `<bpmn:outgoing>${f}</bpmn:outgoing>`).join('');
      const name = n.name ? ` name="${xml(n.name)}"` : '';
      // BPMN order: extensionElements, incoming, outgoing, then (script) body.
      const ext = n.inner && n.tag !== 'scriptTask' ? n.inner : '';
      const script = n.tag === 'scriptTask' ? n.inner ?? '' : '';
      return `    <bpmn:${n.tag} id="${n.id}"${name}${n.attrs ?? ''}>${ext}${ins}${outs}${script}</bpmn:${n.tag}>`;
    })
    .join('\n');

  const laneSet = useLanes
    ? `    <bpmn:laneSet id="LaneSet_1">\n${[...lanes.entries()]
        .map(
          ([lane, ids], i) =>
            `      <bpmn:lane id="Lane_${i + 1}"${lane ? ` name="${xml(lane)}"` : ''}>${ids
              .map((id) => `<bpmn:flowNodeRef>${id}</bpmn:flowNodeRef>`)
              .join('')}</bpmn:lane>`,
        )
        .join('\n')}\n    </bpmn:laneSet>\n`
    : '';

  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
                  id="Definitions_${o.processId}" targetNamespace="http://m8flow.org/e2e/flow">
${useLanes ? `  <bpmn:collaboration id="Collaboration_1"><bpmn:participant id="Participant_1" name="${xml(o.name)}" processRef="${o.processId}" /></bpmn:collaboration>\n` : ''}  <bpmn:process id="${o.processId}" name="${xml(o.name)}" isExecutable="true">
${laneSet}${body}
${flows.join('\n')}
  </bpmn:process>
</bpmn:definitions>
`;
}

export type FormField = {
  type: 'string' | 'number' | 'integer' | 'boolean';
  title: string;
  format?: 'date';
  enum?: string[];
  minLength?: number;
  maxLength?: number;
};

/** A JSON form schema (the subset Task Review renders). */
export function formSchema(title: string, fields: Record<string, FormField>, required: string[] = []): string {
  return JSON.stringify({ title, description: 'E2E test form (test data only).', type: 'object', required, properties: fields }, null, 2);
}

/** A process id safe for BPMN (letters, digits, underscore). */
export function processIdFor(...parts: string[]): string {
  return `Process_${parts.join('_')}`.replace(/[^A-Za-z0-9_]/g, '_');
}

// ---------------------------------------------------------------------------
// Minimal ZIP writer (stored, no compression) for template import tests.
// ---------------------------------------------------------------------------

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function zipFiles(files: Record<string, string | Buffer>): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const [name, content] of Object.entries(files)) {
    const data = Buffer.isBuffer(content) ? content : Buffer.from(content, 'utf-8');
    const nameBuf = Buffer.from(name, 'utf-8');
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt32LE(0, 10);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28);
    locals.push(local, nameBuf, data);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt32LE(0, 12);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBuf);
    offset += 30 + nameBuf.length + data.length;
  }
  const centralSize = centrals.reduce((n, b) => n + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  const count = Object.keys(files).length;
  end.writeUInt16LE(count, 8);
  end.writeUInt16LE(count, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, ...centrals, end]);
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

type RoleSession = { page: Page; checkedAt: number };
const roleSessions = new Map<string, RoleSession>();
/** Re-validate a cached session after this long (tokens are short-lived). */
const SESSION_RECHECK_MS = 3 * 60_000;

/**
 * One logged-in page per role, reused by the tests of this worker for API
 * calls and short UI checks (each worker has its own map, so parallel workers
 * never share a page). The session is re-validated every few minutes. Tests
 * that change routes, cookies or tenants use their own `page` or a new
 * browser context instead.
 */
export async function rolePage(
  browser: Browser,
  persona: DesignerPersona,
  kind: 'shared' | 'platformAdmin' = 'shared',
): Promise<Page> {
  const key = `${kind}:${persona.username}`;
  let session = roleSessions.get(key);
  if (session && (session.page.isClosed() || session.page.context().browser() !== browser)) {
    roleSessions.delete(key);
    session = undefined;
  }
  if (!session) {
    session = { page: await browser.newPage(), checkedAt: 0 };
    roleSessions.set(key, session);
  }
  if (Date.now() - session.checkedAt > SESSION_RECHECK_MS) {
    try {
      await useSession(session.page, persona, kind);
    } catch (error) {
      // The app's redirect to the Keycloak login can abort the browser's
      // navigation (net::ERR_ABORTED / frame detached). Start again once on a
      // new page; a second failure is a real login problem and is reported.
      if (!/ERR_ABORTED|frame was detached|interrupted by another navigation/i.test(String(error))) throw error;
      await session.page.close().catch(() => undefined);
      session.page = await browser.newPage();
      await useSession(session.page, persona, kind);
    }
    session.checkedAt = Date.now();
  }
  return session.page;
}

/** Runs `action` with the cached logged-in page of `persona` (see rolePage). */
export async function withPage<T>(
  browser: Browser,
  persona: DesignerPersona,
  action: (page: Page) => Promise<T>,
  kind: 'shared' | 'platformAdmin' = 'shared',
): Promise<T> {
  return action(await rolePage(browser, persona, kind));
}

/** Opens Home; the app may redirect right after load, so an aborted navigation is retried once. */
export async function gotoHome(page: Page): Promise<void> {
  try {
    await page.goto('/');
  } catch (error) {
    if (!String(error).includes('ERR_ABORTED')) throw error;
    await page.goto('/');
  }
  await continueInTenant(page);
}

// ---------------------------------------------------------------------------
// Test catalog: one group per spec file, models built from FlowOptions.
// ---------------------------------------------------------------------------

export type FlowModelSpec = {
  name: string;
  /** Steps etc. (the process id is added per run), or raw BPMN text. */
  bpmn: Omit<FlowOptions, 'processId' | 'name'> | string;
  /** Extra files (form schemas, …) uploaded before the BPMN. */
  files?: Record<string, string>;
  /** Default true. */
  publish?: boolean;
};

export type FlowModel = { key: string; id: string; name: string; route: string; bpmnFile: string; processId: string };

export type FlowCatalog = {
  stamp: string;
  groupId: string;
  groupName: string;
  model: (key: string) => FlowModel;
  /**
   * A new copy of model `key` just for the calling test (unique id and name),
   * so list and count checks cannot see other tests' or earlier attempts' data.
   */
  fresh: (browser: Browser, key: string) => Promise<FlowModel>;
  /** Everything a test creates outside the declared models; deleted in afterAll. */
  track: { instances: number[]; models: string[]; templates: number[] };
};

/**
 * Call once at the top of a spec file. beforeAll logs in the task users once
 * (so their groups are known before tasks are created), then the editor
 * creates the group and models. afterAll deletes instances, models, templates
 * and the group (best effort; problems are logged, never fail the run).
 */
export function useFlowCatalog(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  test: TestType<any, any>,
  prefix: string,
  specs: Record<string, FlowModelSpec>,
): FlowCatalog {
  const stamp = newStamp();
  const groupId = `e2e-${prefix}-${stamp}`;
  const groupName = `E2E ${prefix} ${stamp}`;
  const models = new Map<string, FlowModel>();
  let freshNo = 0;
  for (const [key, spec] of Object.entries(specs)) {
    const id = `e2e-${key}-${stamp}`.toLowerCase().replace(/[^a-z0-9-]/g, '-');
    models.set(key, {
      key,
      id,
      name: `${spec.name} ${stamp}`,
      route: `${groupId}:${id}`,
      bpmnFile: `${key}.bpmn`.toLowerCase().replace(/[^a-z0-9.-]/g, '-'),
      processId: processIdFor(prefix, key, stamp),
    });
  }
  const catalog: FlowCatalog = {
    stamp,
    groupId,
    groupName,
    model: (key) => {
      const m = models.get(key);
      if (!m) throw new Error(`Unknown flow model "${key}"`);
      return m;
    },
    track: { instances: [], models: [], templates: [] },
    fresh: async (browser, key) => {
      const base = catalog.model(key);
      freshNo += 1;
      const n = `${freshNo}${newStamp().slice(-3)}`;
      const m: FlowModel = {
        ...base,
        id: `${base.id}-t${n}`,
        name: `${base.name}-t${n}`,
        route: `${groupId}:${base.id}-t${n}`,
        processId: `${base.processId}_t${n}`,
      };
      await withPage(browser, editorCredentials(), (page) => createFlowModel(page, m, specs[key]));
      catalog.track.models.push(m.route);
      return m;
    },
  };

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(300_000);
    await checkEnvironment(browser);
    // Log in the task users first so M8Flow knows their groups before tasks are created.
    for (const persona of [submitterCredentials(), reviewerCredentials(), tenantAdminCredentials()]) {
      await rolePage(browser, persona);
    }
    await withPage(browser, editorCredentials(), async (page) => {
      await sweepLeftoversOnce(page);
      await createMockGroup(page, { id: groupId, display_name: groupName });
      for (const [key, spec] of Object.entries(specs)) await createFlowModel(page, catalog.model(key), spec);
    });
  });

  // Failure diagnostics for the test's own page: console errors and failed
  // requests (URLs without query strings, so no tokens end up in the report).
  const diagnostics = new Map<string, string[]>();
  test.beforeEach(async ({ page }: { page: Page }, testInfo: TestInfo) => {
    const lines: string[] = [];
    diagnostics.set(testInfo.testId, lines);
    page.on('console', (m: import('@playwright/test').ConsoleMessage) => {
      if (m.type() === 'error') lines.push(`console: ${m.text().slice(0, 300)}`);
    });
    page.on('requestfailed', (r: import('@playwright/test').Request) => lines.push(`request failed: ${r.method()} ${r.url().split('?')[0]} (${r.failure()?.errorText})`));
    page.on('response', (r: import('@playwright/test').Response) => {
      if (r.status() >= 500) lines.push(`response ${r.status()}: ${r.request().method()} ${r.url().split('?')[0]}`);
    });
  });
  test.afterEach(async ({}, testInfo: TestInfo) => {
    const lines = diagnostics.get(testInfo.testId) ?? [];
    diagnostics.delete(testInfo.testId);
    if (testInfo.status !== testInfo.expectedStatus && lines.length) {
      await testInfo.attach('browser-diagnostics.txt', { body: lines.join('\n'), contentType: 'text/plain' });
    }
  });

  test.afterAll(async ({ browser }) => {
    test.setTimeout(300_000);
    // Tenant admin: since M8F-627 only the starter or a tenant admin may delete an instance.
    await withPage(browser, tenantAdminCredentials(), async (page) => {
      await deleteInstanceIds(page, catalog.track.instances);
      // Each model: all its instances deleted, unpublished, then deleted.
      for (const route of [...[...models.values()].map((m) => m.route), ...catalog.track.models]) {
        await removeMockModelCompletely(page, route);
      }
      for (const id of catalog.track.templates) await deleteMockTemplate(page, id);
      await deleteMockGroup(page, groupId);
    });
  });

  return catalog;
}

/** Creates one model: files, BPMN (primary) and status. */
async function createFlowModel(page: Page, m: FlowModel, spec: FlowModelSpec): Promise<void> {
  await createMockModel(page, { group_id: m.route.split(':')[0], id: m.id, display_name: m.name });
  for (const [file, content] of Object.entries(spec.files ?? {})) {
    await seedProcessModelFile(page, file, content, m.route);
  }
  const bpmn = typeof spec.bpmn === 'string' ? spec.bpmn : flowBpmn({ ...spec.bpmn, processId: m.processId, name: m.name });
  await seedProcessModelFile(page, m.bpmnFile, bpmn, m.route);
  await setPrimaryFile(page, m.route, m.bpmnFile);
  if (spec.publish !== false) await setModelStatus(page, m.route, 'published');
}

/** Fails fast with a clear message when the stack is not reachable. */
async function checkEnvironment(browser: Browser): Promise<void> {
  const context = await browser.newContext();
  try {
    const ready = await context.request.get('/v1.0/readyz').catch((e: unknown) => e);
    if (!(ready && typeof ready === 'object' && 'ok' in ready && (ready as { ok: () => boolean }).ok())) {
      throw new Error(
        `Environment check failed: GET /v1.0/readyz through the designer did not answer 200 (${String(
          ready && typeof ready === 'object' && 'status' in ready ? (ready as { status: () => number }).status() : ready,
        )}). Is the M8Flow stack running and M8FLOW_DESIGNER_BASE_URL / M8FLOW_BACKEND_BASE_URL set?`,
      );
    }
  } finally {
    await context.close();
  }
}

// ---------------------------------------------------------------------------
// Workflow API helpers
// ---------------------------------------------------------------------------

export type TaskItem = {
  id: number;
  task_title: string | null;
  task_name: string;
  process_model_display_name: string;
  process_instance_id: number;
  submitted_by: string | null;
  status: string;
};

export type InstanceTask = { guid: string; bpmn_identifier: string; bpmn_name: string | null; typename: string; state: string };
export type InstanceDetail = {
  id: number;
  status: string;
  started_by: string;
  process_model_display_name: string;
  process_model_identifier: string;
  tasks: InstanceTask[];
  error_message: string | null;
};

export type HomeStats = {
  active_process_instances: number | null;
  tasks_waiting_on_me: number | null;
  show_tasks_waiting_on_me: boolean;
  errors_needing_review: number | null;
  completed_today: number | null;
  avg_completion_minutes: number | null;
  total_tenants: number | null;
};

export type HomeMyTask = {
  id: number;
  task_title: string | null;
  task_name: string;
  tenant_name: string;
  lane_name: string | null;
  process_instance_id: number;
};

export const taskTitle = (t: { task_title: string | null; task_name: string }) => t.task_title?.trim() || t.task_name;

/** Starts an instance through the API (role of `page` must be allowed to start). */
export async function startInstance(page: Page, catalog: FlowCatalog, route: string): Promise<number> {
  const id = await startMockInstance(page, route);
  catalog.track.instances.push(id);
  test.info().annotations.push({ type: 'instance', description: `#${id} of ${route} (run ${catalog.stamp})` });
  return id;
}

export async function startStatus(page: Page, route: string): Promise<number> {
  const path = `/v1.0/m8flow/process-models/${route.split(':').map(encodeURIComponent).join(':')}/start`;
  return (await backendFetch(page, path, { method: 'POST' })).status;
}

/**
 * Since M8F-627 only a tenant admin reads every instance of the tenant; editor,
 * viewer and submitter see only instances they started or have a task in.
 * Status and task-data checks are "what the server holds" checks, not access
 * checks, so they always read as the tenant admin (cached login per worker).
 * Access checks call backendFetch with the user under test instead.
 */
async function orgReader(page: Page): Promise<Page> {
  const browser = page.context().browser();
  return browser ? rolePage(browser, tenantAdminCredentials()) : page;
}

/** Runs `fn` as the tenant admin, who can see and act on every instance (M8F-627). */
export async function asOrgAdmin<T>(browser: Browser, fn: (page: Page) => Promise<T>): Promise<T> {
  return withPage(browser, tenantAdminCredentials(), fn);
}

export async function instanceDetail(page: Page, id: number): Promise<InstanceDetail> {
  const result = await backendFetch(await orgReader(page), `/v1.0/m8flow/process-instances/${id}`);
  expect(result.status, `GET /process-instances/${id}`).toBe(200);
  return result.body as InstanceDetail;
}

/** Waits (up to 30 s) until the instance has one of the given statuses. */
export async function waitForStatus(page: Page, id: number, statuses: string | string[]): Promise<InstanceDetail> {
  const wanted = Array.isArray(statuses) ? statuses : [statuses];
  await expect
    .poll(
      async () => {
        const status = (await instanceDetail(page, id)).status;
        return wanted.includes(status) ? 'reached' : `still "${status}"`;
      },
      { message: `instance #${id} reaches ${wanted.join(' or ')}`, timeout: 30_000 },
    )
    .toBe('reached');
  return instanceDetail(page, id);
}

export async function myTasks(page: Page): Promise<TaskItem[]> {
  const result = await backendFetch(page, '/v1.0/m8flow/task-review?per_page=100');
  expect(result.status, 'GET /task-review').toBe(200);
  return (result.body as { results: TaskItem[] }).results;
}

/** Waits (up to 30 s) for the user's task of an instance (optionally a named step). */
export async function waitForTask(page: Page, instanceId: number, stepName?: string): Promise<TaskItem> {
  let found: TaskItem | undefined;
  await expect
    .poll(
      async () => {
        found = (await myTasks(page)).find(
          (t) => t.process_instance_id === instanceId && (!stepName || taskTitle(t) === stepName || t.task_name === stepName),
        );
        return Boolean(found);
      },
      { message: `task${stepName ? ` "${stepName}"` : ''} of instance #${instanceId} reaches this user`, timeout: 30_000 },
    )
    .toBe(true);
  return found!;
}

export async function hasTaskFor(page: Page, instanceId: number): Promise<boolean> {
  const result = await backendFetch(page, '/v1.0/m8flow/task-review?per_page=100');
  if (result.status !== 200) return false;
  return (result.body as { results: TaskItem[] }).results.some((t) => t.process_instance_id === instanceId);
}

export async function submitTask(
  page: Page,
  taskId: number,
  payload: Record<string, unknown> = {},
): Promise<{ status: number; body: unknown }> {
  return backendFetch(page, `/v1.0/m8flow/task-review/${taskId}/submit`, { method: 'POST', data: payload });
}

/** Waits for the user's task of the instance and submits it through the API. */
export async function completeTask(
  page: Page,
  instanceId: number,
  payload: Record<string, unknown> = {},
  stepName?: string,
): Promise<TaskItem> {
  const task = await waitForTask(page, instanceId, stepName);
  const result = await submitTask(page, task.id, payload);
  expect(result.status, `submit task #${task.id}: ${JSON.stringify(result.body)}`).toBeLessThan(300);
  return task;
}

export async function homeStats(page: Page): Promise<HomeStats> {
  const result = await backendFetch(page, '/v1.0/m8flow/home-stats');
  expect(result.status, 'GET /home-stats').toBe(200);
  return result.body as HomeStats;
}

export async function homeMyTasks(page: Page): Promise<HomeMyTask[]> {
  const result = await backendFetch(page, '/v1.0/m8flow/home-my-tasks');
  expect(result.status, 'GET /home-my-tasks').toBe(200);
  const body = result.body as HomeMyTask[] | { results: HomeMyTask[] };
  return Array.isArray(body) ? body : body.results;
}

/** Task data saved on a completed/ready task of an instance (by BPMN id). */
export async function taskData(page: Page, instanceId: number, bpmnId: string): Promise<Record<string, unknown>> {
  const detail = await instanceDetail(page, instanceId);
  const task = detail.tasks.find((t) => t.bpmn_identifier === bpmnId);
  expect(task, `instance #${instanceId} has task ${bpmnId}`).toBeTruthy();
  const result = await backendFetch(
    await orgReader(page),
    `/v1.0/m8flow/process-instances/${instanceId}/tasks/${encodeURIComponent(task!.guid)}`,
  );
  expect(result.status, `GET task data of ${bpmnId}`).toBe(200);
  return ((result.body as { data?: Record<string, unknown> }).data ?? {}) as Record<string, unknown>;
}

export async function instanceAction(page: Page, id: number, action: 'suspend' | 'resume' | 'terminate'): Promise<number> {
  return (await backendFetch(page, `/v1.0/m8flow/process-instances/${id}/${action}`, { method: 'POST' })).status;
}

/** How Home shows a count: a number, or "—" when the role may not see it. */
export function shown(value: number | null | undefined): string {
  return value == null ? '—' : String(value);
}

/** The number shown on a Home stat card (label and value are siblings). */
export function statValue(page: Page, label: string): Locator {
  return page.getByText(label, { exact: true }).locator('xpath=../following-sibling::span[1]');
}

/** Rows of a DataTable (clickable rows are role=button) that contain `text`. */
export function tableRows(page: Page, text: string): Locator {
  return page.getByRole('table').getByRole('button').filter({ hasText: text });
}

/** Multipart upload with the page's session (template import). */
export async function postMultipart(
  page: Page,
  path: string,
  file: { name: string; mimeType: string; buffer: Buffer },
  headers: Record<string, string>,
): Promise<{ status: number; body: unknown }> {
  const token = await cookieValue(page, 'access_token');
  const response = await page.request.post(path, {
    multipart: { file },
    headers: { Accept: 'application/json', ...headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  const text = await response.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* keep text */
  }
  return { status: response.status(), body };
}

/** UTC date, to detect a run that crosses midnight ("Completed today" resets). */
export const utcDay = () => new Date().toISOString().slice(0, 10);
