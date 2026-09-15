# AGENTS.md

## Project Context

This repository is `m8flow`. The HTTP host lives in `m8flow-backend` and consumes
`m8flow-bpmn-core` as a pinned wheel (`0.1.0` @ `a3d4fd190a384ad06af84f122cad3d8818250c45`).
Do not vendor core source. Do not import `spiffworkflow` from `m8flow-backend`.
Do not reintroduce `spiffworkflow-backend/`, `spiffworkflow-frontend/`, or
`spiff-arena-common/`. Recovery pin: `docs/upstream-recovery.md`.

## Hard Rules

- Do not import `spiffworkflow` or `spiffworkflow_backend` from `m8flow-backend`.
- Routes must not call `execute_command` / `execute_query` / `run_due_scheduler_jobs`.
- Routes must not INSERT into `user` / `group` / `permission_*` / `tenant`.
- Prefer the eight host modules: `workflow`, `catalog`, `human_task`, `scheduler`,
  `identity`, `auth`, `authorization`, `secrets`.

## Repository Ownership

Only modify files that belong to the `m8flow` repository.

Typical safe areas include:

- `m8flow-backend/`
- `m8flow-designer/` — **primary UI** (Vite/React designer app)
- M8Flow configuration
- tests owned by this repo
- documentation owned by this repo

When unsure whether a file is owned by this repo, stop and explain the uncertainty before changing it.

## Deprecated / Legacy Modules

Do not treat these as the default place for new product UX. Prefer `m8flow-designer`
and `m8flow-backend` unless the task explicitly targets a legacy surface.

| Path | Status | Notes |
|------|--------|--------|
| `m8flow-frontend/` | **Deprecated / legacy UI** | Older SpiffArena-style frontend. Not the primary app. Avoid new feature work here unless explicitly requested for that tree. Prefer wiring UX in `m8flow-designer/`. |
| `spiffworkflow-backend/` | **Removed / do not reintroduce** | Upstream vendor tree. See `docs/upstream-recovery.md`. |
| `spiffworkflow-frontend/` | **Removed / do not reintroduce** | Upstream vendor tree. |
| `spiff-arena-common/` | **Removed / do not reintroduce** | Upstream vendor tree. |
| Spiff monkey-patches / `patch_registry` | **Removed / do not reintroduce** | Host must use `m8flow-bpmn-core` APIs and host modules, not Spiff source patches. |

When a ticket mentions “the frontend,” assume **`m8flow-designer`** unless the user
names `m8flow-frontend` explicitly.

## Architecture Guidance

M8Flow is a host on `m8flow-bpmn-core`, not a SpiffArena fork.

- Keep workflow writes behind `m8flow_backend.workflow`.
- Preserve tenant isolation and RBAC (`allow_uri` + dispatcher `authorize`).
- Cookie for active tenant is `m8flow_selected_tenant`.
- Do not reintroduce SpiffArena vendor trees or the retired upstream copy/CPD
  gates (`bin/fetch-upstream.sh`, `bin/check-upstream-*.py`). Recovery pin:
  `docs/upstream-recovery.md`.

## Keycloak Login UX

- Do not change the Keycloak login experience to a two-step username-then-password flow.
- For both the `m8flow` realm and the `master` realm, the login page must collect username and password on the same page.
- If you touch Keycloak themes, browser flows, realm imports, or bootstrap scripts, preserve single-page login by keeping `Username Password Form` active and preventing username-only / identity-first login steps from becoming the user-facing path unless explicitly requested.
- Do not rely on the upstream/base Keycloak `login-username` page for normal sign-in. Repo-owned theme logic must keep the effective sign-in UX on one page.
- After Keycloak login/theme/flow changes, verify both realm login pages still render combined username and password fields before considering the work complete.

## Multi-Tenancy and RBAC

Be careful with tenant and permission-related behavior.

- Preserve tenant isolation.
- Do not bypass tenant scoping.
- Do not remove or weaken RBAC checks.
- Ensure tenant IDs such as `m8f_tenant_id` are handled explicitly where required.
- Be cautious around login, group assignment, permissions, human task assignment, and database queries.
- Do not validate shared-realm auth or RBAC changes only with `admin` or `super-admin`.
- After changes to login, token handling, tenant selection, organization membership sync, or permission patches, verify at least one non-admin shared-realm user such as `editor` or `reviewer`.
- The minimum protected-route regression check for a non-admin shared-realm user is:
  - `GET /v1.0/onboarding`
  - `GET /v1.0/tasks`
- When touching request-time token or membership refresh code, add or update a route-level test for a stale local shared-realm user and a thin token that must be enriched back into the correct tenant-scoped groups.
- Shared-realm regressions must include the multi-organization case, not just the single-organization case. A user such as `editor` joining a second Keycloak organization must still be able to access `GET /v1.0/onboarding` and `GET /v1.0/tasks` after tenant selection/finalization.
- Do not treat a token as authoritative for shared-realm RBAC refresh merely because it lists organization memberships. For multi-organization users, the active organization’s local groups must be present, or the token must be enriched from Keycloak before tenant-scoped group sync runs.
- In shared-realm multitenant flows, do not treat frontend `localStorage` tenant values as authoritative tenant finalization. The backend relies on the `m8flow_selected_tenant` cookie for active-tenant resolution, so UI gates must not bypass tenant selection just because a stale tenant alias remains in browser storage.

## Database and Migrations

- Do not make destructive schema changes without clearly explaining the risk.
- Alembic migrations must be reversible where practical.
- Preserve existing data unless the task explicitly requires a data migration.
- Consider PostgreSQL as the primary supported database unless stated otherwise.

## Testing and Verification

When changing backend code, consider running or updating relevant tests.

When changing frontend code, consider lint/build impact.

After applying code changes, run the relevant repo-owned checks for the area you touched whenever feasible:

- Backend changes:
  - Run the Python lint target for repo-owned backend code (`ruff` in `m8flow-backend`) when backend Python files change.
  - Run the most relevant `pytest` target for the touched backend files.
  - Prefer focused tests first, then widen only if the change is broad or cross-cutting.
- Primary UI (`m8flow-designer`) changes:
  - Run `npm run lint` in `m8flow-designer`.
  - Run `npm test` in `m8flow-designer` (prefer focused tests for touched files).
  - Run `npm run build` in `m8flow-designer` when UI, routing, bundling, or shared frontend infrastructure changed.
- Legacy UI (`m8flow-frontend`) changes (only when that tree is explicitly in scope):
  - Run `npm run lint` / `npm test` / `npm run build` in `m8flow-frontend` as applicable.
- CI or workflow changes:
  - Sanity-check the modified workflow file and, when practical, run the same local commands the workflow is intended to execute.
- Docker, Keycloak, or startup-script changes:
  - Run the relevant shell syntax checks and/or `docker compose ... config` validation when applicable.
- E2E/browser tests:
  - These are not part of the default required verification for now.
  - Only run them when the user explicitly asks, when the task specifically targets browser automation, or when unit/build checks are insufficient for the risk.

Before finalizing work, summarize:

- What changed
- Which files were changed
- What was intentionally not changed
- Any tests or checks run
- Any remaining risks or assumptions

## Dependency Rules

- Do not add new dependencies unless necessary.
- Explain why a new dependency is needed.
- Prefer existing project patterns and libraries.

## Git Hygiene

- Keep changes focused.
- Avoid unrelated formatting changes.
- Do not include generated files unless required.
- Do not reintroduce SpiffArena vendor trees (`spiffworkflow-backend/`, `spiffworkflow-frontend/`, `spiff-arena-common/`).
