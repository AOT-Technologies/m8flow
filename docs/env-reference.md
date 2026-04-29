# Environment variable reference

This file is the **canonical** place for environment variable meanings and examples. The root [README.md](../README.md) and [docker/README.md](../docker/README.md) link here instead of repeating full definitions, to reduce drift.

## Keycloak URLs

- `KEYCLOAK_HOSTNAME`: Browser/public base URL used to reach Keycloak (for example `http://localhost:7002`). If clients access from another machine, use `http://<host>:7002` (or your real hostname and port).
- `KEYCLOAK_HOSTNAME_URL`: Public Keycloak base URL Keycloak uses for token issuer (`iss`). In this repo’s Docker Compose, `KC_HOSTNAME_URL` is wired from `KEYCLOAK_HOSTNAME`; set `KEYCLOAK_HOSTNAME` consistently with how users reach Keycloak.
- `KEYCLOAK_HOSTNAME_HOST` (optional): Hostname segment passed to Keycloak as `KC_HOSTNAME` in [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml) (default `localhost`). Adjust if your deployment needs a different hostname for Keycloak’s own hostname configuration.
- `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL`: Backend URL for Keycloak Admin/API calls. **Docker Compose:** set by compose to `http://keycloak-proxy:7002` for `m8flow-backend` (internal network). **Local dev:** often `http://localhost:7002` to match the proxy port on the host.
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

## Grafana (otel-lgtm)

Observability UI uses **`GRAFANA_*`** variables in `.env`; [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml) maps them to Grafana `GF_*` for the `otel-lgtm` service only (the full `.env` is **not** mounted into Grafana).

- **`GRAFANA_HTTP_PORT`**: host port for Grafana (default `3000`).
- **`GRAFANA_SERVER_ROOT_URL`**: public base URL of Grafana (OAuth redirects).
- **`GRAFANA_OIDC_ENABLED`**: keep **`true`** by default to match cloud/production auth posture.
- **`GRAFANA_OIDC_CLIENT_ID` / `GRAFANA_OIDC_CLIENT_SECRET`**: Keycloak confidential client credentials.
- **`GRAFANA_ALLOWED_ROLE`**: master-realm role name required for Grafana Admin (paired with JMESPath in Compose).
- **`GRAFANA_COOKIE_SECURE`**: set `true` when `GRAFANA_SERVER_ROOT_URL` uses `https://`.
- **Cloud deployment note**: use the same `GRAFANA_*` and `KEYCLOAK_*` keys in ECS/Fargate task env/secrets to keep behavior consistent with local compose.

OTLP ingest ports on `otel-lgtm` are localhost-bound by default in compose (`127.0.0.1:4317`, `127.0.0.1:4318`). Avoid exposing these publicly unless intentionally required and protected.

Full procedure: [grafana-keycloak.md](grafana-keycloak.md).

## Logs (Loki / Promtail / unified dashboard)

- **OTLP application logs**: Python services send logs when `OTEL_EXPORTER_OTLP_ENDPOINT` points at `otel-lgtm` (see [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml)); labels typically derive from `OTEL_SERVICE_NAME`.
- **Docker logs**: The `promtail` service ships selected container stdout to Loki (see [docker/promtail-config.yaml](../docker/promtail-config.yaml)) so Keycloak and other non-OTLP processes appear without duplicating OTLP apps.
- **Dashboard**: [docs/grafana-logs.md](grafana-logs.md) describes the **M8Flow Unified Logs** dashboard and LogQL examples.
