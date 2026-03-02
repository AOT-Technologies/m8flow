# M8Flow NATS Deployment & Quickstart

This document explains how to configure, run, and test the NATS Event-Driven Architecture.

---

## 1. Prerequisites

In `.env`, ensure your NATS Config is assigned correctly:

```env
# Consumer Config
M8FLOW_NATS_URL=nats://nats:4222
M8FLOW_NATS_STREAM_NAME=M8FLOW_EVENTS
M8FLOW_NATS_SUBJECT=m8flow.events.>
```

---

## 2. Starting the Infrastructure

The NATS consumer and NATS server are fully integrated into the main `docker-compose` setup located in the `docker/` directory.

```bash
cd docker
docker compose -f m8flow-docker-compose.yml up -d
```

This commands starts:

1. `m8flow-db` (PostgreSQL)
2. `m8flow-nats` (Customized NATS server that automatically creates the required JetStream streams on boot)
3. `m8flow-backend` (The SpiffWorkflow API)
4. `m8flow-nats-consumer` (The standalone application daemon that securely directly runs Python services context, without requiring HTTP requests)

---

## 3. How to Test Manually

Once the ecosystem is running, you can simulate an external system (like a billing service or an e-commerce storefront) publishing an event into NATS.

We provide a developer utility script inside the `m8flow-nats-consumer` source directory specifically for this purpose.

> **Important:** You must use a valid `tenant_id` and an existing `process_identifier` that has been deployed in M8Flow.

```bash
cd m8flow-nats-consumer

# Run using the modern `uv` Python package manager
uv run python publisher.py \
  --tenant_id "your-tenant-id" \
  --username "tenant-admin@spiffworkflow" \
  --process_identifier "new-workflow/nats-event-trigger-test" \
  --payload '{"customer_id": "123", "amount": 500}'
```

### 3.1 Verify Execution

First, check the consumer container logs to see it receive and process the message successfully:

```bash
docker logs m8flow-nats-consumer
```

Expected output:

```
[INFO] Starting M8Flow NATS Consumer...
[INFO] Subscribing to m8flow.events.>
[INFO] Process instance created | tenant=c29... identifier=some/process instance_id=45
```

Second, log into the M8Flow UI (`http://localhost:8001`), switch to the correct tenant context, and verify that a new instance of your workflow has been executed.
