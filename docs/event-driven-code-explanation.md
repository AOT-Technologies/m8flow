# M8Flow NATS Code Organization

This document acts as an index for the codebase related to the Event-Driven Architecture. We use a high-performance Native Database Integration approach where the consumer lives separately but executes process instances directly within the backend's Python application context.

---

## 1. NATS Consumer Service (`m8flow-nats-consumer/`)

This is a standalone Python application living at the root of the repository. It is responsible for listening to events and natively instantiating processes.

### `consumer.py`

The main ingestion daemon. It connects to NATS using the modern `asyncio` loop with `nats-py`, and integrates directly with the M8Flow backend context:

- **Environment & Initialization:** The application uses `load_dotenv()` to pull configuration and forcefully sets absolute directory paths for BPMN models. By arranging the import order specifically, it ensures backend components read the correct environment flags.
- **Durable Pull Subscription:** The consumer requests batches of messages from the JetStream `M8FLOW_EVENTS` stream (e.g., `batch=10` with a `timeout=2.0s`).
- **Native Invocation:** For each message, it extracts the JSON payload (`tenant_id`, `process_identifier`, `username`, and `payload`). It creates a Flask `app_context()` and dynamically sets the active tenant context using `set_context_tenant_id(tenant_id)`.
- **Process Instantiation:** It queries the database for the relevant user, dynamically resolves the targeted `ProcessModel` using `ProcessModelService`, and synchronously invokes `ProcessInstanceService.create_and_run_process_instance(...)`.
- **Delivery Guarantees:**
  - Upon successful commit to the database, it explicitly calls `msg.ack()`, deleting the event from NATS.
  - On exceptions (like transient DB errors), it performs a rollback and calls `msg.nak(delay=5)`, formatting JetStream to wait 5 seconds and automatically resubmit it to the queue.

### `publisher.py`

A simple CLI wrapper to formulate the correct JSON schema and publish the message into the NATS Server directly. Extremely useful for developers testing pipelines locally. It accepts parameters like `--tenant_id`, `--username`, and `--process_identifier`.

### `pyproject.toml`

Uses the `uv` package manager (and Poetry standards) to manage dependencies, declaring `spiffworkflow-backend` as a relative path dependency so the consumer can natively share the local repository's Python source files for backend instantiation.

### `Dockerfile`

A multi-stage Docker build utilizing `uv` to install dependencies and deploy the consumer daemon efficiently without container bloat.

---

## 2. Infrastructure (`docker/`)

Because NATS JetStream requires specific stream initialization, we cannot always use the raw `nats` image out of the box easily.

### `m8flow.nats.Dockerfile`

We construct over `nats:alpine`. We pre-install `nats-cli` and bind to a script (`setup_stream.sh`) that daemonizes the nats server, waits 2 seconds, and executes a terminal command equivalent to:
`nats stream add M8FLOW_EVENTS --subjects="m8flow.events.>"`

This ensures zero manual setup is required when deploying via `docker-compose`.
