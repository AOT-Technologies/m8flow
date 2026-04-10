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

For `SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS` patterns (master realm, `admin-cli`, role mapping), see [extensions/m8flow-backend/keycloak/KEYCLOAK_SETUP.md](../extensions/m8flow-backend/keycloak/KEYCLOAK_SETUP.md).
