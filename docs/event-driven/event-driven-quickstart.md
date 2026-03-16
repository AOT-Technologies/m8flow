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
```

### M8Flow API Key

Before publishing, you need a valid API key for the target tenant. Generate an API Key in the M8Flow UI or via the `/m8flow/nats-tokens` REST API using an account with the `manage-nats-tokens` permission (e.g., a `tenant-admin`).

> The `api_key` authenticates the **publisher system** (proving they are allowed to send events into this tenant). It does not control which M8Flow user runs the workflow — that is set dynamically per event by `--username`.

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
  --api_key            "m8f_raw_api_key_from_api" \
  --username           "john.doe@company.com" \
  --process_identifier "new-workflow/nats-event-trigger-test" \
  --payload            '{"customer_id": "123", "amount": 500}'
```

**What happens:**

| Step | Who            | What                                                                               |
| ---- | -------------- | ---------------------------------------------------------------------------------- |
| 1    | `publisher.py` | Publishes `{tenant_id, process_identifier, username, api_key, payload}` to NATS    |
| 2    | `consumer.py`  | Idempotency check: creates NATS KV `tenant_id-event_id` (discards if exists)       |
| 3    | `consumer.py`  | Validates `api_key` securely via HMAC hashing against the `NatsTokenModel` DB table|
| 4    | `consumer.py`  | Looks up `username` in M8Flow DB                                                   |
| 5    | `consumer.py`  | Runs `ProcessInstanceService` natively as that user                                |

---

## 4. Verify Execution

### Consumer Logs

```bash
docker logs m8flow-nats-consumer
```

Expected on success:

```
[INFO]  Subscribing to m8flow.events.> (durable: m8flow-engine-consumer)
[INFO]  Process instance created | tenant=9f5d... identifier=new-workflow/... instance_id=42
```

### M8Flow UI

Log into the M8Flow UI, switch to the correct tenant, and verify that a new process instance appeared.
