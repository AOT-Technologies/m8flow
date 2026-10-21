# Configuration

m8flow reads its configuration from environment variables. Compose loads them
from the `.env` file at the repository root, which you create from
[`sample.env`](../../sample.env). This page lists the variables you're most
likely to change. `sample.env` holds the complete set, with a comment on each.

For the port variables, see [Services and ports](services-and-ports.md).

## Values to replace before deploying

The sample values are for local use only. Outside local development, replace
every value in the following table:

| Variable | What it protects |
|---|---|
| `FLASK_SESSION_SECRET_KEY` | Session signing. Also the fallback key for secret encryption. The backend refuses to start without it. |
| `M8FLOW_SECRETS_ENCRYPTION_KEY` | Encryption of stored tenant secrets. Falls back to `FLASK_SESSION_SECRET_KEY` when unset. |
| `M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET` | The backend's Keycloak client secret |
| `M8FLOW_CONNECTOR_PROXY_API_KEY` | Calls from the backend to the connector proxy. Compose refuses to start without it. |
| `M8FLOW_NATS_TOKEN_SALT` | API-key hashes and trigger signatures. At least 32 characters. |
| `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD`, `KC_DB_PASSWORD` | Database access |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak administration |
| `MINIO_ROOT_PASSWORD` | Object storage |
| `M8FLOW_BACKEND_CELERY_FLOWER_BASIC_AUTH` | The Flower UI |

## Backend

| Variable | Default in `sample.env` | Meaning |
|---|---|---|
| `M8FLOW_BACKEND_ENV` | `local_development` | Environment name. Outside `local_development` and `unit_testing`, auth cookies are marked `Secure`. |
| `M8FLOW_BACKEND_DATABASE_URI` | `postgresql+psycopg://postgres:postgres@localhost:6843/postgres` | SQLAlchemy URI for the m8flow database. Compose sets the in-network value for containers. |
| `M8FLOW_BACKEND_UPGRADE_DB` | `true` | Run Alembic migrations at startup |
| `M8FLOW_BACKEND_LOG_LEVEL` | `INFO` | Log level |
| `M8FLOW_BACKEND_URL` | `http://localhost:6840` | Public backend URL |
| `M8FLOW_BACKEND_URL_FOR_FRONTEND` | `http://localhost:6853` | Designer URL that the backend redirects to after sign-in and sign-out |
| `M8FLOW_BACKEND_CORS_ALLOW_ORIGINS` | Local designer origins | Extra browser origins allowed to call the API with credentials, comma-separated |
| `M8FLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH` | `m8flow.yml` in the backend config | The permission policy file |
| `MULTI_TENANT_ON` | `true` | Turns the tenant selection routes on or off |

## Storage

| Variable | Default in `sample.env` | Meaning |
|---|---|---|
| `M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR` | `./data/process_models` | Root of the process-model catalog. Each tenant gets a subfolder. |
| `M8FLOW_TEMPLATES_STORAGE_DIR` | `./data/templates` | Root of template storage |
| `M8FLOW_LOAD_SAMPLE_TEMPLATES` | `true` | Load the sample templates at startup. Skips templates that already exist. |

## Keycloak and sign-in

| Variable | Default | Meaning |
|---|---|---|
| `KEYCLOAK_HOSTNAME` | `http://localhost:6842` | Keycloak URL as browsers reach it. Keycloak also uses it as the token issuer, so it must match how users reach Keycloak. |
| `KEYCLOAK_URL`, `M8FLOW_KEYCLOAK_URL` | `http://localhost:6842` | Keycloak URL as the backend reaches it. Compose sets `http://keycloak-proxy:6842` for containers. |
| `M8FLOW_BACKEND_OPEN_ID_SERVER_URL` | `http://localhost:6842/realms/m8flow` | OpenID Connect issuer of the shared realm |
| `M8FLOW_BACKEND_OPEN_ID_CLIENT_ID` | `m8flow-backend` | The backend's Keycloak client |
| `M8FLOW_KEYCLOAK_SHARED_REALM` | `m8flow` | Realm where tenant users sign in |
| `M8FLOW_KEYCLOAK_MASTER_REALM` | `master` | Realm where platform administrators sign in |
| `M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS` | The shared realm name | Organization that the Keycloak bootstrap creates in the shared realm |
| `M8FLOW_APP_PUBLIC_BASE_URL` | Unset | Public app URL, when the app and Keycloak use different hosts |
| `M8FLOW_AUTH_PROVIDER` | `keycloak` | Which auth provider the backend loads. See [the auth provider guide](../auth-provider/README.md). |

## Invitations and email

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_FRONTEND_BASE_URL` | `http://localhost:6853` | Designer URL used in invitation links |
| `M8FLOW_SMTP_HOST` | Unset | SMTP server for invitation emails. When unset, m8flow doesn't send email and returns the link in the API response instead. |
| `M8FLOW_SMTP_PORT`, `M8FLOW_SMTP_USERNAME`, `M8FLOW_SMTP_PASSWORD`, `M8FLOW_SMTP_FROM`, `M8FLOW_SMTP_USE_TLS` | Unset | The rest of the SMTP settings |

## Background jobs

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_BACKEND_CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery broker |
| `M8FLOW_BACKEND_CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Celery result store |
| `M8FLOW_BACKEND_CELERY_AUTOSCALE_MIN`, `M8FLOW_BACKEND_CELERY_AUTOSCALE_MAX` | `2`, `4` | Worker pool size range |
| `M8FLOW_SCHEDULER_POLL_SECONDS` | `10` | How often the scheduler looks for due timers |

## Connectors and secrets

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_BACKEND_CONNECTOR_PROXY_URL` | `http://localhost:6844` | Connector proxy URL. Compose sets the in-network value. |
| `M8FLOW_CONNECTOR_PROXY_API_KEY` | A local value | Shared key, sent as `X-M8FLOW-Connector-Proxy-Key` |
| `NW_ALLOWED_CONNECTORS` | Set in Compose | Connectors that `m8flow-node-wire-proxy` allows |
| `M8FLOW_SECRET_BACKEND_KIND` | `database` | Where tenant secrets live: `database` (encrypted in PostgreSQL) or `vault` (HashiCorp Vault KV v2) |
| `VAULT_ADDR`, `VAULT_NAMESPACE`, `VAULT_CACERT` | Unset | Vault connection settings, when the backend kind is `vault` |

## NATS triggers

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_NATS_ENABLED` | `false` | Turns on NATS triggers |
| `M8FLOW_NATS_URL` | `nats://admin:admin@localhost:6845` | NATS server URL |
| `M8FLOW_NATS_TOKEN_SALT` | A placeholder | Secret for API-key hashes and trigger signatures. Shared by the backend and the consumer. |
| `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` | `300` | Oldest signed trigger the consumer accepts |
| `M8FLOW_NATS_DEDUP_TTL` | `86400` | How long, in seconds, the consumer remembers an event ID to drop duplicates |
| `M8FLOW_NATS_MONITORING_ENABLED` | `false` | Turns on the API behind the super-admin **NATS** page |
| `M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED` | `false` | Lets the **NATS** page read raw message payloads. Payloads carry tenant business data. |
| `M8FLOW_NATS_AUDIT_RETENTION_DAYS` | `90` | How long event-audit rows are kept. `0` keeps them forever. |

## MCP server

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_MCP_SERVER_URL` | Empty | Browser-reachable MCP endpoint, ending in `/mcp`. Empty hides **MCP Connection**. |
| `M8FLOW_MCP_SERVER_INTERNAL_URL` | Empty | Local Docker only: the MCP URL as the backend container reaches it |

[Set up the MCP server and MCP Tools](../how-to/set-up-mcp-tools.md) explains
the full setup.

## Designer build settings

The designer reads these values when its image is built, not when it runs.
Rebuild the `m8flow-designer` image after you change them.

| Variable | Default | Meaning |
|---|---|---|
| `M8FLOW_FRONTEND_BACKEND_BASE_URL` | `http://localhost:6840` | Backend URL the browser uses for sign-in and sign-out. Becomes `VITE_BACKEND_BASE_URL`. |
| `M8FLOW_MCP_SERVER_URL` | Empty | Becomes `VITE_MCP_SERVER_URL` |
| `M8FLOW_CELERY_FLOWER_URL` | Empty | Becomes `VITE_M8FLOW_CELERY_FLOWER_URL`. Empty hides **System** > **Celery**. |

At run time, the designer container forwards `/v1.0` to `BACKEND_BASE_URL`,
which Compose sets to the backend's in-network address.

## Observability

| Variable | Default | Meaning |
|---|---|---|
| `OTEL_SDK_DISABLED` | `true` | Set to `false` to send logs, metrics, and traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://m8flow-alloy:4317` | Where to send OpenTelemetry data |
| `M8FLOW_SQL_SLOW_MS` | `100` | Threshold for `sql query slow` log lines. `0` logs every statement and `off` turns the lines off. |
| `M8FLOW_FRONTEND_FARO_COLLECTOR_URL` | Empty | Browser telemetry collector. Empty turns browser telemetry off. |

## Related pages

- [Services and ports](services-and-ports.md)
- [Enable logs, metrics, and traces](../how-to/enable-observability.md)
