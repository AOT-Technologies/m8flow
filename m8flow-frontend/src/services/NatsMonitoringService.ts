import HttpService from "@spiffworkflow-frontend/services/HttpService";

const BASE_PATH = "/v1.0/m8flow/nats";

/** Server health and throughput, plus JetStream totals. Super-admin only. */
export interface NatsJetStreamTotals {
  memoryBytes: number;
  storageBytes: number;
  totalStreams: number;
  totalConsumers: number;
  totalMessages: number;
  totalBytes: number;
}

export interface NatsOverview {
  healthy: boolean;
  status: string;
  serverName: string | null;
  serverId: string | null;
  version: string | null;
  uptime: string | null;
  startedAt: string | null;
  connections: number;
  totalConnections: number;
  subscriptions: number;
  inMsgs: number;
  outMsgs: number;
  inBytes: number;
  outBytes: number;
  slowConsumers: number;
  memoryBytes: number;
  cpuPercent: number;
  jetstream: NatsJetStreamTotals;
}

export interface NatsConsumer {
  name: string | null;
  streamName: string | null;
  filterSubject: string | string[] | null;
  /** Messages this consumer still owes work on. The authoritative backlog figure. */
  pending: number;
  /** Delivered but not yet acknowledged. */
  unacked: number;
  /**
   * Sequence distance from the head of the stream. For a consumer with a filter subject
   * this OVERSTATES the backlog because it counts messages on subjects the consumer will
   * never receive — prefer `pending`. Useful only as a "parked far behind the head" signal.
   */
  streamLag: number;
  ackLag: number;
  redelivered: number;
  waiting: number;
  deliveredStreamSeq: number;
  deliveredConsumerSeq: number;
  ackFloorStreamSeq: number;
  lastActive: string | null;
  createdAt: string | null;
}

export interface NatsStream {
  name: string | null;
  account: string | null;
  subjects: string[];
  /** True for JetStream plumbing exposed as a stream: KV buckets and object stores. */
  isInternal: boolean;
  messages: number;
  bytes: number;
  firstSeq: number;
  lastSeq: number;
  numSubjects: number;
  numDeleted: number;
  consumerCount: number;
  createdAt: string | null;
  consumers: NatsConsumer[];
}

export interface NatsStreamTotals {
  streams: number;
  consumers: number;
  messages: number;
  bytes: number;
  pending: number;
  unacked: number;
  redelivered: number;
  internalStreams: number;
}

export interface NatsStreamsResponse {
  streams: NatsStream[];
  totals: NatsStreamTotals;
  jetstream: NatsJetStreamTotals;
}

export interface NatsTenantEventCounts {
  tenantId: string | null;
  tenantSlug: string | null;
  queued: number;
  instantiated: number;
  failed: number;
  total: number;
  lastActivityInSeconds: number;
}

export type NatsEventOutcome =
  | "queued"
  | "instantiated"
  | "duplicate"
  | "invalid_payload"
  | "rejected_auth"
  | "rejected_scope"
  | "tenant_mismatch"
  | "user_not_found"
  | "model_not_found"
  | "transient_error";

export const NATS_EVENT_OUTCOMES: NatsEventOutcome[] = [
  "queued",
  "instantiated",
  "duplicate",
  "invalid_payload",
  "rejected_auth",
  "rejected_scope",
  "tenant_mismatch",
  "user_not_found",
  "model_not_found",
  "transient_error",
];

/** Outcomes where the message never produced a process instance. */
export const NATS_FAILURE_OUTCOMES: NatsEventOutcome[] = [
  "invalid_payload",
  "rejected_auth",
  "rejected_scope",
  "tenant_mismatch",
  "user_not_found",
  "model_not_found",
  "transient_error",
];

export interface NatsStreamMessage {
  seq: number;
  subject: string | null;
  time: string | null;
  sizeBytes: number;
  payload: string;
  /** "utf-8", or "base64" for a binary payload. */
  encoding: string;
  truncated: boolean;
  headers: Record<string, string>;
}

export interface NatsEventRecord {
  id: number;
  tenantId: string | null;
  eventId: string | null;
  worker: string;
  /** Pointer into JetStream; payloads are never copied into the database. */
  streamSeq: number | null;
  processIdentifier: string | null;
  username: string | null;
  outcome: NatsEventOutcome;
  /** Extra deliveries of this same event id suppressed by the dedup guard. */
  duplicateCount: number;
  errorMessage: string | null;
  processInstanceId: number | null;
  queuedAtInSeconds: number;
  completedAtInSeconds: number | null;
  updatedAtInSeconds: number;
  payload?: NatsStreamMessage | null;
}

export interface NatsEventListResponse {
  results: NatsEventRecord[];
  pagination: {
    page: number;
    perPage: number;
    total: number;
    pages: number;
  };
}

export interface NatsEventSummary {
  byOutcome: Partial<Record<NatsEventOutcome, number>>;
  total: number;
  queued: number;
  instantiated: number;
  failed: number;
  duplicateDeliveries: number;
}

export interface NatsEventFilters {
  outcome?: string;
  processIdentifier?: string;
  username?: string;
  eventId?: string;
  worker?: string;
  failuresOnly?: boolean;
  since?: number;
  until?: number;
  allTenants?: boolean;
  tenantId?: string;
  page?: number;
  perPage?: number;
}

function queryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === false) {
      return;
    }
    search.append(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

function get<T>(path: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    HttpService.makeCallToBackend({
      path: `${BASE_PATH}${path}`,
      httpMethod: "GET",
      successCallback: resolve,
      // Pass failures through rather than letting HttpService alert(): a 503 from a broker
      // that is simply switched off is an expected state this page renders itself.
      failureCallback: reject,
      onUnauthorized: reject,
    });
  });
}

const NatsMonitoringService = {
  getOverview: (): Promise<NatsOverview> => get<NatsOverview>("/overview"),

  getStreams: (): Promise<NatsStreamsResponse> => get<NatsStreamsResponse>("/streams"),

  getTenants: (): Promise<NatsTenantEventCounts[]> =>
    get<{ results: NatsTenantEventCounts[] }>("/tenants").then((r) => r.results ?? []),

  getEvents: (filters: NatsEventFilters = {}): Promise<NatsEventListResponse> =>
    get<NatsEventListResponse>(`/events${queryString(filters as Record<string, unknown>)}`),

  getEventSummary: (
    filters: Pick<NatsEventFilters, "allTenants" | "tenantId"> = {},
  ): Promise<NatsEventSummary> =>
    get<NatsEventSummary>(
      `/events/summary${queryString(filters as Record<string, unknown>)}`,
    ),

  getEvent: (
    eventId: string,
    options: {
      includePayload?: boolean;
      // No streamName: the backend derives the stream from the audit row's worker, so both
      // halves of the JetStream pointer come from the row the caller is authorized for.
      allTenants?: boolean;
      tenantId?: string;
    } = {},
  ): Promise<NatsEventRecord> =>
    get<NatsEventRecord>(
      `/events/${encodeURIComponent(eventId)}${queryString(options as Record<string, unknown>)}`,
    ),

  getStreamMessages: (
    streamName: string,
    options: { startSeq?: number; limit?: number } = {},
  ): Promise<NatsStreamMessage[]> =>
    get<{ results: NatsStreamMessage[] }>(
      `/streams/${encodeURIComponent(streamName)}/messages${queryString(
        options as Record<string, unknown>,
      )}`,
    ).then((r) => r.results ?? []),
};

export default NatsMonitoringService;
