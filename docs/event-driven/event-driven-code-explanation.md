# M8Flow NATS Code Organization

This document is an index for the Event-Driven Architecture codebase. The consumer performs API Key validation then runs process instances directly within the backend's Python application context.

---

## 1. NATS Consumer Service (`m8flow-nats-consumer/`)

### `consumer.py`

The main ingestion daemon. Connects to NATS, authenticates every event via an M8Flow API Key, and instantiates processes natively.

#### Required Event Fields

The consumer immediately discards any message missing these fields:

| Field                | Purpose                                                          |
| -------------------- | ---------------------------------------------------------------- |
| `tenant_id`          | Identifies the M8Flow tenant (used for DB schema switching)      |
| `process_identifier` | BPMN process path to instantiate                                 |
| `username`           | M8Flow user who will own the process instance                    |
| `api_key`            | M8Flow API Key — proves the publisher is authorized to send events |

#### API Key Authentication Layer (`NatsTokenService`)

- **Secure Verification:** The `api_key` provided in the message payload is sent directly to `NatsTokenService.verify_token(tenant_id, api_key)`.
- **HMAC Storage:** M8Flow never stores plain API keys. The incoming key is hashed securely via HMAC-SHA256, applying an internal salt.
- **Comparison:** This hash is queried and compared cryptographically against the hash stored for the given tenant ID in `NatsTokenModel`.

#### User Resolution

After the JWT is verified, the `username` from the payload is looked up in the M8Flow database:

```python
user = UserModel.query.filter_by(username=username).first()
```

If the user does not exist, the event is discarded with an error log. The `username` payload field controls _process ownership_; the API key controls _publisher authorization_ — these are two distinct identities.

#### Process Instantiation

- Flask `app_context()` established
- `set_context_tenant_id(tenant_id)` switches the active DB schema
- `ProcessModelService.get_process_model(process_identifier)` resolves the BPMN
- `ProcessInstanceService.create_and_run_process_instance(process_model, user)` runs the workflow
- `db.session.commit()` persists, `reset_context_tenant_id()` cleans up

#### Delivery Guarantees

| Outcome                   | Action                                                |
| ------------------------- | ----------------------------------------------------- |
| Success                   | `db.session.commit()` → `msg.ack()`                   |
| Auth / validation failure | `msg.ack()` (discard — retrying won't help)           |
| Duplicate Event (NATS KV) | `msg.ack()` (discard — already processed)             |
| Transient DB error        | `kv.delete()` → `db.session.rollback()` → `msg.nak()` |

---

### `publisher.py`

CLI developer utility to publish authenticated test events. It:

1. Takes an M8Flow API Key as the `--api_key` argument
2. Embeds the API Key as `api_key` in the event payload
3. Publishes the event to NATS JetStream

Arguments:

| Argument               | Required | Description                                                          |
| ---------------------- | -------- | -------------------------------------------------------------------- |
| `--tenant_id`          | ✅       | M8Flow tenant UUID                                                   |
| `--process_identifier` | ✅       | Target BPMN process path                                             |
| `--username`           | ✅       | M8Flow user who will own the process instance                        |
| `--api_key`            | ✅       | M8Flow API Key (generated from `/m8flow/nats-tokens` API endpoint)   |
| `--payload`            | No       | JSON string injected as event data                                   |

> The `api_key` is only used for authentication — it proves the publisher is authorized for the tenant. It has no relation to the `username` field.

---

### `pyproject.toml`

Uses `uv` to declare `spiffworkflow-backend` as a local path dependency, giving the consumer native access to the backend's Python modules.

### `Dockerfile`

Lean image — `uv pip install --system` installs dependencies, then runs `consumer.py` as the entrypoint.

---

## 2. Infrastructure (`docker/`)

### `m8flow.nats.Dockerfile`

Lean image built directly from the official `nats:alpine` base image.

> **Stream & KV Creation:** Stream creation (`M8FLOW_EVENTS`) and Key-Value bucket creation (`m8flow-dedup`) are handled natively on startup by `consumer.py` using `js.add_stream()` and `js.create_key_value()`.
