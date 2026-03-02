# M8Flow NATS Consumer

Standalone Python service for consuming NATS JetStream messages and seamlessly triggering M8Flow workflows via native database execution.

## Overview

This service forms the ingest layer of the Event-Driven Architecture. It operates directly against the M8Flow backend database within a Flask application context, natively executing SpiffWorkflow models and securely bypassing external APIs.

For architectural details, see the main `docs/event-driven-architecture.md`.

## Quickstart

Use the `docker-compose.yml` in the parent `docker/` directory.

```bash
cd ../docker
docker compose -f m8flow-docker-compose.yml up -d
```

## Developer Usage

You can use the publisher utility to test the consumer manually:

```bash
cd m8flow-nats-consumer
uv run python publisher.py \
  --tenant_id "your-tenant-id" \
  --username "tenant-admin@spiffworkflow" \
  --process_identifier "new-workflow/nats-event-trigger-test" \
  --payload '{"key": "value"}'
```
