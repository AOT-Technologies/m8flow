import {
  getAccessToken,
  type OrganizationMembership,
  resumeLoginAfterLogout,
} from './auth';

/**
 * Absolute backend for direct calls; empty string = same-origin Vite proxy.
 * Exported (Template modeler map, ticket 01) so feature-specific API
 * modules (e.g. `templatesApi.ts`) that need raw `Response` access — blob
 * export, multipart import — don't have to re-derive it.
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  (import.meta.env.VITE_BACKEND_BASE_URL as string | undefined) ??
  'http://localhost:6840';

export type HomeStats = {
  active_process_instances: number | null;
  tasks_waiting_on_me: number | null;
  errors_needing_review: number | null;
  completed_today: number | null;
  avg_completion_minutes: number | null;
  total_tenants: number | null;
};

export type TenantSummary = {
  id: string;
  name: string;
  slug?: string;
};

export class ApiError extends Error {
  status: number;

  /** The backend's `message` from the JSON error body, when present — the
   * human-readable reason (e.g. "…lane 'Submitters' has no owners"). Callers
   * should prefer this over the generic `message` for user-facing text. */
  serverMessage?: string;

  constructor(path: string, status: number, method: string = 'GET', serverMessage?: string) {
    super(`${method} ${path} failed: ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.serverMessage = serverMessage;
  }
}

/** Best-effort read of the backend's `{ error_code, message }` error body so
 * the ApiError can carry the real reason. Clones the response so callers that
 * still want the raw body are unaffected. */
async function readServerMessage(response: Response): Promise<string | undefined> {
  try {
    const data = await response.clone().json();
    const record = data as { message?: unknown; detail?: unknown };
    const message = record?.message;
    if (typeof message === 'string' && message.trim()) {
      return message.trim();
    }
    const detail = record?.detail;
    return typeof detail === 'string' && detail.trim() ? detail.trim() : undefined;
  } catch {
    return undefined;
  }
}

// Deduped across concurrent 401s: several in-flight requests hitting an
// expired access token at once should trigger one /v1.0/refresh call, not
// one each (same pattern as m8flow-frontend's HttpService). Cleared once
// that call settles so the next expiry tries again.
let refreshInFlight: Promise<boolean> | null = null;

function attemptSilentRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/v1.0/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// Guards against firing more than one full-page redirect when several
// requests in flight all end up unauthenticated after a failed/insufficient
// refresh (e.g. the refresh token itself expired too).
let redirectingToLogin = false;

function redirectToLoginAfterFailedRefresh(): void {
  if (redirectingToLogin) {
    return;
  }
  redirectingToLogin = true;
  resumeLoginAfterLogout();
}

/**
 * Shared authenticated fetch — attaches the bearer token, and on a 401
 * transparently tries POST /v1.0/refresh (see login_controller.py) and
 * retries the request once with the refreshed access_token cookie before
 * giving up. This is what makes an expired access token invisible to the
 * user instead of surfacing as a raw "not_authenticated" error; only when
 * the refresh itself fails (or the retried request is still 401) does this
 * fall back to a full Keycloak login redirect. Mirrors m8flow-frontend's
 * HttpService.withAuthRetry/attemptSilentRefresh.
 */
async function fetchWithAuthRetry(
  path: string,
  init: RequestInit,
  alreadyRetried = false,
): Promise<Response> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (response.status !== 401) {
    return response;
  }
  if (alreadyRetried) {
    redirectToLoginAfterFailedRefresh();
    return response;
  }
  const refreshed = await attemptSilentRefresh();
  if (!refreshed) {
    redirectToLoginAfterFailedRefresh();
    return response;
  }
  return fetchWithAuthRetry(path, init, true);
}

/**
 * Shared authenticated fetch (Template modeler map, ticket 01) — attaches
 * the tenant cookie + bearer token the same way apiGet/
 * fetchProcessModelFileContent already do, but returns the raw `Response`
 * so callers can pick `.json()`/`.text()`/`.blob()` as needed (templates
 * has JSON, raw-text file-content, and binary export/import endpoints,
 * unlike the JSON-only routes apiGet was built for). Throws ApiError with
 * the real HTTP method on failure, not a hardcoded 'GET'.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetchWithAuthRetry(path, init);
  if (!response.ok) {
    throw new ApiError(path, response.status, init.method ?? 'GET', await readServerMessage(response));
  }
  return response;
}

/**
 * Concurrent identical GETs share one in-flight promise. React StrictMode
 * remounts effects in development (setup → cleanup → setup) without aborting
 * the first fetch, which would otherwise hit the backend twice for the same
 * path. Cleared when the request settles so a later load (refresh, tenant
 * change) still fetches.
 */
const inFlightGets = new Map<string, Promise<unknown>>();

/**
 * Thin authenticated GET against m8flow-backend. Uses the access_token cookie
 * as a Bearer header (same pattern as m8flow-frontend HttpService).
 */
export async function apiGet<T>(path: string): Promise<T> {
  const existing = inFlightGets.get(path);
  if (existing) {
    return existing as Promise<T>;
  }
  const request = (async () => {
    const response = await apiFetch(path, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    return (await response.json()) as T;
  })().finally(() => {
    inFlightGets.delete(path);
  });
  inFlightGets.set(path, request);
  return request;
}

const ORGANIZATION_MEMBERSHIPS_PATH = '/v1.0/m8flow/organization-memberships';

function asMembership(value: unknown): OrganizationMembership | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const alias = typeof record.alias === 'string' ? record.alias.trim() : '';
  if (!alias) {
    return null;
  }
  return {
    alias,
    id: typeof record.id === 'string' && record.id.trim() ? record.id.trim() : null,
    name: typeof record.name === 'string' && record.name.trim() ? record.name.trim() : null,
  };
}

/** Display names for the current user's shared-realm organizations. Tenant-cookie exempt. */
export async function fetchOrganizationMemberships(): Promise<OrganizationMembership[]> {
  const body = await apiGet<{ organizations?: unknown }>(ORGANIZATION_MEMBERSHIPS_PATH);
  if (!Array.isArray(body.organizations)) {
    return [];
  }
  return body.organizations.flatMap((item) => {
    const membership = asMembership(item);
    return membership ? [membership] : [];
  });
}

export function homeStatsPath(tenantId: string | null | undefined): string {
  const base = '/v1.0/m8flow/home-stats';
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

export function fetchHomeStats(tenantId: string | null | undefined): Promise<HomeStats> {
  return apiGet<HomeStats>(homeStatsPath(tenantId));
}

export function fetchTenants(): Promise<TenantSummary[]> {
  return apiGet<TenantSummary[]>('/v1.0/m8flow/tenants');
}

export type Capabilities = {
  can_manage_processes: boolean;
  can_read_secrets?: boolean;
  can_manage_secrets?: boolean;
  /** YAML connectors-grouped read (tenant-admin / editor / integrator). */
  can_read_connectors?: boolean;
  /** YAML connector-profile writes (tenant-admin / integrator). */
  can_manage_connector_profiles?: boolean;
  /** Advisory Tenant Management hint. Not the members/groups API gate. */
  can_manage_tenant?: boolean;
};

/** UI capability hints from the backend (authoritative — computed from the
 * same allow_uri gate the routes enforce). Used to show/hide Start/Delete on
 * Processes without parsing Keycloak token claims. */
export function fetchCapabilities(): Promise<Capabilities> {
  return apiGet<Capabilities>('/v1.0/m8flow/capabilities');
}

export type HomeRecentInstance = {
  id: number;
  tenant_id: string;
  tenant_name: string;
  process_model_display_name: string;
  start_in_seconds: number | null;
  status: string;
};

export function homeRecentInstancesPath(tenantId: string | null | undefined): string {
  const base = '/v1.0/m8flow/home-recent-instances';
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

export function fetchHomeRecentInstances(
  tenantId: string | null | undefined,
): Promise<HomeRecentInstance[]> {
  return apiGet<HomeRecentInstance[]>(homeRecentInstancesPath(tenantId));
}

export type HomeMyTask = {
  id: number;
  task_title: string | null;
  task_name: string;
  tenant_id: string;
  tenant_name: string;
  lane_name: string | null;
  created_at_in_seconds: number | null;
  process_instance_id: number;
};

export function homeMyTasksPath(tenantId: string | null | undefined): string {
  const base = '/v1.0/m8flow/home-my-tasks';
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

export function fetchHomeMyTasks(
  tenantId: string | null | undefined,
): Promise<HomeMyTask[]> {
  return apiGet<HomeMyTask[]>(homeMyTasksPath(tenantId));
}

export type ProcessModelListItem = {
  id: string;
  display_name: string;
  group_id: string;
  group_display_name: string;
  last_run_in_seconds: number | null;
  runs_30d: number;
};

export function processModelsPath(
  tenantId: string | null | undefined,
  group?: string | null,
): string {
  const params = new URLSearchParams();
  if (tenantId) {
    params.set('tenantId', tenantId);
  }
  if (group) {
    params.set('group', group);
  }
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/process-models?${qs}` : '/v1.0/m8flow/process-models';
}

export function fetchProcessModels(
  tenantId: string | null | undefined,
  group?: string | null,
): Promise<ProcessModelListItem[]> {
  return apiGet<ProcessModelListItem[]>(processModelsPath(tenantId, group));
}

export type ProcessGroupListItem = {
  id: string;
  display_name: string;
  description: string;
  model_count: number;
  last_run_in_seconds: number | null;
};

export function processGroupsPath(tenantId: string | null | undefined): string {
  const params = new URLSearchParams();
  if (tenantId) {
    params.set('tenantId', tenantId);
  }
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/process-groups?${qs}` : '/v1.0/m8flow/process-groups';
}

export function fetchProcessGroups(
  tenantId: string | null | undefined,
): Promise<ProcessGroupListItem[]> {
  return apiGet<ProcessGroupListItem[]>(processGroupsPath(tenantId));
}

export type ProcessGroupWriteInput = {
  id: string;
  display_name: string;
  description: string;
};

function processGroupWritePath(groupId: string, tenantId?: string | null): string {
  const encodedId = groupId.split('/').map(encodeURIComponent).join(':');
  const base = `/v1.0/m8flow/process-groups/${encodedId}`;
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

export async function createProcessGroup(
  input: ProcessGroupWriteInput,
  tenantId?: string | null,
): Promise<ProcessGroupListItem> {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-groups${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as ProcessGroupListItem;
}

export async function updateProcessGroup(
  groupId: string,
  patch: { display_name: string; description: string },
  tenantId?: string | null,
): Promise<ProcessGroupListItem> {
  const path = processGroupWritePath(groupId, tenantId);
  const response = await apiFetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return (await response.json()) as ProcessGroupListItem;
}

export async function deleteProcessGroup(
  groupId: string,
  tenantId?: string | null,
): Promise<void> {
  await apiFetch(processGroupWritePath(groupId, tenantId), { method: 'DELETE' });
}

export type ProcessModelIdentity = {
  id: string;
  display_name: string;
  description: string;
  group_id: string;
  group_display_name: string;
};

export type ProcessModelCreateInput = {
  group_id: string;
  /** Optional leaf; when omitted the host slugifies `display_name`. */
  id?: string;
  display_name: string;
  description: string;
};

export async function createProcessModel(
  input: ProcessModelCreateInput,
  tenantId?: string | null,
): Promise<ProcessModelIdentity> {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as ProcessModelIdentity;
}

export async function updateProcessModel(
  modifiedId: string,
  patch: { display_name?: string; description?: string; primary_file_name?: string },
  tenantId?: string | null,
): Promise<ProcessModelIdentity> {
  const path = processModelDetailPath(modifiedId, tenantId);
  const response = await apiFetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return (await response.json()) as ProcessModelIdentity;
}

export async function copyProcessModel(
  modifiedId: string,
  input: { id: string; display_name: string },
  tenantId?: string | null,
): Promise<ProcessModelIdentity> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/copy${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as ProcessModelIdentity;
}

export type ProcessModelTestCaseResult = {
  passed: boolean;
  bpmn_file: string;
  test_case_identifier: string;
  test_case_error_details?: { error_messages?: string[] } | null;
};

export type ProcessModelTestRunResult = {
  all_passed: boolean;
  passing: ProcessModelTestCaseResult[];
  failing: ProcessModelTestCaseResult[];
};

export async function runProcessModelTests(
  modifiedId: string,
  tenantId?: string | null,
): Promise<ProcessModelTestRunResult> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/tests/run${suffix}`;
  const response = await apiFetch(path, { method: 'POST' });
  return (await response.json()) as ProcessModelTestRunResult;
}

export type ScriptUnitTest = {
  id: string;
  bpmn_task_identifier: string;
};

export async function fetchScriptUnitTests(
  modifiedId: string,
  tenantId?: string | null,
): Promise<ScriptUnitTest[]> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/script-unit-tests${suffix}`;
  const response = await apiFetch(path);
  const body = (await response.json()) as { tests?: ScriptUnitTest[] };
  return Array.isArray(body.tests) ? body.tests : [];
}

export async function createScriptUnitTest(
  modifiedId: string,
  input: {
    bpmn_task_identifier: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  },
  tenantId?: string | null,
): Promise<{ ok: boolean; id: string }> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/script-unit-tests${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as { ok: boolean; id: string };
}

export type ScriptUnitTestRunResult = {
  result: boolean;
  context?: Record<string, unknown> | null;
  error?: string | null;
  line_number?: number | null;
};

export async function runScriptUnitTest(
  modifiedId: string,
  input: { unit_test_id?: string; python_script?: string; input_json?: Record<string, unknown>; expected_output_json?: Record<string, unknown> },
  tenantId?: string | null,
): Promise<ScriptUnitTestRunResult> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/script-unit-tests/run${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as ScriptUnitTestRunResult;
}

export type ProcessModelDetailInstance = {
  id: number;
  started_by: string;
  start_in_seconds: number | null;
  duration_seconds: number | null;
  status: string;
};

export type ProcessModelDetailFile = {
  name: string;
  size_bytes: number;
  updated_at_in_seconds: number;
  primary: boolean;
};

export type ProcessModelDetail = {
  id: string;
  display_name: string;
  description: string;
  group_id: string;
  group_display_name: string;
  last_run_in_seconds: number | null;
  running_now: number;
  runs_30d: number;
  recent_instances: ProcessModelDetailInstance[];
  files: ProcessModelDetailFile[];
};

export function processModelDetailPath(
  modifiedId: string,
  tenantId?: string | null,
): string {
  // Keep `:` as the slash stand-in. encodeURIComponent would turn it into %3A
  // and the backend path converter would look up a non-existent id.
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const base = `/v1.0/m8flow/process-models/${encodedId}`;
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

export function fetchProcessModelDetail(
  modifiedId: string,
  tenantId?: string | null,
): Promise<ProcessModelDetail> {
  return apiGet<ProcessModelDetail>(processModelDetailPath(modifiedId, tenantId));
}

export function processModelFilePath(
  modifiedId: string,
  fileName: string,
  tenantId?: string | null,
): string {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const base = `/v1.0/m8flow/process-models/${encodedId}/files/${encodeURIComponent(fileName)}`;
  if (tenantId) {
    return `${base}?tenantId=${encodeURIComponent(tenantId)}`;
  }
  return base;
}

/**
 * Raw file content (XML text) — not JSON, so this bypasses apiGet's
 * response.json() and reads text directly. Same auth/tenant pattern.
 */
export async function fetchProcessModelFileContent(
  modifiedId: string,
  fileName: string,
  tenantId?: string | null,
): Promise<string> {
  const path = processModelFilePath(modifiedId, fileName, tenantId);
  const response = await fetchWithAuthRetry(path, { method: 'GET' });
  if (!response.ok) {
    throw new ApiError(path, response.status);
  }
  return response.text();
}

export type ProcessModelFileSaveResult = {
  name: string;
  size_bytes: number;
  updated_at_in_seconds: number;
};

/** Saves raw file content back to an existing process model file. */
export async function saveProcessModelFileContent(
  modifiedId: string,
  fileName: string,
  content: string,
  tenantId?: string | null,
): Promise<ProcessModelFileSaveResult> {
  const path = processModelFilePath(modifiedId, fileName, tenantId);
  const response = await fetchWithAuthRetry(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: content,
  });
  if (!response.ok) {
    throw new ApiError(path, response.status, 'PUT');
  }
  return (await response.json()) as ProcessModelFileSaveResult;
}

export async function createProcessModelFile(
  modifiedId: string,
  input: { file_name: string; content?: string },
  tenantId?: string | null,
): Promise<ProcessModelFileSaveResult> {
  const encodedId = modifiedId.split(':').map(encodeURIComponent).join(':');
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${encodedId}/files${suffix}`;
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return (await response.json()) as ProcessModelFileSaveResult;
}

export async function deleteProcessModelFile(
  modifiedId: string,
  fileName: string,
  tenantId?: string | null,
): Promise<void> {
  const path = processModelFilePath(modifiedId, fileName, tenantId);
  await apiFetch(path, { method: 'DELETE' });
}

export type StartProcessInstanceResult = {
  id: number;
  status: string;
  process_model_identifier: string;
};

/** Starts a process instance from a model's latest definition (Processes
 * list/detail "Start" action). POST /process-models/{id}/start. */
export async function startProcessInstance(
  modifiedId: string,
  tenantId?: string | null,
): Promise<StartProcessInstanceResult> {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${modifiedId}/start${suffix}`;
  const response = await apiFetch(path, { method: 'POST' });
  return (await response.json()) as StartProcessInstanceResult;
}

/** Deletes a process model's on-disk spec. The backend returns 409 when the
 * model still has instances — surfaced to the caller as an ApiError(status
 * 409) so the confirmation dialog can explain why. */
export async function deleteProcessModel(
  modifiedId: string,
  tenantId?: string | null,
): Promise<void> {
  const suffix = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
  const path = `/v1.0/m8flow/process-models/${modifiedId}${suffix}`;
  await apiFetch(path, { method: 'DELETE' });
}

/**
 * One operation within a connector group, as m8flow_backend's
 * connectors_controller.connectors_grouped returns it. `parameters` comes
 * from the connector proxy's `/v1/commands` catalog (via the host
 * ServiceTaskRegistry) — distinct from connector-level `configFields`, used
 * for the Connectors "Configure" form's secrets. Read by
 * ServiceTaskOperatorSelect (bpmn-js-spiffworkflow) to render each service
 * task operator's parameter inputs.
 */
export type ConnectorOperation = {
  id: string;
  name: string;
  rawName: string;
  description: string;
  parameters: { id: string; type: string }[];
};

export type ConnectorGroup = {
  id: string;
  name: string;
  description: string;
  status: string;
  icon: string;
  operationCount: number;
  operations: ConnectorOperation[];
  docsUrl?: string;
  /** When true, Configure opens connector profiles instead of Configuration secrets. */
  supportsProfiles?: boolean;
};

/** Not tenant-scoped — connectors are platform-level, same as the Connectors page. */
export function fetchConnectorsGrouped(): Promise<ConnectorGroup[]> {
  return apiGet<ConnectorGroup[]>('/v1.0/m8flow/connectors-grouped');
}
