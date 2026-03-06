# M8Flow NATS Consumer

Standalone Python service that bridges NATS JetStream to M8Flow's SpiffWorkflow engine. It validates publisher identity via Keycloak JWT, then instantiates workflow processes natively inside the Flask application context — no HTTP hop to the backend required.

---

## How it Works

1. **Publisher** fetches a JWT from Keycloak (Client Credentials Grant) and publishes an event to NATS that includes:
   - `auth_token` — the JWT (proves the publisher is authorized)
   - `username` — the M8Flow user who should own the process instance
   - `tenant_id`, `process_identifier`, and optional `payload`
2. **Consumer** pulls the event from the durable JetStream subscription
3. **Idempotency check** — NATS KV lookup using `tenant_id-event_id`. Duplicate events are immediately acked and discarded.
4. **JWT validated** via JWKS (public keys fetched from Keycloak's `{iss}/protocol/openid-connect/certs` endpoint and cached)
5. **User resolved** — `username` looked up in `UserModel`; event discarded if not found
6. **Process instantiated** — `ProcessInstanceService` called directly within a Flask app context and multi-tenant DB schema

---

## Environment Variables

All variables are strictly required and must be provided via `.env` or the Docker environment. There are no fallbacks.

| Variable                    | Example                    | Description                                                                                                                             |
| --------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `M8FLOW_NATS_URL`           | `nats://localhost:4222`    | NATS server URL                                                                                                                         |
| `M8FLOW_NATS_STREAM_NAME`   | `M8FLOW_EVENTS`            | JetStream stream name                                                                                                                   |
| `M8FLOW_NATS_SUBJECT`       | `m8flow.events.>`          | Subject filter for subscription                                                                                                         |
| `M8FLOW_NATS_DURABLE_NAME`  | `m8flow-engine-consumer`   | Durable consumer name                                                                                                                   |
| `M8FLOW_NATS_FETCH_BATCH`   | `10`                       | Pull batch size per loop iteration                                                                                                      |
| `M8FLOW_NATS_FETCH_TIMEOUT` | `2.0`                      | Fetch timeout in seconds                                                                                                                |
| `M8FLOW_NATS_DEDUP_BUCKET`  | `m8flow-dedup`             | Name of the NATS KV Bucket used for deduplication.                                                                                      |
| `M8FLOW_NATS_DEDUP_TTL`     | `86400`                    | Time in seconds to remember an event to block duplicate processing.                                                                     |
| `KEYCLOAK_URL`              | `http://192.168.1.89:7002` | Keycloak base URL. Used by the publisher to construct the token endpoint. The consumer derives realm from the JWT `iss` claim directly. |

---

## Event Message Schema

Every event must carry these fields — the consumer discards any message that is missing one:

| Field                | Description                                       |
| -------------------- | ------------------------------------------------- |
| `tenant_id`          | M8Flow tenant UUID                                |
| `process_identifier` | BPMN process path, e.g. `billing/invoice-paid`    |
| `username`           | M8Flow username who will own the process instance |
| `auth_token`         | Keycloak JWT — authenticates the publisher        |
| `payload`            | _(optional)_ JSON injected as process variables   |

> `auth_token` and `username` serve different purposes. The JWT proves _who published the event_ (authorization). The `username` controls _which M8Flow user runs the workflow_ (process ownership). They can be different identities.

---

## Publishing Events — `publisher.py`

```bash
uv run python publisher.py \
  --tenant_id          "your-m8flow-tenant-uuid" \
  --realm              "your-keycloak-realm" \
  --client_id          "your-service-account-client-id" \
  --client_secret      "your-service-account-client-secret" \
  --username           "john.doe@company.com" \
  --process_identifier "new-workflow/nats-event-trigger-test" \
  --payload            '{"customer_id": "123"}'
```

| Argument               | Required | Description                                              |
| ---------------------- | -------- | -------------------------------------------------------- |
| `--tenant_id`          | ✅       | M8Flow tenant UUID                                       |
| `--process_identifier` | ✅       | BPMN process path                                        |
| `--username`           | ✅       | M8Flow user who will own the process instance            |
| `--realm`              | ✅       | Keycloak realm name                                      |
| `--client_id`          | ✅       | Service account client ID (needed to fetch `auth_token`) |
| `--client_secret`      | ✅       | Service account client secret                            |
| `--payload`            | No       | JSON string of additional process variables              |

---

## Troubleshooting

| Log                                  | Cause                                                                              |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| `Missing required fields`            | `tenant_id`, `process_identifier`, `username`, or `auth_token` absent from payload |
| `Failed to fetch public keys`        | Keycloak unreachable from inside Docker (check `KEYCLOAK_URL` and network)         |
| `Invalid or expired auth_token`      | JWT expired or wrong Keycloak realm/client                                         |
| `User 'x' not found in the database` | `--username` does not exist as an M8Flow user                                      |
| `Process model ... not found`        | Wrong `--process_identifier` or process not deployed in M8Flow                     |
