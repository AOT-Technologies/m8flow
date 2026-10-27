# Services and ports

This page lists every service in the m8flow Compose files, its default host
port, and the variable in `.env` that changes the port.

## Main stack

The main stack is defined in `docker/m8flow-docker-compose.yml`.

| Service | Purpose | Host port | Port variable |
|---|---|---|---|
| `m8flow-designer` | Web UI | 6853 | `M8FLOW_FRONTEND_PORT` |
| `m8flow-backend` | HTTP API | 6840 | `M8FLOW_BACKEND_PORT` |
| `keycloak-proxy` | Browser-facing Keycloak URL | 6842 | `KEYCLOAK_PROXY_PORT` |
| `keycloak` | Identity provider. Only the management and health port is published. | 6849 | `KEYCLOAK_MGMT_PORT` |
| `keycloak-db` | PostgreSQL for Keycloak | Not published | Not applicable |
| `m8flow-db` | PostgreSQL for m8flow | 6843 | `POSTGRES_HOST_PORT` |
| `m8flow-db-extensions` | One-shot job that enables `pg_stat_statements` | Not published | Not applicable |
| `m8flow-node-wire-proxy` | Connector proxy for service tasks | 6844 | `CONNECTOR_PROXY_PORT` |
| `minio` | Object storage API and console | 6846, 6847 | `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` |
| `redis` | Celery broker | 6848 | `REDIS_HOST_PORT` |
| `m8flow-celery-worker` | Background jobs | Not published | Not applicable |
| `m8flow-celery-flower` | Celery monitoring UI | 6850 | `M8FLOW_BACKEND_CELERY_FLOWER_PORT` |
| `m8flow-notification-worker` | Sends external-form emails | Not published | Not applicable |

## Profiles

Some services start only when you pass `--profile <name>` to
`docker compose`. Replace `<name>` with one of the profiles in the following
table:

| Profile | Services | Purpose |
|---|---|---|
| `init` | `keycloak-master-admin-init`, `minio-mc-init`, `process-models-sync`, `templates-sync`, `smtp-attachments-sync`, `slack-attachments-sync` | One-time setup. Run on the first start. |
| `nats` | `m8flow-nats-consumer` | Starts processes from NATS trigger events. Needs the NATS server. |

The `init` jobs do the following:

- `keycloak-master-admin-init` creates the `super-admin` user and the backend
  client in the master realm.
- `minio-mc-init` creates the `m8flow-process-models` and `m8flow-templates`
  buckets.
- `process-models-sync` and `templates-sync` copy the seed process models and
  templates into MinIO.
- `smtp-attachments-sync` and `slack-attachments-sync` copy the connector
  attachment folders.

## NATS stack

The NATS server is defined in `docker/m8flow-nats-docker-compose.yml`. It
joins the main stack's network, so start the main stack first.

| Service | Purpose | Host port | Port variable |
|---|---|---|---|
| `nats` | NATS client port | 6845 | `M8FLOW_NATS_PORT` |
| `nats` | NATS monitoring | 6851 | `M8FLOW_NATS_MONITORING_PORT` |

Port 6845 is also the default for the alternative connector proxy. Change one
of them if you run both.

## Observability stack

The observability stack is defined in
`docker/m8flow-observability-docker-compose.yml`.

| Service | Host port | Port variable |
|---|---|---|
| Grafana | 6868 | `M8FLOW_GRAFANA_PORT` |
| Prometheus | 6864 | `M8FLOW_PROMETHEUS_PORT` |
| Loki | 6862 | `M8FLOW_LOKI_PORT` |
| Tempo | 6863 | `M8FLOW_TEMPO_PORT` |
| Alloy OTLP gRPC and HTTP | 4317, 4318 | `M8FLOW_ALLOY_OTLP_GRPC_PORT`, `M8FLOW_ALLOY_OTLP_HTTP_PORT` |
| cAdvisor | 6867 | `M8FLOW_CADVISOR_PORT` |
| MinIO for Loki and Tempo | 6860, 6861 | `M8FLOW_OBS_MINIO_API_PORT`, `M8FLOW_OBS_MINIO_CONSOLE_PORT` |

## Change a port

To change a port, follow these steps:

1. Find the program that holds the port. On macOS or Linux, run
   `lsof -i :<port>`. On Windows PowerShell, run
   `Get-NetTCPConnection -LocalPort <port>`.
2. In `.env`, set the service's port variable to a free port.
3. Update the URL settings that include the old port, such as
   `KEYCLOAK_HOSTNAME` or `M8FLOW_BACKEND_DATABASE_URI`.
4. Start the stack again with `docker compose ... up -d`.

Replace `<port>` with the port number, for example `6840`.

## Related pages

- [Configuration](configuration.md)
- [About the m8flow architecture](../explanation/architecture.md)
