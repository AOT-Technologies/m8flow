# Changelog for m8flow

## Unreleased

`Added`

* `m8flow-designer` is now built and served by Docker Compose as the primary UI, on port **6853**.
* Global tenant selector for super-admins that scopes process-instance and task lists by the selected tenant.
* Named, multi-key-per-tenant NATS API keys (Manage Token page). Each key has its own name, optional process scope, optional expiry (30/90/365 days or never), and can be revoked independently, so an integration can rotate or revoke its key without affecting others. Key values are shown once at creation and never stored in plaintext.

`Changed`

* The legacy `m8flow-frontend` service was removed from Docker Compose; `m8flow-designer` replaces it as the only UI container. The `m8flow-frontend/` tree, its image and its CI jobs are unchanged.
* `M8FLOW_BACKEND_URL_FOR_FRONTEND` now defaults to `http://localhost:6853`, so Keycloak's primary post-logout redirect targets the designer.
* Super-admin tenant filtering on the Template Library now also includes PUBLIC templates from other tenants (tenant-owned OR public), mirroring regular tenant scoping. Filtering by a tenant therefore returns that tenant's templates plus all public templates.
* NATS API key management (create/revoke) is now restricted to `tenant-admin` only; read access is `tenant-admin` and `super-admin`. (Previously `integrator` could also manage tokens.)

`Breaking`

* `M8FLOW_FRONTEND_PORT` now defaults to **6853** (was 6841) and maps the `m8flow-designer` service. Existing `.env` files keep their old value and will serve the designer on 6841 until updated; bookmarks to `http://localhost:6841` stop working. Keycloak redirect URIs change with it, so the realm must be re-imported for sign-out to land on the new origin.
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

