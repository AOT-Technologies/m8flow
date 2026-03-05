# M8Flow NATS Deployment & Quickstart

This document explains how to configure, run, and test the NATS Event-Driven Architecture.

---

## 1. Prerequisites

### Environment Variables

In `.env`, ensure the following are set:

```env
# NATS Consumer Config (All are strictly required; no defaults)
M8FLOW_NATS_URL=nats://nats:4222
M8FLOW_NATS_STREAM_NAME=M8FLOW_EVENTS
M8FLOW_NATS_SUBJECT=m8flow.events.>
M8FLOW_NATS_DURABLE_NAME=m8flow-engine-consumer
M8FLOW_NATS_FETCH_BATCH=10
M8FLOW_NATS_FETCH_TIMEOUT=2.0
M8FLOW_NATS_DEDUP_BUCKET=m8flow-dedup
M8FLOW_NATS_DEDUP_TTL=86400

# Keycloak (required for JWT validation in the consumer and token fetching in the publisher)
# Base URL only — the consumer resolves the realm automatically from the JWT's iss claim.
KEYCLOAK_URL=http://<LOCAL_IP>:7002
```

### Keycloak Client

M8Flow's Keycloak realm already includes the **`spiffworkflow-backend`** client with Service Accounts Roles enabled. Use it directly — no new client needs to be created.

> The `client_id` + `client_secret` authenticate the **publisher** (who is allowed to send events). They do not control which M8Flow user runs the workflow — that is set by `--username`.

### M8Flow User

The `username` you pass to the publisher must already exist as an M8Flow `UserModel` in the database. Ensure the target user has logged in or been provisioned before publishing events.

---

## 2. Starting the Infrastructure

```bash
cd docker
docker compose -f m8flow-docker-compose.yml up -d
```

This starts `m8flow-db`, `m8flow-nats`, `m8flow-backend`, and `m8flow-nats-consumer`.

---

## 3. Publishing a Test Event

Use `publisher.py` to send an authenticated event that triggers a workflow:

```bash
cd m8flow-nats-consumer

uv run python publisher.py \
  --tenant_id          "your-m8flow-tenant-uuid" \
  --realm              "spiffworkflow" \
  --client_id          "spiffworkflow-backend" \
  --client_secret      "<spiffworkflow-backend-client-secret>" \
  --username           "john.doe@company.com" \
  --process_identifier "new-workflow/nats-event-trigger-test" \
  --payload            '{"customer_id": "123", "amount": 500}'
```

**What happens:**

| Step | Who            | What                                                                               |
| ---- | -------------- | ---------------------------------------------------------------------------------- |
| 1    | `publisher.py` | Calls Keycloak Client Credentials Grant → receives signed JWT                      |
| 2    | `publisher.py` | Publishes `{tenant_id, process_identifier, username, auth_token, payload}` to NATS |
| 3    | `consumer.py`  | Idempotency check: creates NATS KV `tenant_id-event_id` (discards if exists)       |
| 4    | `consumer.py`  | Validates JWT signature via JWKS                                                   |
| 5    | `consumer.py`  | Looks up `username` in M8Flow DB                                                   |
| 6    | `consumer.py`  | Runs `ProcessInstanceService` natively as that user                                |

---

## 4. Verify Execution

### Consumer Logs

```bash
docker logs m8flow-nats-consumer
```

Expected on success:

```
[INFO]  Subscribing to m8flow.events.> (durable: m8flow-engine-consumer)
[DEBUG] Authenticated event | publisher='service-account-...' target_user='john.doe@company.com'
[INFO]  Process instance created natively | tenant=9f5d... identifier=new-workflow/... instance_id=42
```

Common error logs and causes:

| Error                                | Cause                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------- |
| `Missing 'auth_token'`               | Publisher did not fetch a JWT — check `--client_id`/`--client_secret`/`--realm` |
| `Token is missing 'iss' claim`       | Malformed JWT                                                                   |
| `Invalid or expired auth_token`      | Keycloak unreachable from inside Docker, or token expired in flight             |
| `User 'x' not found in the database` | The `--username` does not exist as an M8Flow user                               |
| `Process model ... not found`        | Wrong `--process_identifier` or process not deployed                            |

### M8Flow UI

Log into the M8Flow UI, switch to the correct tenant, and verify that a new process instance appeared.
