# Extensions

This directory contains the Apache-2.0 m8flow-specific code layered on top of the upstream `m8flow-core` code fetched into the repo at development or build time.

The main rule is simple: upstream workflow engine code lives outside this folder, and m8flow-specific behavior lives inside this folder. When possible, extend or override upstream behavior here instead of modifying the fetched upstream directories directly.

## What Lives Here

```text
extensions/
|-- app.py                    ASGI entrypoint used by the backend runtime
|-- bootstrap.py              Pre-app and post-app patch bootstrap helpers
|-- startup/                  Shared backend startup, patching, and request wiring
|-- m8flow-backend/           Backend extension package
`-- m8flow-frontend/          Frontend extension app
```

## Responsibilities

### `m8flow-backend/`

The backend extension adds m8flow-specific server behavior on top of `spiffworkflow-backend`, including:

- multi-tenant APIs and tenant context handling
- Keycloak integration and realm provisioning support
- m8flow database models and migrations
- background processing and service-layer logic
- sample templates and local-development helpers
- unit and integration tests for extension behavior

Important subdirectories:

```text
extensions/m8flow-backend/
|-- bin/                      Local run, migration, sync, and setup scripts
|-- keycloak/                 Keycloak bootstrap docs and realm assets
|-- migrations/               Alembic migrations for m8flow-owned tables
|-- sample_templates/         Seed templates for local/dev bootstrap
|-- src/m8flow_backend/       Extension source code
`-- tests/                    Unit and integration tests
```

Inside `src/m8flow_backend/`, the main code is organized into areas such as:

- `routes/` for API endpoints
- `services/` for application logic
- `models/` for persistence models
- `auth_provider/` for auth integration
- `background_processing/` for async and worker flows
- `helpers/`, `utils/`, and `config/` for supporting infrastructure

Useful backend entrypoints:

- `extensions/m8flow-backend/bin/run_m8flow_backend.sh`
- `extensions/m8flow-backend/bin/run_m8flow_backend.ps1`
- `extensions/m8flow-backend/bin/run_m8flow_alembic.sh`
- `extensions/m8flow-backend/bin/run_m8flow_alembic.ps1`
- `extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh`
- `extensions/m8flow-backend/bin/run_m8flow_celery_worker.ps1`
- `extensions/m8flow-backend/keycloak/KEYCLOAK_SETUP.md`

### `m8flow-frontend/`

The frontend extension is a standalone React/Vite application that extends and overrides `spiffworkflow-frontend` without requiring changes to upstream frontend files.

It is responsible for:

- tenant-aware user experience and login flow
- m8flow-specific UI, branding, and routes
- selective component and service overrides
- frontend build tooling for resolving upstream modules plus local overrides

Important files and directories:

```text
extensions/m8flow-frontend/
|-- src/                              Extension components, views, hooks, and services
|-- package.json                      Frontend package definition
|-- vite.config.ts                    Vite config for local dev and builds
|-- vite-plugin-override-resolver.ts  Override resolution for upstream imports
|-- README.md                         Frontend extension usage guide
`-- ARCHITECTURE.md                   Detailed override/resolution design
```

Start with these docs when changing frontend behavior:

- `extensions/m8flow-frontend/README.md`
- `extensions/m8flow-frontend/ARCHITECTURE.md`

### `startup/`

`extensions/startup/` is the shared backend wiring layer that makes the extension package work with the upstream backend application lifecycle.

This area handles things such as:

- mapping m8flow environment variables into upstream-compatible settings
- applying pre-app and post-app patches
- enforcing model identity and boot ordering
- registering Flask request hooks and tenant context hooks
- registering fallback routes
- running migrations when enabled
- loading sample templates
- wrapping the ASGI app with tenant context middleware

The main runtime flow is:

1. `extensions/app.py` calls `create_application()`
2. `extensions/startup/sequence.py` prepares bootstrap state and applies safe pre-app patches
3. the upstream backend app is created
4. app-dependent patches, hooks, migrations, and tenant-aware behavior are registered
5. the resulting ASGI app is returned for uvicorn or Docker startup

This startup layer is the right place for cross-cutting backend boot logic. Domain behavior should usually stay inside `m8flow-backend/src/m8flow_backend/`.

## Working In This Folder

Before working on extensions locally, make sure the upstream source folders have been fetched into the repo root:

- Bash: `./bin/fetch-upstream.sh`
- PowerShell: `.\bin\fetch-upstream.ps1`

Common local workflows:

- Run backend locally with `extensions/m8flow-backend/bin/run_m8flow_backend.sh` or `extensions/m8flow-backend/bin/run_m8flow_backend.ps1`
- Run migrations with `extensions/m8flow-backend/bin/run_m8flow_alembic.sh` or `extensions/m8flow-backend/bin/run_m8flow_alembic.ps1`
- Run the frontend from `extensions/m8flow-frontend`
- Read Keycloak setup notes in `extensions/m8flow-backend/keycloak/KEYCLOAK_SETUP.md`

## Development Guidelines

- Prefer adding behavior under `extensions/` rather than editing fetched upstream directories.
- Keep backend domain logic in `m8flow-backend/src/m8flow_backend/`; reserve `startup/` for boot and integration concerns.
- Keep frontend overrides minimal and intentional; reuse upstream modules where possible and override only what needs to change.
- When changing auth, tenant resolution, or request lifecycle behavior, trace the impact through `extensions/startup/sequence.py`.
- When changing Keycloak behavior, check both the backend code and `extensions/m8flow-backend/keycloak/`.

## Related Docs

- `README.md` at the repository root for full project setup
- `docs/env-reference.md` for canonical environment variables
- `extensions/m8flow-backend/keycloak/KEYCLOAK_SETUP.md` for local Keycloak flows
- `extensions/m8flow-frontend/README.md` for frontend extension usage
- `extensions/m8flow-frontend/ARCHITECTURE.md` for override and bundling details
