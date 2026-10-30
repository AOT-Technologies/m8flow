# M8Flow NATS Consumer

Standalone Python service that bridges NATS JetStream to M8Flow's workflow engine (`m8flow-core` via `m8flow_backend.workflow`). It processes only trigger events the backend signed after authenticating the caller's API key, then instantiates workflow processes natively inside the Flask application context — no HTTP hop to the backend required.

---

## How it Works

1. **An external system calls** `POST /v1.0/m8flow/events/m8flow-trigger` with its API key in the `X-M8FLOW-NATS-API-Key` header. The backend authenticates the key and checks its process scope.
2. **The backend publishes** an event to `m8flow.events.<tenant-slug>.trigger`. It carries the key's public id (`api_key_id`) and an HMAC signature, never the raw key, because JetStream retains every message.
3. **The consumer** verifies the signature, refuses events whose signed `issued_at` is more than `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` (default 300) from now, re-checks that the key is still active and scoped for the process, and drops duplicate event ids (NATS KV, keyed `tenant_id-event_id`).
4. **The process starts as the key's owner** (the user who created the key) through `m8flow_backend.workflow.start`. The request's `data` is stored as process-instance metadata.

Publishing straight to NATS is not supported: the consumer rejects any event without a valid backend signature.

---

## Environment Variables

All variables are strictly required and must be provided via `.env` or the Docker environment. There are no fallbacks.

| Variable                    | Example                    | Description                                                                                              |
| --------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------- |
| `M8FLOW_NATS_ENABLED`           | `true`    | Enable NATS                                                                                           |
| `M8FLOW_NATS_URL`           | `nats://localhost:6845`    | NATS server URL (host port default; see `M8FLOW_NATS_PORT` in [sample.env](../sample.env)) |
| `M8FLOW_NATS_STREAM_NAME`   | `M8FLOW_EVENTS`            | JetStream stream name                                                                                    |
| `M8FLOW_NATS_SUBJECT`       | `m8flow.events.>`          | Subject filter for subscription                                                                          |
| `M8FLOW_NATS_DURABLE_NAME`  | `m8flow-engine-consumer`   | Durable consumer name                                                                                    |
| `M8FLOW_NATS_FETCH_BATCH`   | `10`                       | Pull batch size per loop iteration                                                                       |
| `M8FLOW_NATS_FETCH_TIMEOUT` | `2.0`                      | Fetch timeout in seconds                                                                                 |
| `M8FLOW_NATS_DEDUP_BUCKET`  | `m8flow-dedup`             | Name of the NATS KV Bucket used for deduplication.                                                       |
| `M8FLOW_NATS_DEDUP_TTL`     | `86400`                    | Time in seconds to remember an event to block duplicate processing.                                      |
| `M8FLOW_NATS_TOKEN_SALT`   | output of `openssl rand -hex 32` | Server secret that peppers stored API-key hashes and signs trigger events. Must be the same for the backend and this consumer. Required: while it is unset, a placeholder published in this repo, or shorter than 32 characters, the backend refuses to sign triggers and this consumer refuses to start. Changing it invalidates API keys already issued. |
  
---

## Docker Compose

To run the NATS event stack locally with Docker Compose:

1. Start the NATS server and UI:

```bash
docker compose -f docker/m8flow-nats-docker-compose.yml up -d
```

2. Start the main m8flow stack with the NATS profile so the consumer is included:

```bash
docker compose --env-file .env --profile nats -f docker/m8flow-docker-compose.yml up -d --build
```

If the main stack is already running, rerun the second command so `m8flow-nats-consumer` is started with the `nats` profile enabled.

---

## Triggering a Workflow

```bash
curl -X POST "http://localhost:6840/v1.0/m8flow/events/m8flow-trigger" \
  -H "Content-Type: application/json" \
  -H "X-M8FLOW-NATS-API-Key: <key from Setup > API keys>" \
  -d '{"processIdentifier": "group-name/process-model-name", "data": {"invoice_id": 9921}}'
```

The response carries the created process instance, or the reason none was created. The instance's initiator is the user who created the API key.

---

## Runbook: triggers dropped as `rejected_stale`

A signed trigger is only accepted within `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` (default 300) of its `issued_at`, so a captured event cannot be replayed later. The same rule drops real triggers that waited in the stream longer than that, typically while this consumer was down. Each one is recorded with outcome `rejected_stale`, kept apart from `rejected_auth` (bad or missing signature) so the two can be told apart.

**Symptoms.** The caller got a response with `process_instance: null` (the backend stopped waiting for the reply), and no instance was started. **System → NATS → Events** lists the event as *Rejected: stale*, and the "Failures by outcome" panel of the *M8Flow NATS Trigger Consumer Overview* dashboard shows a `rejected_stale` series.

**Alert.** Alert on any occurrence, for example:

```promql
sum(increase(nats_consumer_processing_failures_total{job="m8flow-nats-consumer", outcome="rejected_stale"}[10m])) > 0
```

**Response.**
1. Check the consumer is running and connected (`docker logs m8flow-nats-consumer`). A burst right after it restarts means the stream held triggers from the outage.
2. Ask the affected integrations to resend the dropped triggers; each resend is signed afresh, and the dropped copies never start late, so a resend does not duplicate them.
3. If outages longer than the window are expected, raise `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` on the consumer. A longer window also lets a captured event be replayed for longer whenever the dedup bucket (`M8FLOW_NATS_DEDUP_TTL`) has forgotten it or is unavailable.
4. Steady `rejected_stale` with the consumer healthy points at clock skew: compare the backend and consumer host clocks.
