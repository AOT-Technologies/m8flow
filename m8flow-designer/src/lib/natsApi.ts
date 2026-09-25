import { apiGet } from './api';

/**
 * Read-only NATS JetStream monitoring (super-admin only; the backend's
 * `/m8flow/nats/*` permission is the enforcement layer). Shapes mirror
 * `nats_monitoring_controller.py`.
 */
const BASE_PATH = '/v1.0/m8flow/nats';

export type NatsJetStreamTotals = {
  memoryBytes: number;
  storageBytes: number;
  totalStreams: number;
  totalConsumers: number;
  totalMessages: number;
  totalBytes: number;
};

/** What the page reads from /overview: health for the Connected badge. */
export type NatsOverview = {
  healthy: boolean;
};

export type NatsConsumer = {
  name: string | null;
  filterSubject: string | string[] | null;
  /** Messages this consumer still owes work on — the authoritative backlog. */
  pending: number;
  /** Delivered but not yet acknowledged. */
  unacked: number;
  /** Distance from the stream head; overstates backlog for filtered consumers — prefer `pending`. */
  streamLag: number;
  redelivered: number;
  waiting: number;
  deliveredStreamSeq: number;
  ackFloorStreamSeq: number;
  lastActive: string | null;
};

/** Configured limits/policies; limits use NATS's -1 = unlimited, maxAgeSeconds 0 = forever. */
export type NatsStreamConfig = {
  retention: string | null;
  storage: string | null;
  replicas: number;
  maxAgeSeconds: number;
  maxMsgs: number;
  maxBytes: number;
  maxMsgSize: number;
  maxMsgsPerSubject: number;
  maxConsumers: number;
  discard: string | null;
  duplicateWindowSeconds: number;
  compression: string | null;
  sealed: boolean;
  denyDelete: boolean;
  denyPurge: boolean;
};

export type NatsStream = {
  name: string | null;
  subjects: string[];
  /** JetStream plumbing (KV buckets, object stores) exposed as a stream. */
  isInternal: boolean;
  messages: number;
  bytes: number;
  firstSeq: number;
  lastSeq: number;
  numSubjects: number;
  numDeleted: number;
  consumerCount: number;
  createdAt: string | null;
  /** Oldest / newest retained message. */
  firstTs: string | null;
  lastTs: string | null;
  config?: NatsStreamConfig;
  consumers: NatsConsumer[];
};

export type NatsStreamsResponse = {
  streams: NatsStream[];
  totals: {
    streams: number;
    consumers: number;
    messages: number;
    bytes: number;
    pending: number;
    unacked: number;
    redelivered: number;
    internalStreams: number;
  };
  jetstream: NatsJetStreamTotals;
};

export type NatsStreamMessage = {
  seq: number;
  subject: string | null;
  time: string | null;
  sizeBytes: number;
  payload: string;
  /** "utf-8", or "base64" for a binary payload. */
  encoding: string;
  truncated: boolean;
};

export type NatsTenantEventCounts = {
  tenantId: string | null;
  tenantSlug: string | null;
  queued: number;
  instantiated: number;
  failed: number;
  total: number;
  lastActivityInSeconds: number;
};

export const NATS_EVENT_OUTCOMES = [
  'queued',
  'instantiated',
  'duplicate',
  'invalid_payload',
  'rejected_auth',
  'rejected_scope',
  'tenant_mismatch',
  'user_not_found',
  'model_not_found',
  'transient_error',
] as const;

export type NatsEventOutcome = (typeof NATS_EVENT_OUTCOMES)[number];

export type NatsEventRecord = {
  id: number;
  tenantId: string | null;
  eventId: string | null;
  /** "consumer" (trigger events) | "notification_worker" | "manual". */
  worker: string;
  /** JetStream stream the event was consumed from (derived server-side from worker). */
  streamName: string;
  streamSeq: number | null;
  processIdentifier: string | null;
  username: string | null;
  outcome: NatsEventOutcome;
  duplicateCount: number;
  errorMessage: string | null;
  processInstanceId: number | null;
  queuedAtInSeconds: number;
  completedAtInSeconds: number | null;
  payload?: NatsStreamMessage | null;
};

export type NatsEventListResponse = {
  /** M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED; payload reads 403 when false. */
  messageInspectionEnabled: boolean;
  results: NatsEventRecord[];
  pagination: { page: number; perPage: number; total: number; pages: number };
};

export type NatsEventSummary = {
  total: number;
  queued: number;
  instantiated: number;
  failed: number;
  duplicateDeliveries: number;
};

/**
 * Whose events to read. `tenantId` picks one tenant and `allTenants` asks for every
 * tenant -- both are super-admin options the backend ignores for anyone else, who is
 * always pinned to their active tenant. Send neither for "my tenant".
 */
export type NatsEventScope = { tenantId: string | null; allTenants?: boolean };

export type NatsEventFilters = NatsEventScope & {
  outcome?: string;
  processIdentifier?: string;
  eventId?: string;
  worker?: string;
  failuresOnly?: boolean;
  page: number;
  perPage: number;
};

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    search.append(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

function scopeParams({ tenantId, allTenants }: NatsEventScope) {
  if (tenantId) return { tenantId };
  return allTenants ? { allTenants: true } : {};
}

export function fetchNatsOverview(): Promise<NatsOverview> {
  return apiGet<NatsOverview>(`${BASE_PATH}/overview`);
}

export function fetchNatsStreams(): Promise<NatsStreamsResponse> {
  return apiGet<NatsStreamsResponse>(`${BASE_PATH}/streams`);
}

export function fetchNatsTenants(): Promise<NatsTenantEventCounts[]> {
  return apiGet<{ results: NatsTenantEventCounts[] }>(`${BASE_PATH}/tenants`).then(
    (response) => response.results ?? [],
  );
}

export function fetchNatsEvents({ tenantId, allTenants, ...filters }: NatsEventFilters): Promise<NatsEventListResponse> {
  return apiGet<NatsEventListResponse>(
    `${BASE_PATH}/events${query({ ...filters, ...scopeParams({ tenantId, allTenants }) })}`,
  );
}

export function fetchNatsEventSummary(scope: NatsEventScope): Promise<NatsEventSummary> {
  return apiGet<NatsEventSummary>(`${BASE_PATH}/events/summary${query(scopeParams(scope))}`);
}

/** One event with its JetStream payload (the backend derives stream + seq from the audit row). */
export function fetchNatsEventPayload(eventId: string, scope: NatsEventScope): Promise<NatsEventRecord> {
  return apiGet<NatsEventRecord>(
    `${BASE_PATH}/events/${encodeURIComponent(eventId)}${query({ includePayload: true, ...scopeParams(scope) })}`,
  );
}
