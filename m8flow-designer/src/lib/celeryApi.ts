import { apiGet, apiPost } from './api';

/**
 * Celery monitoring and control (super-admin only; the backend's `/m8flow/celery/*`
 * permissions are the enforcement layer). Shapes mirror `celery_monitoring_controller.py`.
 * The backend caches one inspect round for a few seconds, so the live calls a refresh
 * makes cost the broker one broadcast round.
 */
const BASE_PATH = '/v1.0/m8flow/celery';

export type CeleryQueue = {
  name: string;
  /** Messages waiting for a worker; null when the broker is not Redis. */
  messages: number | null;
  /** Workers consuming this queue. */
  consumers: string[];
};

export type CeleryOverview = {
  workersOnline: number;
  /** Seen in task history in the last 24 hours, no longer answering. */
  workersOffline: number;
  concurrency: number;
  tasksRunning: number;
  /** Prefetched by a worker, waiting for a free process. */
  tasksReserved: number;
  /** Waiting for an ETA or countdown. */
  tasksScheduled: number;
  /** Since each worker started; resets when a worker restarts. */
  tasksProcessed: number;
  queues: CeleryQueue[];
  unacked: number | null;
  history: { windowHours: number; succeeded: number; failed: number; retried: number; revoked: number };
  historyEnabled: boolean;
  controlEnabled: boolean;
  transport: string | null;
  capturedAt: string | null;
};

export type CeleryConfigEntry = { key: string; value: string };

/** Offline workers carry only `name`, `online` and `lastSeenAt`. */
export type CeleryWorker = {
  name: string;
  online: boolean;
  lastSeenAt: string | null;
  pid?: number | null;
  uptimeSeconds?: number;
  pool?: string | null;
  concurrency?: number;
  processes?: number;
  maxTasksPerChild?: number | null;
  softTimeLimitSeconds?: number | null;
  hardTimeLimitSeconds?: number | null;
  autoscaleMin?: number | null;
  autoscaleMax?: number | null;
  prefetchCount?: number;
  tasksProcessed?: number;
  tasksProcessedByName?: Record<string, number>;
  queues?: string[];
  registeredTasks?: string[];
  running?: number;
  reserved?: number;
  scheduled?: number;
  system?: Record<string, number>;
  conf?: CeleryConfigEntry[];
};

export type CeleryTask = {
  id: string;
  name: string;
  worker: string;
  queue: string | null;
  startedAt: string | null;
  eta: string | null;
  acknowledged: boolean;
  /** Revoked, but the worker has not dropped it yet. */
  revoked: boolean;
  /** Redacted, truncated JSON preview. */
  args: string;
  /** Redacted, truncated JSON preview. */
  kwargs: string;
};

export type CeleryTasks = {
  active: CeleryTask[];
  reserved: CeleryTask[];
  scheduled: CeleryTask[];
  revoked: string[];
  capturedAt: string | null;
};

export type CeleryBroker = {
  queues: CeleryQueue[];
  unacked: number | null;
  transport: string | null;
  capturedAt: string | null;
};

export const CELERY_TASK_STATES = ['RECEIVED', 'STARTED', 'SUCCESS', 'FAILURE', 'RETRY', 'REVOKED'] as const;
export type CeleryTaskState = (typeof CELERY_TASK_STATES)[number];

export type CeleryHistoryTask = {
  taskId: string;
  name: string | null;
  state: CeleryTaskState;
  worker: string | null;
  queue: string | null;
  tenantId: string | null;
  args: string;
  kwargs: string;
  retries: number;
  receivedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  runtimeSeconds: number | null;
  updatedAt: string | null;
  exception: string | null;
  /** Detail only. */
  result?: string | null;
  traceback?: string | null;
  eta?: string | null;
  expires?: string | null;
  parentId?: string | null;
  rootId?: string | null;
};

export type CeleryHistoryPage = {
  results: CeleryHistoryTask[];
  pagination: { page: number; perPage: number; total: number; pages: number };
};

export type CeleryHistoryFilters = {
  state?: CeleryTaskState | null;
  name?: string | null;
  worker?: string | null;
  search?: string | null;
  windowHours?: number | null;
  page?: number;
  perPage?: number;
};

export type CeleryTaskType = {
  name: string;
  total: number;
  succeeded: number;
  failed: number;
  retried: number;
  revoked: number;
  running: number;
  avgRuntimeSeconds: number | null;
  maxRuntimeSeconds: number | null;
  lastSeenAt: string | null;
};

export type CeleryControlResult = {
  ok: boolean;
  message: string | null;
  results: { worker: string; ok: boolean; message: string }[];
};

export type CeleryWorkerAction =
  | { action: 'pool_grow' | 'pool_shrink'; n: number }
  | { action: 'autoscale'; min: number; max: number }
  | { action: 'add_consumer' | 'cancel_consumer'; queue: string }
  | { action: 'pool_restart' | 'shutdown' };

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

export function fetchCeleryOverview(): Promise<CeleryOverview> {
  return apiGet<CeleryOverview>(`${BASE_PATH}/overview`);
}

export function fetchCeleryWorkers(): Promise<CeleryWorker[]> {
  return apiGet<{ results: CeleryWorker[] }>(`${BASE_PATH}/workers`).then((response) => response.results ?? []);
}

export function fetchCeleryTasks(): Promise<CeleryTasks> {
  return apiGet<CeleryTasks>(`${BASE_PATH}/tasks`);
}

export function fetchCeleryBroker(): Promise<CeleryBroker> {
  return apiGet<CeleryBroker>(`${BASE_PATH}/broker`);
}

export function fetchCeleryHistory(filters: CeleryHistoryFilters): Promise<CeleryHistoryPage> {
  return apiGet<CeleryHistoryPage>(`${BASE_PATH}/history${query(filters)}`);
}

export function fetchCeleryHistoryTask(taskId: string): Promise<CeleryHistoryTask> {
  return apiGet<CeleryHistoryTask>(`${BASE_PATH}/history/${encodeURIComponent(taskId)}`);
}

export function fetchCeleryTaskTypes(windowHours: number | null): Promise<CeleryTaskType[]> {
  return apiGet<{ results: CeleryTaskType[] }>(`${BASE_PATH}/task-types${query({ windowHours })}`).then(
    (response) => response.results ?? [],
  );
}

export function revokeCeleryTask(body: { taskId: string; terminate: boolean; signal?: string }): Promise<CeleryControlResult> {
  return apiPost<CeleryControlResult>(`${BASE_PATH}/control/revoke`, body);
}

export function setCeleryRateLimit(taskName: string, rateLimit: string): Promise<CeleryControlResult> {
  return apiPost<CeleryControlResult>(`${BASE_PATH}/control/rate-limit`, { taskName, rateLimit });
}

export function setCeleryTimeLimit(
  taskName: string,
  softSeconds: number | null,
  hardSeconds: number | null,
): Promise<CeleryControlResult> {
  return apiPost<CeleryControlResult>(`${BASE_PATH}/control/time-limit`, { taskName, softSeconds, hardSeconds });
}

export function sendCeleryWorkerAction(worker: string, body: CeleryWorkerAction): Promise<CeleryControlResult> {
  return apiPost<CeleryControlResult>(`${BASE_PATH}/control/workers/${encodeURIComponent(worker)}`, body);
}
