# M8Flow NATS Consumer

Standalone Python service that bridges NATS JetStream to M8Flow's SpiffWorkflow engine. It validates publisher identity via a hashed API Key via the `/m8flow/nats-tokens` API, then instantiates workflow processes natively inside the Flask application context — no HTTP hop to the backend required.

---

## How it Works

1. **Publisher - ( dev use only )** publishes an event to NATS that includes:
   - `username` — the M8Flow user who should own the process instance
   - `tenant_id`, `api_key`, `process_identifier`, and optional `payload`
2. **Consumer** pulls the event from the durable JetStream subscription
3. **Idempotency check** — NATS KV lookup using `tenant_id-event_id`. Duplicate events are immediately acked and discarded.
4. **User resolved** — `username` looked up in `UserModel`; event discarded if not found
5. **Process instantiated** — `ProcessInstanceService` called directly within a Flask app context and multi-tenant DB schema

---

## Environment Variables

All variables are strictly required and must be provided via `.env` or the Docker environment. There are no fallbacks.

| Variable                    | Example                    | Description                                                                                              |
| --------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------- |
| `M8FLOW_NATS_ENABLED`           | `true`    | Enable NATS                                                                                           |
| `M8FLOW_NATS_URL`           | `nats://localhost:4222`    | NATS server URL                                                                                          |
| `M8FLOW_NATS_STREAM_NAME`   | `M8FLOW_EVENTS`            | JetStream stream name                                                                                    |
| `M8FLOW_NATS_SUBJECT`       | `m8flow.events.>`          | Subject filter for subscription                                                                          |
| `M8FLOW_NATS_DURABLE_NAME`  | `m8flow-engine-consumer`   | Durable consumer name                                                                                    |
| `M8FLOW_NATS_FETCH_BATCH`   | `10`                       | Pull batch size per loop iteration                                                                       |
| `M8FLOW_NATS_FETCH_TIMEOUT` | `2.0`                      | Fetch timeout in seconds                                                                                 |
| `M8FLOW_NATS_DEDUP_BUCKET`  | `m8flow-dedup`             | Name of the NATS KV Bucket used for deduplication.                                                       |
| `M8FLOW_NATS_DEDUP_TTL`     | `86400`                    | Time in seconds to remember an event to block duplicate processing.                                      |
| `M8FLOW_NATS_TOKEN_SALT`   | `my-random-salt-string`    | Salt used for hashing the NATS API keys.                                                                 |
  
---

## Event Message Schema

Every event must carry these fields — the consumer discards any message that is missing one:

| Field                | Description                                       |
| -------------------- | ------------------------------------------------- |
| `tenant_id`          | M8Flow tenant UUID                                |
| `api_key`            | M8Flow API Key (generated via `/nats-tokens` API) |
| `process_identifier` | BPMN process path, e.g. `billing/invoice-paid`    |
| `username`           | M8Flow username who will own the process instance |
| `payload`            | _(optional)_ JSON injected as process variables   |

### Example JSON Event Payload Published by External System

This is the exact JSON structure that an external system must publish to the NATS JetStream server for the M8Flow consumer to pick up and trigger a workflow:

```json
{
  "id": "e3b0c442-989b-464c-8822-abcdef123456",
  "subject": "m8flow.events.your-tenant-uuid.trigger",
  "tenant_id": "your-tenant-uuid",
  "api_key": "m8f_OaW_xxxxxxxxxxxxxxxxxxxxxxxxxx",
  "process_identifier": "group-name/process-model-name or key",
  "username": "tenant-admin@m8flow",
  "payload": {
    "invoice_id": 9921,
    "amount": 150.00
  }
}
```

---

## Publishing Events — `publisher.py`

```bash
uv run python publisher.py \
  --tenant_id          "your-m8flow-tenant-uuid" \
  --api_key            "m8f_raw_api_key_from_api" \
  --username           "username-with-tenant-name" \
  --process_identifier "group-name/process-model-name or key" \
  --payload            '{"example-key" : "example-value"}'
```

| Argument               | Required | Description                                              |
| ---------------------- | -------- | -------------------------------------------------------- |
| `--tenant_id`          | ✅       | M8Flow tenant UUID                                       |
| `--api_key`            | ✅       | M8Flow API key (generated via `/nats-tokens` API)        |
| `--process_identifier` | ✅       | BPMN process path (group-name/process-model-name or key) |
| `--username`           | ✅       | M8Flow username who will own the process instance        |
| `--payload`            | No       | JSON string of additional process variables              |

---
