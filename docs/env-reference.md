# Environment variable reference

This file is the **canonical** place for environment variable meanings and examples. The root [README.md](../README.md) and [docker/README.md](../docker/README.md) link here instead of repeating full definitions, to reduce drift.

## Host ports (Docker Compose defaults)

These control what **your machine** listens on when you run [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml). Defaults are chosen to avoid common host port clashes (for example reserved or popular defaults in the 7000 and 9000 ranges). Set overrides in `.env` (from [sample.env](../sample.env)) and rebuild.

| Variable | Default | Service / use |
|----------|---------|----------------|
| `M8FLOW_BACKEND_PORT` | `6840` | Backend API (host and container use the same value in compose) |
| `M8FLOW_FRONTEND_PORT` | `6841` | Frontend (host → container 8080) |
| `KEYCLOAK_PROXY_PORT` | `6842` | Keycloak nginx proxy (host → container 6842) |
| `KEYCLOAK_MGMT_PORT` | `6849` | Keycloak management / health on host |
| `POSTGRES_HOST_PORT` | `6843` | `m8flow-db` PostgreSQL on host |
| `CONNECTOR_PROXY_PORT` | `6844` | Connector proxy |
| `M8FLOW_NATS_PORT` | `6845` | NATS client port ([m8flow-nats-docker-compose.yml](../docker/m8flow-nats-docker-compose.yml)) |
| `MINIO_API_PORT` | `6846` | MinIO S3 API on host |
| `MINIO_CONSOLE_PORT` | `6847` | MinIO console on host |
| `REDIS_HOST_PORT` | `6848` | Redis on host |
| `M8FLOW_BACKEND_CELERY_FLOWER_PORT` | `6850` | Celery Flower (host and in-container bind) |
| `M8FLOW_NATS_MONITORING_PORT` | `6851` | NATS monitoring (host → container 8222) |
| `M8FLOW_NATS_UI_PORT` | `6852` | NATS UI (host → container 31311) |
| `MINIO_LOCAL_DEV_API_PORT` | `16846` | Standalone MinIO dev API ([minio.local-dev.docker-compose.yml](../docker/minio.local-dev.docker-compose.yml)) |
| `MINIO_LOCAL_DEV_CONSOLE_PORT` | `16847` | Standalone MinIO dev console |

Also align URL-style settings with the above (e.g. `M8FLOW_BACKEND_URL`, `KEYCLOAK_HOSTNAME`, `M8FLOW_BACKEND_DATABASE_URI` host port, `M8FLOW_NATS_URL`).

## Keycloak URLs

- `KEYCLOAK_HOSTNAME`: Browser/public base URL used to reach Keycloak (for example `http://localhost:6842`). If clients access from another machine, use `http://<host>:6842` (or your real hostname and port).
- `KEYCLOAK_HOSTNAME_URL`: Public Keycloak base URL Keycloak uses for token issuer (`iss`). In this repo’s Docker Compose, `KC_HOSTNAME_URL` is wired from `KEYCLOAK_HOSTNAME`; set `KEYCLOAK_HOSTNAME` consistently with how users reach Keycloak.
- `KEYCLOAK_HOSTNAME_HOST` (optional): Hostname segment passed to Keycloak as `KC_HOSTNAME` in [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml) (default `localhost`). Adjust if your deployment needs a different hostname for Keycloak’s own hostname configuration.
- `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL`: Backend URL for Keycloak Admin/API calls. **Docker Compose:** set by compose to `http://keycloak-proxy:6842` for `m8flow-backend` (internal network). **Local dev:** often `http://localhost:6842` to match the proxy port on the host.
- `M8FLOW_APP_PUBLIC_BASE_URL` (optional): Set when the app and Keycloak are exposed on different public hosts. If unset, `KEYCLOAK_HOSTNAME` is used for generated app-facing URLs where applicable.

## Connector attachment paths

For SMTP and Slack connectors:

- `*_ATTACHMENTS_DIR`: Host/source path where files are read from.
- `*_ATTACHMENTS_USER_ACCESS_DIR`: User-visible mounted path used in service-task file selection.

Examples:

- `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_DIR=../data/email_attachments`
- `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_USER_ACCESS_DIR=/data/email_attachments`
- `M8FLOW_CONNECTOR_SLACK_ATTACHMENTS_DIR=../data/slack_attachments`
- `M8FLOW_CONNECTOR_SLACK_ATTACHMENTS_USER_ACCESS_DIR=/data/slack_attachments`

## Advanced Keycloak auth configs

For `SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS` patterns (master realm, `admin-cli`, role mapping), see [m8flow-backend/keycloak/KEYCLOAK_SETUP.md](../m8flow-backend/keycloak/KEYCLOAK_SETUP.md).
