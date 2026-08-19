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
| `M8FLOW_VAULT_PORT` | `8200` | Vault API and built-in UI on host (`/ui/`) |
| `M8FLOW_NATS_PORT` | `6845` | NATS client port ([m8flow-nats-docker-compose.yml](../docker/m8flow-nats-docker-compose.yml)) |
| `MINIO_API_PORT` | `6846` | MinIO S3 API on host |
| `MINIO_CONSOLE_PORT` | `6847` | MinIO console on host |
| `REDIS_HOST_PORT` | `6848` | Redis on host |
| `M8FLOW_BACKEND_CELERY_FLOWER_PORT` | `6850` | Celery Flower (host and in-container bind) |
| `M8FLOW_NATS_MONITORING_PORT` | `6851` | NATS monitoring (host → container 8222) |
| `MINIO_LOCAL_DEV_API_PORT` | `16846` | Standalone MinIO dev API ([minio.local-dev.docker-compose.yml](../docker/minio.local-dev.docker-compose.yml)) |
| `MINIO_LOCAL_DEV_CONSOLE_PORT` | `16847` | Standalone MinIO dev console |

Also align URL-style settings with the above (e.g. `M8FLOW_BACKEND_URL`, `KEYCLOAK_HOSTNAME`, `M8FLOW_BACKEND_DATABASE_URI` host port, `M8FLOW_NATS_URL`).

## Keycloak URLs

- `KEYCLOAK_HOSTNAME`: Browser/public base URL used to reach Keycloak (for example `http://localhost:6842`). If clients access from another machine, use `http://<host>:6842` (or your real hostname and port).
- `KEYCLOAK_HOSTNAME_URL`: Public Keycloak base URL Keycloak uses for token issuer (`iss`). In this repo’s Docker Compose, `KC_HOSTNAME_URL` is wired from `KEYCLOAK_HOSTNAME`; set `KEYCLOAK_HOSTNAME` consistently with how users reach Keycloak.
- `KEYCLOAK_HOSTNAME_HOST` (optional): Hostname segment passed to Keycloak as `KC_HOSTNAME` in [docker/m8flow-docker-compose.yml](../docker/m8flow-docker-compose.yml) (default `localhost`). Adjust if your deployment needs a different hostname for Keycloak’s own hostname configuration.
- `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL`: Backend URL for Keycloak Admin/API calls. **Docker Compose:** set by compose to `http://keycloak-proxy:6842` for `m8flow-backend` (internal network). **Local dev:** often `http://localhost:6842` to match the proxy port on the host.
- `M8FLOW_APP_PUBLIC_BASE_URL` (optional): Set when the app and Keycloak are exposed on different public hosts. If unset, `KEYCLOAK_HOSTNAME` is used for generated app-facing URLs where applicable.
- `M8FLOW_KEYCLOAK_SHARED_REALM` (optional): Shared tenant-user realm name used by M8Flow auth defaults and local Keycloak bootstrap. Default: `m8flow`.
- `M8FLOW_KEYCLOAK_MASTER_REALM` (optional): Platform/bootstrap admin realm name used by M8Flow auth defaults and local Keycloak bootstrap. Default: `master`.
- `M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS` (optional): Organization alias the Keycloak bootstrap ensures exists inside the shared realm. Default: the shared realm name, usually `m8flow`.
- `M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME` (optional): Display name used when the bootstrap creates the default shared-realm organization. Default: the default organization alias.

## Frontend monitoring dashboards (super-admin)

The UI embeds the Celery and NATS operations dashboards as super-admin-only sections (sidebar **Celery** / **NATS**) via an iframe, so operators no longer leave the app. URLs must be **browser-reachable** (resolved from the user's browser, not from inside a container).

- `M8FLOW_CELERY_FLOWER_URL` (optional): URL of the Celery Flower dashboard embedded in the **Celery** section. Default `http://localhost:6850` (matches `M8FLOW_BACKEND_CELERY_FLOWER_PORT`). Flower keeps its own basic auth (`M8FLOW_BACKEND_CELERY_FLOWER_BASIC_AUTH`), so a basic-auth prompt may appear inside the embedded frame.
- `M8FLOW_NATS_MONITORING_ENABLED` (optional): shows the **NATS** monitoring section, served by the built-in dashboard rather than an embedded third-party UI. **`false` by default**, matching `M8FLOW_NATS_ENABLED`; set to `true` when running the optional [m8flow-nats-docker-compose.yml](../docker/m8flow-nats-docker-compose.yml). (Replaces the removed `M8FLOW_NATS_UI_URL`, which pointed at the third-party NUI dashboard.)

- `M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED` (optional): allows raw message payloads to be read through the monitoring API and shown in the UI. **`false` by default** — payloads carry tenant business data and notification recipients, and m8flow's streams retain them indefinitely. Even when enabled, browsing a stream by sequence (`/nats/streams/{name}/messages`) stays super-admin only; a tenant-admin sees the payload of an event in their own tenant, because the stream and the sequence are both taken from the tenant-scoped audit row rather than from the request. Reads never acknowledge a message.
- `M8FLOW_GRAFANA_URL` (optional): browser-reachable Grafana URL, linked from the NATS **Overview** tab for metric history. Empty hides the link. Grafana runs with anonymous auth disabled, so it is linked to rather than embedded.

These are consumed by the frontend at build time (`VITE_*`) and at runtime in Docker (injected into `window.spiffworkflowFrontendJsenv` by [docker/scripts/m8flow_frontend_entrypoint.sh](../docker/scripts/m8flow_frontend_entrypoint.sh)). If an embedded dashboard refuses framing (e.g. via `X-Frame-Options`), the section shows an "Open in new tab" fallback.

Backend-side NATS monitoring settings:

- `M8FLOW_NATS_MONITORING_URL` (optional): base URL of the NATS server's monitoring endpoints. Default `http://nats:8222`, reached over the internal docker network, so the monitoring port never needs publishing to a browser.
- `M8FLOW_NATS_MESSAGE_PREVIEW_MAX_BYTES` (optional): cap on how much of a payload a preview returns. Default `4096`.
- `M8FLOW_NATS_AUDIT_RETENTION_DAYS` (optional): how long terminal event-audit rows are kept before the notification worker's sweep prunes them. Default `90`; `0` disables pruning. In-flight (`queued`) rows are never pruned.
- `M8FLOW_NATS_BROKER_METRICS_INTERVAL_SECONDS` (optional): how often `m8flow-nats-consumer` polls the broker to emit per-stream/per-consumer metrics feeding the "M8Flow NATS Trigger Consumer Overview" and "M8Flow NATS Notification Worker Overview" Grafana dashboards. Default `20`. Coupled to `OTEL_METRIC_EXPORT_INTERVAL` (default `60000`ms) — polling faster than roughly half that interval buys nothing, since an OTel gauge is last-value-wins per export tick.

## Connector attachment paths

For SMTP and Slack connectors:

- `*_ATTACHMENTS_DIR`: Host/source path where files are read from.
- `*_ATTACHMENTS_USER_ACCESS_DIR`: User-visible mounted path used in service-task file selection.

Examples:

- `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_DIR=../data/email_attachments`
- `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_USER_ACCESS_DIR=/data/email_attachments`
- `M8FLOW_CONNECTOR_SLACK_ATTACHMENTS_DIR=../data/slack_attachments`
- `M8FLOW_CONNECTOR_SLACK_ATTACHMENTS_USER_ACCESS_DIR=/data/slack_attachments`

## Vault

- `M8FLOW_VAULT_ENABLED` (optional): When `true`, the backend switches completely to Vault-backed secrets. Legacy database secrets are not read or written in this mode. This is a runtime cutover flag, not a data migration; enabling it does not copy database secrets into Vault, and disabling it does not copy Vault secrets back into the database. See [vault-local-development.md](./vault-local-development.md) for the current runtime auth flow, failure behavior, audit log usage, and migration/rollback notes.
- `M8FLOW_VAULT_ADDR` / `VAULT_ADDR` (optional): Base URL of the Vault API, for example `https://vault.example.com`.
- `M8FLOW_VAULT_TOKEN` / `VAULT_TOKEN` (optional): Broker/control-plane token used by backend Vault operations. Use this for manual token-based runtime auth.
- `M8FLOW_VAULT_TOKEN_FILE` / `VAULT_TOKEN_FILE` (optional): File containing a Vault token. Useful when the runtime token is mounted into the container instead of injected directly as an env var.
- `M8FLOW_VAULT_ROLE_ID` / `VAULT_ROLE_ID` (optional): Broker/control-plane Vault AppRole role ID used by backend Vault operations.
- `M8FLOW_VAULT_ROLE_ID_FILE` / `VAULT_ROLE_ID_FILE` (optional): File containing the Vault AppRole role ID.
- `M8FLOW_VAULT_SECRET_ID` / `VAULT_SECRET_ID` (optional): Broker/control-plane Vault AppRole secret ID used by backend Vault operations.
- `M8FLOW_VAULT_SECRET_ID_FILE` / `VAULT_SECRET_ID_FILE` (optional): File containing the Vault AppRole secret ID.
- `M8FLOW_VAULT_NAMESPACE` / `VAULT_NAMESPACE` (optional): Vault Enterprise namespace when your deployment uses namespaced auth and KV mounts.
- `M8FLOW_VAULT_MOUNT_POINT` (optional): KV v2 mount used for M8Flow-managed secrets. Default: `kv`.
- `M8FLOW_VAULT_SECRET_PATH_PREFIX` (optional): Prefix within the KV mount used as the root namespace for derived secret paths such as `m8flow/tenants/{tenant_id}/secrets/{secret_name}`. Default: `m8flow`.
- `M8FLOW_VAULT_APPROLE_MOUNT_POINT` (optional): Vault auth mount used when M8Flow provisions per-tenant AppRoles. Default: `approle`.
- `M8FLOW_VAULT_TENANT_POLICY_PREFIX` (optional): Prefix used for auto-created per-tenant Vault ACL policies. Effective policy names look like `{prefix}-{tenant_id}` after Vault-safe normalization. Default: `m8flow-tenant-policy`.
- `M8FLOW_VAULT_TENANT_ROLE_PREFIX` (optional): Prefix used for auto-created per-tenant Vault AppRoles. Effective role names look like `{prefix}-{tenant_id}` after Vault-safe normalization. Default: `m8flow-tenant-role`.
- `M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES` (optional): How many times a generated tenant AppRole `secret_id` may be used. Default: `1`.
- `M8FLOW_VAULT_TENANT_SECRET_ID_TTL` (optional): TTL assigned to generated tenant AppRole `secret_id` values. Default: `10m`.
- `M8FLOW_VAULT_TENANT_TOKEN_TTL` (optional): Initial TTL assigned to tenant AppRole login tokens. Default: `10m`.
- `M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL` (optional): Maximum TTL assigned to tenant AppRole login tokens. Default: `30m`.
- `M8FLOW_VAULT_TIMEOUT_SECONDS` (optional): Request timeout for Vault API calls. Default: `5`.
- `M8FLOW_VAULT_SKIP_VERIFY` / `VAULT_SKIP_VERIFY` (optional): Set to `true` only when TLS certificate verification must be disabled for a non-production environment.
- `M8FLOW_VAULT_CACERT` / `VAULT_CACERT` (optional): CA bundle path used to verify Vault TLS certificates. When set, it takes precedence over `*_SKIP_VERIFY`.
- `M8FLOW_VAULT_PORT` (optional, Docker Compose local dev): Host port that publishes the local Vault API and built-in UI. Default: `8200`.
- `M8FLOW_VAULT_DEMO_OVERWRITE` (optional, Docker Compose local dev): When `true`, the `vault-demo` bootstrap overwrites secrets defined in your local `docker/vault/demo/secrets.yml` file. Start from `docker/vault/demo/secrets.yml.sample` when you want real demo secrets. If the file is absent, `vault-demo` still bootstraps Vault and tenant identities but does not seed any tenant secret. Default: `false`.

Tenant AppRole lifetime settings:

- These four `M8FLOW_VAULT_TENANT_*` variables apply to the per-tenant AppRoles that M8Flow creates automatically for tenant secret access.
- They are passed through to Vault when M8Flow creates or updates the tenant AppRole role definition.
- They do not configure the shared broker/control-plane AppRole used by the local `vault-demo` bootstrap.

- `M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES`
  Integer. Default `1`.
  Controls how many AppRole logins a newly generated tenant `secret_id` may perform before Vault rejects it.
  `1` means single-use. `0` means unlimited reuse.
  In the current M8Flow flow, a fresh tenant `secret_id` is minted when the app builds a tenant-scoped Vault client, so `1` is the safer default.

- `M8FLOW_VAULT_TENANT_SECRET_ID_TTL`
  Vault duration string such as `10m`, `1h`, or `24h`. Default `10m`.
  Controls how long a generated tenant `secret_id` stays valid if it is not used immediately.
  This limits the exposure window of a leaked but unused `secret_id`.

- `M8FLOW_VAULT_TENANT_TOKEN_TTL`
  Vault duration string. Default `10m`.
  Controls the initial lease duration of the Vault client token returned after a successful tenant AppRole login.
  This is the token that actually performs the tenant secret read, write, delete, or list operation.

- `M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL`
  Vault duration string. Default `30m`.
  Controls the maximum lifetime Vault will allow for tokens issued from that tenant AppRole, including renewal limits when renewal is used.
  This should normally be greater than or equal to `M8FLOW_VAULT_TENANT_TOKEN_TTL`.
  Example: if `M8FLOW_VAULT_TENANT_TOKEN_TTL=10m` and `M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL=30m`, Vault issues the tenant token with `10m` initially. If renewal is used, it can be extended, but never past `30m` total.

Practical guidance:

- Lower values reduce the useful lifetime of leaked credentials, but make slow or long-running flows less tolerant.
- Higher values reduce re-authentication frequency, but increase the window in which a leaked `secret_id` or tenant token remains useful.
- For request-driven secret access, the current defaults are intentionally short-lived: single-use `secret_id`, `10m` initial token TTL, and `30m` max token TTL.

Per-tenant Vault identity notes:

- When `M8FLOW_VAULT_ENABLED=true`, tenant creation now provisions Vault-side isolation artifacts automatically.
- The create-tenant API writes a tenant-scoped ACL policy limited to `kv/data|metadata/<prefix>/tenants/{tenant_id}/secrets/...` and creates a matching AppRole for that tenant.
- Shared-realm bootstrap also provisions the default `m8flow` tenant's Vault identity after it reconciles the canonical tenant UUID.
- The configured runtime token or runtime AppRole is now a broker/control-plane identity. M8Flow uses it to manage tenant policies/AppRoles and to mint tenant-scoped Vault clients for tenant secret CRUD.
- A healthy configuration does not let that broker identity read tenant secret values directly; only the derived tenant-scoped client should have data-plane access inside `tenants/{tenant_id}/secrets/...`.
- On a brand-new tenant, M8Flow generates an initial AppRole `secret_id`. On later startup/bootstrap passes, the role and policy are reconciled idempotently without rotating that `secret_id`.
- By default, tenant AppRoles are provisioned with `secret_id_num_uses=1`, `secret_id_ttl=10m`, `token_ttl=10m`, and `token_max_ttl=30m`. Override those with the `M8FLOW_VAULT_TENANT_*` settings when your environment needs different values.

Local Docker Compose notes:

- Browser and host-side CLI URL: `http://127.0.0.1:${M8FLOW_VAULT_PORT:-8200}`
- Backend and Celery in Compose use the service DNS name: `http://vault:8200`
- Set `M8FLOW_VAULT_ENABLED=true` in your local `.env` when you want the Compose backend/Celery services to use Vault-backed secrets. The `vault-demo` profile supplies connection and AppRole runtime files, but it does not force the enable flag.
- The local `vault-demo` profile still creates one shared development broker policy/AppRole (`m8flow`) for backend/Celery startup. That identity is separate from the per-tenant AppRoles created by M8Flow when tenants are provisioned, and it should not read tenant secrets directly.
- The `vault-demo` profile writes encrypted AppRole credential files, `runtime.env`, and verification artifacts into the named Docker volume mounted at `/vault/demo`.
- The `vault-demo` bootstrap resolves the shared-realm `m8flow` organization to its canonical tenant UUID before it writes seeded secrets, so there is no post-start metadata mirror phase.
- In Vault KV v2, empty folders are not real persisted objects. A tenant secrets path becomes visible in the Vault UI only after the first real secret is written under `tenants/{tenant_id}/secrets/...`.
- Do not point containerized backend/Celery startup at `http://localhost:8200`; inside those containers, `localhost` is the container itself.
- See [vault-local-development.md](./vault-local-development.md) for init, unseal, policy bootstrap, and reset steps.

## Advanced Keycloak auth configs

For `SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS` patterns (master realm, `admin-cli`, role mapping), see [m8flow-backend/keycloak/KEYCLOAK_SETUP.md](../m8flow-backend/keycloak/KEYCLOAK_SETUP.md).
