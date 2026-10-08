# M8Flow NATS Consumer

Standalone Python service that bridges NATS JetStream to M8Flow's workflow engine (`m8flow-bpmn-core` via `m8flow_backend.workflow`). It processes only trigger events the backend signed after authenticating the caller's API key, then instantiates workflow processes natively inside the Flask application context — no HTTP hop to the backend required.

---

## How it Works

1. **An external system calls** `POST /v1.0/m8flow/events/m8flow-trigger` with its API key in the `X-M8FLOW-NATS-API-Key` header. The backend authenticates the key and checks its process scope.
2. **The backend publishes** an event to `m8flow.events.<tenant-slug>.trigger`. It carries the key's public id (`api_key_id`) and an HMAC signature, never the raw key, because JetStream retains every message.
3. **The consumer** verifies the signature, re-checks that the key is still active and scoped for the process, and drops duplicate event ids (NATS KV, keyed `tenant_id-event_id`).
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
| `M8FLOW_NATS_TOKEN_SALT`   | `my-random-salt-string`    | Server secret that peppers stored API-key hashes and signs trigger events. Must be the same for the backend and this consumer. |
  
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
