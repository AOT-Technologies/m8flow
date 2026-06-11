# AGENTS.md

## Project Context

This repository is `m8flow`, which extends and customizes SpiffArena through patches and extension code.

The project depends on SpiffArena-related folders that may exist locally for development, but they are not owned by this repository:

- `spiff-arena-common/`
- `spiffworkflow-backend/`
- `spiffworkflow-frontend/`

These folders are imported/reference dependencies and must be treated as upstream/vendor code.

## Hard Rules

- Do not modify files under:
  - `spiff-arena-common/`
  - `spiffworkflow-backend/`
  - `spiffworkflow-frontend/`
- Do not create commits that include changes to those folders.
- Do not reformat, rename, move, or “clean up” files in those folders.
- If a change appears necessary in upstream SpiffArena code, explain the required change instead of editing it directly.
- Prefer implementing behavior through M8Flow extension code, patches, wrappers, configuration, or repo-owned modules.

## Repository Ownership

Only modify files that belong to the `m8flow` repository.

Typical safe areas include:

- `extensions/`
- M8Flow-specific backend code
- M8Flow-specific frontend code
- M8Flow-specific patches
- M8Flow configuration
- tests owned by this repo
- documentation owned by this repo

When unsure whether a file is owned by this repo, stop and explain the uncertainty before changing it.

## Architecture Guidance

M8Flow is built on top of SpiffArena, not as a fork where upstream folders should be edited directly.

Changes should preserve the patch-based architecture:

- Keep custom behavior isolated in M8Flow-owned extension layers.
- Avoid coupling new code unnecessarily to upstream internals.
- Do not duplicate large sections of upstream code unless there is a clear reason.
- Prefer small, targeted patches over broad rewrites.
- Preserve compatibility with upstream SpiffArena where practical.

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
- Frontend changes:
  - Run `npm run lint` in `m8flow-frontend`.
  - Run `npm test` in `m8flow-frontend`.
  - Run `npm run build` in `m8flow-frontend` when UI, routing, bundling, or shared frontend infrastructure changed.
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
- Do not modify imported SpiffArena folders even if they appear in the working tree.
