# Changelog

All notable changes to m8flow are recorded in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and m8flow follows
[Semantic Versioning](https://semver.org/); see the
[versioning policy](docs/reference/versioning.md). Each release lists its
changes under **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**,
**Security**, and **Breaking**; a **Breaking** entry says what to do before or
after you upgrade.

## [Unreleased]

### Added

* Open-source project policies: a [security policy](SECURITY.md) with private vulnerability reporting, a [contributing guide](CONTRIBUTING.md), a [code of conduct](CODE_OF_CONDUCT.md), [governance](GOVERNANCE.md), and [support](SUPPORT.md) pages, and issue templates.
* The repository is [REUSE](https://reuse.software/) compliant, and [DEPENDENCIES.md](DEPENDENCIES.md) lists the license of every runtime dependency. CI checks file licensing, dependency licenses and vulnerabilities, high-severity Bandit findings, secrets across the git history, and CodeQL, and runs the tests across the supported Python and Node.js versions.
* Final releases are tagged `X.Y.Z` with a signed tag, and their GitHub Release carries CycloneDX SBOMs, SHA-256 checksums, a Sigstore signature, and build-provenance attestations. See [Release and roll back m8flow](docs/how-to/release-and-roll-back.md) and the [versioning policy](docs/reference/versioning.md).
* `m8flow-designer` is now built and served by Docker Compose as the primary UI, on port **6853**.
* Global tenant selector for super-admins that scopes process-instance and task lists by the selected tenant.
* Named, multi-key-per-tenant NATS API keys (Manage Token page). Each key has its own name, optional process scope, optional expiry (30/90/365 days or never), and can be revoked independently, so an integration can rotate or revoke its key without affecting others. Key values are shown once at creation and never stored in plaintext.
* Built-in **NATS** monitoring page in m8flow-designer (**System → NATS**, `/system/nats`), replacing the removed third-party NUI embed. Super-admins see JetStream streams, per-consumer pending/acked figures with an Active/Lagging/Stalled state, and the most recent messages per stream, read live from the broker's own monitoring endpoints. NATS events are also recorded in a new event-audit table (outcome, failure reason, created process instance). Broker-wide endpoints are super-admin only, and tenant-admins read their own tenant's event history. All `/m8flow/nats/*` endpoints are read-only; raw payloads need `M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED` (off by default) and are redacted before they are truncated.
* The third-party NUI dashboard is no longer embedded in the **NATS** monitoring section. It could not be extended with the metrics we need (queued/pending counts, consumer lag, stream detail), had no m8flow authentication or tenant scoping, and could only be shown as an opaque cross-origin iframe.

### Changed

* The legacy `m8flow-frontend` service was removed from Docker Compose; `m8flow-designer` replaces it as the only UI container. The `m8flow-frontend/` tree, its image and its CI jobs are unchanged.
* `M8FLOW_BACKEND_URL_FOR_FRONTEND` now defaults to `http://localhost:6853`, so Keycloak's primary post-logout redirect targets the designer.
* Super-admin tenant filtering on the Template Library now also includes PUBLIC templates from other tenants (tenant-owned OR public), mirroring regular tenant scoping. Filtering by a tenant therefore returns that tenant's templates plus all public templates.
* NATS API key management (create/revoke) is now restricted to `tenant-admin` only; read access is `tenant-admin` and `super-admin`. (Previously `integrator` could also manage tokens.)

### Fixed

* The core 0.2.0 upgrade migration (`b2c3d4e5f6a7`) no longer aborts on `json_data` rows that nothing references. Those payloads (left behind by deleted tasks and instances) have no tenant to be scoped to and nothing can read them, so they are dropped and counted in the migration log. A missing payload, an unknown tenant or a null reference still aborts before anything is changed.
* The NATS API key migration (`7d4b1e9c3a20`) drops the old `m8flow_nats_api_key` placeholder table only when it is empty. Nothing reads it (keys live in `m8flow_nats_api_keys`); a placeholder that holds rows is left untouched.
* The MCP server image builds again. It is now built from the repository root (`docker build -f m8flow-mcp/Dockerfile .`) and installs `m8flow-telemetry` first, since pip cannot resolve that `uv` path dependency.
* The designer image can show **System → Celery** again: the Flower URL is a `VITE_M8FLOW_CELERY_FLOWER_URL` build arg (compose passes `M8FLOW_CELERY_FLOWER_URL`).
* Looking up a user by Keycloak identity no longer fails with `'UserModel' object has no attribute 'updated_at_in_seconds'` (a 500 on `/v1.0/onboarding` when the user's row came from another Keycloak host).
* A user reached through two Keycloak hosts no longer gets a second local account. Browsers use the public Keycloak URL and member sync used the internal one, so the same person could end up with two rows, and a NATS trigger naming that username failed with "User not found". Users are now matched by realm and Keycloak user ID, member sync uses the public issuer, and the NATS consumer starts existing duplicates as the account logins use. Two different people sharing a username are now reported as ambiguous.

### Security

* The NATS API key routes (`/m8flow/nats-tokens`) now enforce their tenant-admin grants. Before, any signed-in member of a tenant, including editors and reviewers, could create, list and revoke that tenant's keys.
* Permission checks count only the groups of the active tenant. A user who is tenant-admin in one organization no longer carries tenant-admin rights into another organization where they hold a lesser role.

### Breaking


* Upgrading from 1.0.x runs the destructive migration `c4d5e6f7a8b9`, which moves the database to the `m8flow-bpmn-core` 0.2.1 contract. It copies human-task assignments to work items and drops `human_task`, `human_task_user`, and the old digest, serializer, tenant-identity, URI-target, and epoch timestamp columns. A downgrade restores the old structure only, not the removed values. **Back up the databases, and stop the backend, the Celery worker and Flower, the NATS consumer, and the notification worker before you migrate.** The migration aborts before changing anything if it finds ambiguous process digests, orphaned task assignments, or other data it can't convert. On MySQL and MariaDB a failed migration isn't rolled back, so restore the backup instead of retrying. See [Upgrade from 1.0.x to 2.0](docs/how-to/upgrade.md#upgrade-from-10x-to-20).
* `GET /v1.0/m8flow/task-review` now returns **403 Forbidden** when the caller lacks the dedicated Task Review permission. Previously, unauthorized callers received a successful empty page, which was indistinguishable from having no assigned tasks. Authorized callers with no tasks still receive an empty page. Update API clients that treated the previous 200 response as an empty inbox.
* NATS triggers now require `M8FLOW_NATS_TOKEN_SALT` to be a private value of at least 32 characters, set identically on the backend and `m8flow-nats-consumer` (generate one with `openssl rand -hex 32`). The salt signs each trigger event so the broker never carries a usable API key. While it is unset, a placeholder published in this repo (such as `changeme_nats_salt` from `sample.env`), or shorter than 32 characters, `POST /v1.0/m8flow/events/m8flow-trigger` answers `503 nats_signing_not_configured`, the backend logs an error at boot, and `m8flow-nats-consumer` refuses to start. It also refuses to start when `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` is not a positive whole number. **Set the salt before upgrading any deployment with `M8FLOW_NATS_ENABLED=true`.** Changing the salt invalidates NATS API keys already issued, so re-issue them from the Manage Token page.
* Signed NATS trigger events are only accepted within `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` (default 300) of being issued, so a captured event cannot be replayed. Triggers that wait in the stream longer than that, such as through a consumer outage, are dropped instead of being processed late. They are recorded with the new outcome `rejected_stale` (shown as *Rejected: stale* on the NATS page and in the consumer's failures-by-outcome metric), so they can be alerted on apart from forged events; see the [consumer runbook](m8flow-nats-consumer/README.md#runbook-triggers-dropped-as-rejected_stale).
* `M8FLOW_FRONTEND_PORT` now defaults to **6853** (was 6841) and maps the `m8flow-designer` service. Existing `.env` files keep their old value and will serve the designer on 6841 until updated; bookmarks to `http://localhost:6841` stop working. Keycloak redirect URIs change with it, so the realm must be re-imported for sign-out to land on the new origin.
* The `nats-ui` service and its `nui-db` volume are removed from [docker/m8flow-nats-docker-compose.yml](docker/m8flow-nats-docker-compose.yml), freeing host port `6852`. The `M8FLOW_NATS_UI_URL` and `M8FLOW_NATS_UI_PORT` settings are replaced by `M8FLOW_NATS_MONITORING_ENABLED` (default `false`), which gates the backend NATS monitoring API. Deployments that set `M8FLOW_NATS_UI_URL` must switch to `M8FLOW_NATS_MONITORING_ENABLED=true` for the **NATS** page to load data, and can reclaim disk with `docker volume rm m8flow-nats-stack_nui-db`.
* The legacy single-token-per-tenant NATS model (`m8flow_nats_tokens`) is removed on upgrade and replaced by named API keys (`m8flow_nats_api_keys`). Because legacy tokens are stored only as one-way hashes and use an incompatible format, they cannot be migrated. **All existing NATS trigger integrations stop working after upgrade and must generate a new key** from the Manage Token page (tenant-admin). Coordinate this rollout with integration owners. The Alembic downgrade recreates the legacy table structure but does not restore any token values.

## [1.0.0] - 2026-03-31

### Added

* Initial release with features
    * Multi-tenant Workflow Engine
    * Workflow Template Library
    * Connectors
    * Event-based Workflow Execution

### Known issues

* In this release, only Docker deployment is supported.
* Local backend and frontend development are not available.

[Unreleased]: https://github.com/AOT-Technologies/m8flow/compare/1.0.0...HEAD
[1.0.0]: https://github.com/AOT-Technologies/m8flow/releases/tag/1.0.0
