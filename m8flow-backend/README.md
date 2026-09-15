# m8flow-backend

Apache-2.0 HTTP host for M8Flow. It consumes the pinned **`m8flow-bpmn-core`**
wheel under `vendor/` (see [docs/upstream-recovery.md](../docs/upstream-recovery.md)).
Do not import `spiffworkflow` / `spiffworkflow_backend`, and do not fetch SpiffArena
vendor trees into this repo.

## What lives here

```text
m8flow-backend/
|-- bin/                      Local run, migration, sync, and setup scripts
|-- keycloak/                 Keycloak bootstrap docs and realm assets
|-- migrations/               Alembic migrations for m8flow-owned tables
|-- sample_templates/         Seed templates for local/dev bootstrap
|-- vendor/                   Pinned m8flow-bpmn-core wheel
|-- src/m8flow_backend/       Host source (ASGI entry + domain modules)
`-- tests/                    Unit tests for host behavior
```

Prefer the host modules: `workflow`, `catalog`, `human_task`, `scheduler`,
`identity`, `auth`, `authorization`, `secrets`.

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

## Working locally

```bash
cd m8flow-backend
uv sync --group dev
uv run pytest
./bin/run_m8flow_backend.sh 6840 --reload
```

Set `FLASK_SESSION_SECRET_KEY` (and preferably `M8FLOW_SECRETS_ENCRYPTION_KEY`)
outside unit-testing environments — the host refuses to start with hardcoded
fallback secrets in production-like configs.

## Related docs

- Repo root setup guide: `README.md`
- Environment variables: `docs/env-reference.md`
- Known gaps: `docs/known-gaps.md`
- Keycloak: `m8flow-backend/keycloak/KEYCLOAK_SETUP.md`
- Integration tests: `m8flow-backend/tests/integration/README.md`
