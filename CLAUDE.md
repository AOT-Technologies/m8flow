# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`m8flow` is a multi-tenant, Python-based BPMN/DMN workflow platform built **on top of** SpiffArena (SpiffWorkflow). It is not a fork: upstream code is kept untouched and m8flow customizes it through an **extension + patch layer**. The product aligns with formsflow.ai, caseflow, and the SLED360 suite.

## The upstream boundary (read this first)

The upstream SpiffArena code lives in three directories that are **gitignored and absent after a fresh clone**:

- `spiffworkflow-backend/` — upstream LGPL-2.1 workflow engine (Flask/Connexion)
- `spiffworkflow-frontend/` — upstream LGPL-2.1 React/BPMN modeler UI
- `spiff-arena-common/` — upstream shared utilities

They are fetched on demand from [AOT-Technologies/m8flow-core](https://github.com/AOT-Technologies/m8flow-core) and kept out of git history to preserve m8flow's Apache-2.0 license boundary. **Run this once after cloning or nothing will start:**

```bash
./bin/fetch-upstream.sh      # Linux/macOS/WSL
.\bin\fetch-upstream.ps1     # Windows PowerShell
```

The pinned tag/ref lives in `upstream.sources.json`. `bin/diff-from-upstream.sh` reports local divergence.

**Hard rules (also in [AGENTS.md](AGENTS.md)):**
- Never modify, reformat, rename, or move files under `spiffworkflow-backend/`, `spiffworkflow-frontend/`, or `spiff-arena-common/`, and never include them in a commit — even when they show up in the working tree.
- If upstream behavior needs to change, implement it as a patch/override/wrapper in m8flow-owned code instead, or explain the required upstream change rather than editing it.
- Owned (safe-to-edit) areas: `m8flow-backend/`, `m8flow-frontend/`, `m8flow-connector-proxy/`, `m8flow-nats-consumer/`, `keycloak-extensions/`, `docker/`, `docs/`, `bin/`, and repo-owned tests/config. When unsure whether a file is owned, stop and ask.

## Architecture: how customization works without touching upstream

### Backend — runtime monkeypatch registry

The backend boots through `m8flow-backend/src/m8flow_backend/startup/sequence.py:create_application()` (uvicorn target `m8flow_backend.app:app`). It applies upstream behavior changes as **patches registered in `startup/patch_registry.py`**, gated by a boot-phase guard:

1. **PRE_APP** patches (`PRE_APP_PATCH_SPECS`) run before `spiffworkflow_backend.create_app()` and must NOT import models — config overrides, model overrides, OpenAPI merge, auth defaults.
2. App is created (`spiffworkflow_backend.create_app()` — imported lazily, only after overrides are in place).
3. **POST_APP** patches (`POST_APP_CORE_PATCH_SPECS`, `POST_APP_EXTENSION_PATCH_SPECS`) run after the Flask app exists and may import models — tenant scoping, auth/token handling, controllers, services.
4. ASGI app is wrapped with `AsgiTenantContextMiddleware` (skipped in `unit_testing`/`testing` envs).

Each patch is a `*_patch.py` module exposing an `apply(...)` function. Patches are idempotent (tracked in `_APPLIED_PATCH_TARGETS` / per-app set). When changing upstream behavior, **add or edit a patch module and register a `PatchSpec`** — do not edit upstream directly. `startup/` holds cross-cutting boot logic; domain behavior belongs in `services/`, `routes/`, `models/`.

### Frontend — Vite deep override resolver

`m8flow-frontend` is a standalone React app (Vite + Preact + MUI/Carbon) that overrides upstream components **by path** without touching `spiffworkflow-frontend`. The custom plugin `vite-plugin-override-resolver.ts` (configured first in `vite.config.ts`, `enforce: 'pre'`) intercepts ALL imports — including imports *between* core files — and, for any import, prefers a same-path file under `m8flow-frontend/src/` before falling back to upstream via the `@spiffworkflow-frontend` alias.

- To override a component, create the matching path under `m8flow-frontend/src/` (e.g. override `.../src/components/SpiffLogo.tsx` → `m8flow-frontend/src/components/SpiffLogo.tsx`). It is then used everywhere automatically; **you do not need to override parent components**.
- Access upstream code via the `@spiffworkflow-frontend` alias (e.g. `import CoreX from '@spiffworkflow-frontend/components/X'`) to wrap rather than replace.
- All deps install into `m8flow-frontend/node_modules`; the resolver routes upstream files' bare imports there too.
- Adding routes/nav and full details: [m8flow-frontend/ARCHITECTURE.md](m8flow-frontend/ARCHITECTURE.md).

### Multi-tenancy & RBAC (handle with care)

Tenancy is the backbone of the system — see `m8flow-backend/src/m8flow_backend/tenancy.py`, the `tenant_*` services/routes, and `startup/tenant_resolution.py`.

- Tenant id flows via the JWT claim `m8flow_tenant_id` (configurable through `M8FLOW_TENANT_CLAIM`). The Keycloak image is built with the **m8flow realm-info-mapper** provider (`keycloak-extensions/`) so tokens carry `m8flow_tenant_id`/`m8flow_tenant_name`.
- Active-tenant resolution in shared-realm login relies on the **`m8flow_selected_tenant` cookie** — the backend is authoritative, NOT frontend `localStorage`. Do not gate UI on stale browser tenant values.
- Never weaken/bypass RBAC checks or tenant isolation. Do not treat a token as authoritative for shared-realm RBAC refresh merely because it lists org memberships — for multi-org users the active org's local groups must be present or the token must be enriched from Keycloak first.
- When touching login/token/membership/permission code, verify with a **non-admin** shared-realm user (e.g. `editor`/`reviewer`), not just `admin`/`super-admin`. Minimum regression check: `GET /v1.0/onboarding` and `GET /v1.0/tasks`, including the multi-organization case.

### Keycloak login UX (do not regress)

Both the `m8flow` and `master` realms must keep **single-page** username+password login (`Username Password Form` active). Do not introduce a two-step username-then-password / identity-first flow or rely on the upstream `login-username` page. Verify both realm login pages render combined fields after any Keycloak theme/flow/realm change.

## Commands

### Run locally (active dev — backend & frontend on host, infra in Docker)

```bash
# 1. Fetch upstream (once)
./bin/fetch-upstream.sh                      # or .\bin\fetch-upstream.ps1

# 2. Start infra only (DB, Keycloak, MinIO, Redis, connector-proxy) + one-time init jobs
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build \
  m8flow-db keycloak-db keycloak keycloak-proxy redis minio \
  minio-mc-init keycloak-master-admin-init m8flow-connector-proxy

# 3. Backend (uvicorn; syncs deps via uv automatically)
./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload    # bash
.\m8flow-backend\bin\run_m8flow_backend.ps1 6840            # PowerShell
curl http://localhost:6840/v1.0/status                      # -> {"ok": true, ...}

# 4. Frontend (http://localhost:6841, proxies /v1.0 + /api to :6840)
cd m8flow-frontend && npm install && npm start

# 5. Celery worker (bash; on Windows run the celery container instead)
./m8flow-backend/bin/run_m8flow_celery_worker.sh
```

Backend launcher env toggles: `M8FLOW_BACKEND_SYNC_DEPS=false` (skip uv sync), `M8FLOW_BACKEND_USE_UV=false` (use current Python), `M8FLOW_BACKEND_UPGRADE_DB=false` (skip migrations). Set `MULTI_TENANT_ON=false` for a single-tenant UI. Full local-dev guide and troubleshooting: [docs/README.md](docs/README.md).

### Run everything in Docker

```bash
# First start (runs one-time init jobs)
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build
# Subsequent starts (no init profile)
docker compose -f docker/m8flow-docker-compose.yml up -d --build
docker compose -f docker/m8flow-docker-compose.yml down [-v]   # -v also deletes data volumes
```

Default host ports 6840–6852 (backend 6840, frontend 6841, keycloak-proxy 6842, db 6843, connector-proxy 6844). Configure in `.env` (copy from `sample.env`). Env var reference: [docs/env-reference.md](docs/env-reference.md).

### Tests & lint (these are the CI merge gates)

```bash
# Backend lint — Ruff, scope is intentionally narrow (F + E402 only)
cd m8flow-backend && ruff check . --config ruff.toml

# Backend tests — MUST run from spiffworkflow-backend with PYTHONPATH set (it depends on upstream at runtime)
cd spiffworkflow-backend
uv sync --group dev
export PYTHONPATH=$PYTHONPATH:$(pwd):$(pwd)/src:$(pwd)/../m8flow-backend/src
uv run pytest ../m8flow-backend/tests                          # all backend tests
uv run pytest ../m8flow-backend/tests/unit/... -k <name>       # a single test/file

# Frontend (run inside m8flow-frontend/)
npm run lint        # ESLint
npm run test:ci     # vitest (CI runner)
npm run build       # vite build — run when UI/routing/bundling changed
npm run typecheck   # tsc --noEmit
```

Prefer focused tests first, then widen. E2E/browser tests are NOT part of default verification — only run when explicitly requested. CI details: [docs/ci-validations.md](docs/ci-validations.md).

### Migrations

m8flow owns Alembic migrations under `m8flow-backend/migrations/` (separate from upstream's). Run via `m8flow-backend/bin/run_m8flow_alembic.{sh,ps1}`; they run automatically at backend startup unless `M8FLOW_BACKEND_UPGRADE_DB=false`. Keep migrations reversible where practical; PostgreSQL is the primary supported DB. Don't make destructive schema changes without explaining the risk.

## Supporting services

- `m8flow-connector-proxy/` — dispatches connector service-task commands (SMTP, Slack, HTTP). Backend logs connection-refused on :6844 if it isn't running.
- `m8flow-nats-consumer/` — NATS event consumer for event-driven workflow execution.
- `sample_templates/` (`m8flow-backend/sample_templates/`) — seed workflow templates loaded at startup; stored in MinIO buckets `m8flow-process-models` / `m8flow-templates`.
