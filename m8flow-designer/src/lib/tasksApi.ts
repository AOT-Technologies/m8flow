import { apiFetch, apiGet } from './api';

/**
 * Client for m8flow-backend's `/v1.0/m8flow/task-review*` routes (the Task
 * Review inbox + composite detail + submit). Response shapes read directly
 * from `routes/task_review_controller.py` and the frozen contract
 * (`.scratch/task-review/assets/03-api-contract.md`), snake_case like the
 * app's other `/v1.0/m8flow/*` clients. Timestamps are epoch seconds; the
 * backend resolves user ids to display names (never leaks ids) and returns
 * raw `event_type` enums — this app owns the wording/formatting.
 */

// ---------------------------------------------------------------------------
// Inbox list
// ---------------------------------------------------------------------------

export type TaskReviewListItem = {
  /** human_task id — the detail route key (`/task-review/:taskId`). */
  id: number;
  task_title: string | null;
  task_name: string;
  process_model_display_name: string;
  process_instance_id: number;
  /** Process initiator display name, or null. */
  submitted_by: string | null;
  /** Raw task status enum (e.g. READY / CLAIMED). */
  status: string;
  created_at_in_seconds: number | null;
  /** Tenant name (present for the super-admin cross-tenant view). */
  tenant_name: string | null;
};

export type TaskReviewPagination = {
  page: number;
  per_page: number;
  total: number;
};

export type TaskReviewListResponse = {
  results: TaskReviewListItem[];
  pagination: TaskReviewPagination;
};

export type TaskReviewListFilters = {
  page?: number;
  perPage?: number;
  /** Super-admin only; same convention as fetchProcessInstances. */
  tenantId?: string | null;
};

export function taskReviewListPath(filters: TaskReviewListFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.perPage !== undefined) params.set('per_page', String(filters.perPage));
  if (filters.tenantId) params.set('tenantId', filters.tenantId);
  const qs = params.toString();
  return qs ? `/v1.0/m8flow/task-review?${qs}` : '/v1.0/m8flow/task-review';
}

export function fetchTaskReviewList(
  filters: TaskReviewListFilters = {},
): Promise<TaskReviewListResponse> {
  return apiGet<TaskReviewListResponse>(taskReviewListPath(filters));
}

// ---------------------------------------------------------------------------
// Composite detail
// ---------------------------------------------------------------------------

/** Raw `event_type` enum from core's ProcessInstanceEventModel. Known values
 * listed for autocomplete; `(string & {})` keeps it open to ones core adds. */
export type TaskReviewEventType =
  | 'process_instance_created'
  | 'process_instance_completed'
  | 'task_completed'
  | 'task_failed'
  | 'task_cancelled'
  | (string & {});

export type TaskReviewTaskHeader = {
  id: number;
  task_title: string | null;
  task_name: string;
  task_type: string;
  status: string;
  completed: boolean;
  process_model_display_name: string;
  bpmn_process_identifier: string;
  submitted_by: string | null;
  created_at_in_seconds: number | null;
};

/** Editable form for the review task: JSON schema + optional ui-schema +
 * the initial values, rendered as an editable form the reviewer fills in. */
export type TaskReviewForm = {
  schema: Record<string, unknown>;
  ui_schema: Record<string, unknown> | null;
  values: Record<string, unknown>;
};

/** One reviewer outcome, derived from the BPMN gateway flows. `value` is the
 * reserved `outcome` variable value; `label` is the flow name. `[]` = a
 * linear task (render a single generic Submit). */
export type TaskReviewOutcome = {
  value: string;
  label: string;
};

export type TaskReviewApprovalNode = {
  /** Owner/completer display name, or null for system-completed tasks. */
  name: string | null;
  status: string;
  completed: boolean;
  is_current: boolean;
  lane_name: string | null;
  completed_at_in_seconds: number | null;
};

export type TaskReviewActivityEvent = {
  event_type: TaskReviewEventType;
  /** Actor display name, or null for system events. */
  actor_name: string | null;
  timestamp: number;
  task_guid: string | null;
  task_title: string | null;
};

export type TaskReviewInstanceSummary = {
  id: number;
  status: string | null;
  start_in_seconds: number | null;
  last_milestone_bpmn_name: string | null;
  /** Frontend route to the full process-instance detail. */
  detail_path: string;
};

export type TaskReviewDetail = {
  task: TaskReviewTaskHeader;
  form: TaskReviewForm;
  outcomes: TaskReviewOutcome[];
  approval_chain: TaskReviewApprovalNode[];
  activity: TaskReviewActivityEvent[];
  instance: TaskReviewInstanceSummary;
};

/** Detail is scoped by the `m8flow_selected_tenant` cookie server-side
 * (no `tenantId` query param, unlike the list). */
export function taskReviewDetailPath(taskId: number): string {
  return `/v1.0/m8flow/task-review/${taskId}`;
}

export function fetchTaskReviewDetail(taskId: number): Promise<TaskReviewDetail> {
  return apiGet<TaskReviewDetail>(taskReviewDetailPath(taskId));
}

// ---------------------------------------------------------------------------
// Submit (atomic claim-then-complete)
// ---------------------------------------------------------------------------

/**
 * Submit body: the filled-in task-form values plus, for a gateway task, the
 * reserved `outcome` value. The form fields come straight from the task's JSON
 * schema, so the payload is open-ended (`Record<string, unknown>`).
 */
export type SubmitTaskReviewPayload = { outcome?: string } & Record<string, unknown>;

export type SubmitTaskReviewResponse = {
  process_instance_id: number;
  /** The process instance's status after the task completed (e.g. "complete",
   * "user_input_required" when the workflow advanced to its next step). */
  process_status: string | null;
  /** True only when the whole process finished (status === "complete"). */
  process_complete: boolean;
  /** Human-readable success message ("Task completed. …"). */
  message: string;
};

export function taskReviewSubmitPath(taskId: number): string {
  return `/v1.0/m8flow/task-review/${taskId}/submit`;
}

export async function submitTaskReview(
  taskId: number,
  payload: SubmitTaskReviewPayload = {},
): Promise<SubmitTaskReviewResponse> {
  const response = await apiFetch(taskReviewSubmitPath(taskId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as SubmitTaskReviewResponse;
}
