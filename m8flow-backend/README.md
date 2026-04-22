# m8flow-backend

Apache-2.0 **m8flow-specific backend layer** that runs on top of the upstream `m8flow-core` backend (`spiffworkflow-backend`) fetched into the repo at development/build time.

## License boundary (important)

This repository keeps the Apache-2.0 m8flow layer separate from upstream LGPL-2.1 code by **not committing** upstream folders. Fetch them when needed:

- Bash: `./bin/fetch-upstream.sh`
- PowerShell: `.\bin\fetch-upstream.ps1`

Upstream folders are configured in `upstream.sources.json` and are gitignored.

## What lives here

```text
m8flow-backend/
|-- bin/                      Local run, migration, sync, and setup scripts
|-- keycloak/                 Keycloak bootstrap docs and realm assets
|-- migrations/               Alembic migrations for m8flow-owned tables
|-- sample_templates/         Seed templates for local/dev bootstrap
|-- src/m8flow_backend/       m8flow backend source (ASGI entry + startup wiring)
`-- tests/                    Unit + integration tests for m8flow behavior
```

Inside `src/m8flow_backend/`, the main code is organized into areas such as:

- `routes/` for API endpoints and upstream route patches
- `services/` for application logic (tenant context, auth, templates, etc.)
- `models/` for m8flow persistence models
- `background_processing/` for Celery worker flows
- `startup/` for boot wiring (env mapping, patch registry, hooks, migrations)

## Useful entrypoints

- Backend server:
  - `m8flow-backend/bin/run_m8flow_backend.sh`
  - `m8flow-backend/bin/run_m8flow_backend.ps1`
- Alembic migrations:
  - `m8flow-backend/bin/run_m8flow_alembic.sh`
  - `m8flow-backend/bin/run_m8flow_alembic.ps1`
- Celery worker / flower:
  - `m8flow-backend/bin/run_m8flow_celery_worker.sh`
  - `m8flow-backend/bin/run_m8flow_celery_worker.ps1`
- Keycloak setup:
  - `m8flow-backend/keycloak/KEYCLOAK_SETUP.md`

## Startup wiring overview

The backend runtime entrypoint is:

- `m8flow-backend/src/m8flow_backend/app.py` (uvicorn target: `m8flow_backend.app:app`)

The high-level boot flow is implemented in:

- `m8flow-backend/src/m8flow_backend/startup/sequence.py`

At a high level:

1. Pre-bootstrap: harden logging + map env vars into upstream-compatible settings.
2. Bootstrap: apply safe pre-app overrides/patches that don’t need a Flask app.
3. Create upstream Connexion/Flask app (`spiffworkflow_backend.create_app()`).
4. Post-app bootstrap: register request hooks, fallback routes, migrations, tenant resolution ordering, and app-dependent patches.
5. Wrap the ASGI app (when appropriate) with tenant context middleware.

`startup/` is the right place for cross-cutting boot logic. Domain behavior should generally stay in `services/`, `routes/`, and `models/`.

## Working locally

1. Fetch upstream source folders once after cloning:

```bash
./bin/fetch-upstream.sh
```

```powershell
.\bin\fetch-upstream.ps1
```

2. Start the backend:

```bash
./m8flow-backend/bin/run_m8flow_backend.sh 7000 --reload
```

```powershell
.\m8flow-backend\bin\run_m8flow_backend.ps1 7000 --Reload
```

## Related docs

- Repo root setup guide: `README.md`
- Environment variables: `docs/env-reference.md`
- Keycloak: `m8flow-backend/keycloak/KEYCLOAK_SETUP.md`
- Integration tests: `m8flow-backend/tests/integration/README.md`

