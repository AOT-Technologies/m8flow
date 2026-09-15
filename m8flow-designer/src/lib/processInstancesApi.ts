import { apiFetch, apiGet } from './api';

/**
 * Client for m8flow-backend's `/v1.0/m8flow/process-instances*` routes
 * (Process Instances + task-state map, ticket 02 —
 * `.scratch/process-instances-task-state/`, backend built in ticket 01).
 * Response shapes read directly from `process_instances_controller.py`/
 * `workflow.list_instances_for_designer`/`get_instance_detail_for_
 * designer`, snake_case (unlike Templates' camelCase) — same convention
 * as this app's other `/v1.0/m8flow/*` routes (`ProcessModelListItem`,
 * `HomeRecentInstance`, etc. in `lib/api.ts`).
 */

export type ProcessInstanceListItem = {
  id: number;
  process_model_identifier: string;
  process_model_display_name: string;
  status: string;
  started_by: string;
  start_in_seconds: number | null;
  end_in_seconds: number | null;
};

export type ProcessInstancePagination = {
  count: number;
  total: number;
  pages: number;
};

export type ProcessInstanceListResponse = {
  results: ProcessInstanceListItem[];
  pagination: ProcessInstancePagination;
};

/** Allowlisted server sort keys — must mirror workflow.py's
 * `_INSTANCE_SORTS`. Kept as a union so the UI's sort <select> can't emit
 * a value the backend would silently ignore. */
export type ProcessInstanceSort = 'newest' | 'oldest' | 'recent_start' | 'status';

export type ProcessInstanceListFilters = {
  status?: string;
  search?: string;
  /** Exact initiator-username match; options from fetchProcessInstanceOwners. */
  startedBy?: string;
  sort?: ProcessInstanceSort;
  page?: number;
  perPage?: number;
  /** Super-admin only; same convention as fetchProcessModels/fetchTemplates. */
  tenantId?: string | null;
};

export function processInstancesPath(filters: ProcessInstanceListFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.search) params.set('search', filters.search);
  if (filters.startedBy) params.set('started_by', filters.startedBy);
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.perPage !== undefined) params.set('per_page', String(filters.perPage));
  if (filters.tenantId) params.set('tenantId', filters.tenantId);
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/process-instances?${qs}` : '/v1.0/m8flow/process-instances';
}

export function fetchProcessInstances(
  filters: ProcessInstanceListFilters = {},
): Promise<ProcessInstanceListResponse> {
  return apiGet<ProcessInstanceListResponse>(processInstancesPath(filters));
}

export type ProcessInstanceOwnersResponse = { owners: string[] };

export function processInstanceOwnersPath(tenantId?: string | null): string {
  const base = '/v1.0/m8flow/process-instances/owners';
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

/** Distinct initiator usernames for the "started by" filter dropdown. */
export function fetchProcessInstanceOwners(tenantId?: string | null): Promise<string[]> {
  return apiGet<ProcessInstanceOwnersResponse>(processInstanceOwnersPath(tenantId)).then(
    (r) => r.owners ?? [],
  );
}

export type ProcessInstanceTaskState = {
  bpmn_identifier: string;
  state: string;
};

export type ProcessInstanceDetail = {
  id: number;
  process_model_identifier: string;
  process_model_display_name: string;
  status: string;
  started_by: string;
  start_in_seconds: number | null;
  end_in_seconds: number | null;
  updated_at_in_seconds: number | null;
  last_milestone_bpmn_name: string | null;
  bpmn_xml: string | null;
  tasks: ProcessInstanceTaskState[];
};

export function processInstanceDetailPath(id: number, tenantId?: string | null): string {
  const base = `/v1.0/m8flow/process-instances/${id}`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export function fetchProcessInstanceDetail(
  id: number,
  tenantId?: string | null,
): Promise<ProcessInstanceDetail> {
  return apiGet<ProcessInstanceDetail>(processInstanceDetailPath(id, tenantId));
}

export type ProcessInstanceEventRow = {
  id: number;
  bpmn_process: string | null;
  task_name: string | null;
  task_identifier: string | null;
  task_type: string | null;
  event_type: string;
  user: string;
  timestamp: number | null;
};

export type ProcessInstanceEventsResponse = {
  results: ProcessInstanceEventRow[];
};

export function processInstanceEventsPath(id: number, tenantId?: string | null): string {
  const base = `/v1.0/m8flow/process-instances/${id}/events`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export function fetchProcessInstanceEvents(
  id: number,
  tenantId?: string | null,
): Promise<ProcessInstanceEventRow[]> {
  return apiGet<ProcessInstanceEventsResponse>(processInstanceEventsPath(id, tenantId)).then(
    (r) => r.results ?? [],
  );
}

export type ProcessInstanceMilestoneRow = {
  milestone: string;
  bpmn_process: string | null;
  timestamp: number | null;
};

export type ProcessInstanceMilestonesResponse = {
  results: ProcessInstanceMilestoneRow[];
};

export function processInstanceMilestonesPath(id: number, tenantId?: string | null): string {
  const base = `/v1.0/m8flow/process-instances/${id}/milestones`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export function fetchProcessInstanceMilestones(
  id: number,
  tenantId?: string | null,
): Promise<ProcessInstanceMilestoneRow[]> {
  return apiGet<ProcessInstanceMilestonesResponse>(processInstanceMilestonesPath(id, tenantId)).then(
    (r) => r.results ?? [],
  );
}

export type ProcessInstanceCompletableTaskRow = {
  id: number;
  task_title: string | null;
  task_name: string;
  lane_name: string | null;
};

export type ProcessInstanceCompletableTasksResponse = {
  results: ProcessInstanceCompletableTaskRow[];
};

export function processInstanceCompletableTasksPath(id: number, tenantId?: string | null): string {
  const base = `/v1.0/m8flow/process-instances/${id}/completable-tasks`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export function fetchProcessInstanceCompletableTasks(
  id: number,
  tenantId?: string | null,
): Promise<ProcessInstanceCompletableTaskRow[]> {
  return apiGet<ProcessInstanceCompletableTasksResponse>(
    processInstanceCompletableTasksPath(id, tenantId),
  ).then((r) => r.results ?? []);
}

export type ProcessInstanceCompletedTaskRow = {
  id: number;
  task_title: string | null;
  task_name: string;
  completed_by: string | null;
  timestamp: number | null;
};

export type ProcessInstanceCompletedTasksResponse = {
  completed_by_me: ProcessInstanceCompletedTaskRow[];
  all_completed: ProcessInstanceCompletedTaskRow[];
};

export function processInstanceCompletedTasksPath(id: number, tenantId?: string | null): string {
  const base = `/v1.0/m8flow/process-instances/${id}/completed-tasks`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export function fetchProcessInstanceCompletedTasks(
  id: number,
  tenantId?: string | null,
): Promise<ProcessInstanceCompletedTasksResponse> {
  return apiGet<ProcessInstanceCompletedTasksResponse>(
    processInstanceCompletedTasksPath(id, tenantId),
  ).then((r) => ({
    completed_by_me: r.completed_by_me ?? [],
    all_completed: r.all_completed ?? [],
  }));
}

export type ProcessInstanceLifecycleAction = 'suspend' | 'resume' | 'terminate';

export type ProcessInstanceLifecycleResult = {
  id: number;
  status: string;
};

export function processInstanceLifecyclePath(
  id: number,
  action: ProcessInstanceLifecycleAction,
  tenantId?: string | null,
): string {
  const base = `/v1.0/m8flow/process-instances/${id}/${action}`;
  return tenantId ? `${base}?tenantId=${encodeURIComponent(tenantId)}` : base;
}

export async function postProcessInstanceLifecycle(
  id: number,
  action: ProcessInstanceLifecycleAction,
  tenantId?: string | null,
): Promise<ProcessInstanceLifecycleResult> {
  const path = processInstanceLifecyclePath(id, action, tenantId);
  const response = await apiFetch(path, { method: 'POST' });
  return (await response.json()) as ProcessInstanceLifecycleResult;
}
