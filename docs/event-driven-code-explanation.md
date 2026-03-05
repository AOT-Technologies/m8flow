# M8Flow NATS Code Organization

This document is an index for the Event-Driven Architecture codebase. The consumer performs JWT authentication then runs process instances directly within the backend's Python application context.

---

## 1. NATS Consumer Service (`m8flow-nats-consumer/`)

### `consumer.py`

The main ingestion daemon. Connects to NATS, authenticates every event via Keycloak JWT, and instantiates processes natively.

#### Required Event Fields

The consumer immediately discards any message missing these fields:

| Field                | Purpose                                                          |
| -------------------- | ---------------------------------------------------------------- |
| `tenant_id`          | Identifies the M8Flow tenant (used for DB schema switching)      |
| `process_identifier` | BPMN process path to instantiate                                 |
| `username`           | M8Flow user who will own the process instance                    |
| `auth_token`         | Keycloak JWT — proves the publisher is authorized to send events |

#### JWT Authentication Layer (`get_public_keys`, `validate_token`)

- **Issuer discovery:** `iss` claim decoded from the JWT (unverified read only) to determine the Keycloak realm URL. No realm config required — the token carries its own origin.
- **JWKS fetch & cache:** Public keys fetched from `{iss}/protocol/openid-connect/certs` and cached in `jwks_cache` by issuer URL.
- **Signature verification:** `jwt.decode` validates RSA signature, expiry, and issuer. Key rotation handled by cache invalidation and re-fetch.

#### User Resolution

After the JWT is verified, the `username` from the payload is looked up in the M8Flow database:

```python
user = UserModel.query.filter_by(username=username).first()
```

If the user does not exist, the event is discarded with an error log. The `username` payload field controls _process ownership_; the JWT controls _publisher authorization_ — these are two distinct identities.

#### Process Instantiation

- Flask `app_context()` established
- `set_context_tenant_id(tenant_id)` switches the active DB schema
- `ProcessModelService.get_process_model(process_identifier)` resolves the BPMN
- `ProcessInstanceService.create_and_run_process_instance(process_model, user)` runs the workflow
- `db.session.commit()` persists, `reset_context_tenant_id()` cleans up

#### Delivery Guarantees

| Outcome                   | Action                                                 |
| ------------------------- | ------------------------------------------------------ |
| Success                   | `db.session.commit()` → `msg.ack()`                    |
| Auth / validation failure | `msg.ack()` (discard — retrying won't help)            |
| Transient DB error        | `db.session.rollback()` → `msg.nak(delay=5)` (requeue) |

---

### `publisher.py`

CLI developer utility to publish signed test events. It:

1. Fetches a Keycloak JWT using Client Credentials Grant (`--client_id` + `--client_secret`)
2. Embeds the JWT as `auth_token` in the event payload
3. Publishes the event to NATS JetStream

Arguments:

| Argument               | Required | Description                                                          |
| ---------------------- | -------- | -------------------------------------------------------------------- |
| `--tenant_id`          | ✅       | M8Flow tenant UUID                                                   |
| `--process_identifier` | ✅       | Target BPMN process path                                             |
| `--username`           | ✅       | M8Flow user who will own the process instance                        |
| `--realm`              | ✅\*     | Keycloak realm name (e.g. `spiffworkflow`) — **not** the tenant UUID |
| `--client_id`          | No†      | Service account client ID (required to include `auth_token`)         |
| `--client_secret`      | No†      | Service account client secret                                        |
| `--payload`            | No       | JSON string injected as event data                                   |

> †`client_id` and `client_secret` are only used for authentication — they prove the publisher is authorized. They have no relation to the `username` field.

---

### `pyproject.toml`

Uses `uv` to declare `spiffworkflow-backend` as a local path dependency, giving the consumer native access to the backend's Python modules.

### `Dockerfile`

Lean image — `uv pip install --system` installs dependencies, then runs `consumer.py` as the entrypoint.

---

## 2. Infrastructure (`docker/`)

### `m8flow.nats.Dockerfile`

Built over `nats:alpine`. Runs `setup_stream.sh` on startup to create the `M8FLOW_EVENTS` JetStream stream automatically:

```
nats stream add M8FLOW_EVENTS --subjects="m8flow.events.>"
```
