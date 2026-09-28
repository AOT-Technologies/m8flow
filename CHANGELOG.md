# Changelog for m8flow

## Unreleased

`Added`

* `m8flow-designer` is now built and served by Docker Compose as the primary UI, on port **6853**.
* Global tenant selector for super-admins that scopes process-instance and task lists by the selected tenant.
* Named, multi-key-per-tenant NATS API keys (Manage Token page). Each key has its own name, optional process scope, optional expiry (30/90/365 days or never), and can be revoked independently, so an integration can rotate or revoke its key without affecting others. Key values are shown once at creation and never stored in plaintext.
* Built-in **NATS** monitoring page in m8flow-designer (**System → NATS**, `/system/nats`), replacing the removed third-party NUI embed. Super-admins see JetStream streams, per-consumer pending/acked figures with an Active/Lagging/Stalled state, and the most recent messages per stream, read live from the broker's own monitoring endpoints. NATS events are also recorded in a new event-audit table (outcome, failure reason, created process instance). Broker-wide endpoints are super-admin only, and tenant-admins read their own tenant's event history. All `/m8flow/nats/*` endpoints are read-only; raw payloads need `M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED` (off by default) and are redacted before they are truncated.
* The third-party NUI dashboard is no longer embedded in the **NATS** monitoring section. It could not be extended with the metrics we need (queued/pending counts, consumer lag, stream detail), had no m8flow authentication or tenant scoping, and could only be shown as an opaque cross-origin iframe.

`Changed`

* The legacy `m8flow-frontend` service was removed from Docker Compose; `m8flow-designer` replaces it as the only UI container. The `m8flow-frontend/` tree, its image and its CI jobs are unchanged.
* `M8FLOW_BACKEND_URL_FOR_FRONTEND` now defaults to `http://localhost:6853`, so Keycloak's primary post-logout redirect targets the designer.
* Super-admin tenant filtering on the Template Library now also includes PUBLIC templates from other tenants (tenant-owned OR public), mirroring regular tenant scoping. Filtering by a tenant therefore returns that tenant's templates plus all public templates.
* NATS API key management (create/revoke) is now restricted to `tenant-admin` only; read access is `tenant-admin` and `super-admin`. (Previously `integrator` could also manage tokens.)

`Security`

* The NATS API key routes (`/m8flow/nats-tokens`) now enforce their tenant-admin grants. Before, any signed-in member of a tenant, including editors and reviewers, could create, list and revoke that tenant's keys.
* Permission checks count only the groups of the active tenant. A user who is tenant-admin in one organization no longer carries tenant-admin rights into another organization where they hold a lesser role.

`Breaking`

* `M8FLOW_FRONTEND_PORT` now defaults to **6853** (was 6841) and maps the `m8flow-designer` service. Existing `.env` files keep their old value and will serve the designer on 6841 until updated; bookmarks to `http://localhost:6841` stop working. Keycloak redirect URIs change with it, so the realm must be re-imported for sign-out to land on the new origin.
* The `nats-ui` service and its `nui-db` volume are removed from [docker/m8flow-nats-docker-compose.yml](docker/m8flow-nats-docker-compose.yml), freeing host port `6852`. The `M8FLOW_NATS_UI_URL` and `M8FLOW_NATS_UI_PORT` settings are replaced by `M8FLOW_NATS_MONITORING_ENABLED` (default `false`), which gates the backend NATS monitoring API. Deployments that set `M8FLOW_NATS_UI_URL` must switch to `M8FLOW_NATS_MONITORING_ENABLED=true` for the **NATS** page to load data, and can reclaim disk with `docker volume rm m8flow-nats-stack_nui-db`.
* The legacy single-token-per-tenant NATS model (`m8flow_nats_tokens`) is removed on upgrade and replaced by named API keys (`m8flow_nats_api_keys`). Because legacy tokens are stored only as one-way hashes and use an incompatible format, they cannot be migrated. **All existing NATS trigger integrations stop working after upgrade and must generate a new key** from the Manage Token page (tenant-admin). Coordinate this rollout with integration owners. The Alembic downgrade recreates the legacy table structure but does not restore any token values.

## 1.0.0 - 2026-03-31

`Added`

* Initial release with features
    * Multi-tenant Workflow Engine
    * Workflow Template Library
    * Connectors
    * Event-based Workflow Execution

`Known Issues`

* In this release, only Docker deployment is supported.
* Local backend and frontend development are not available.

