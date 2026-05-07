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

## Database and Migrations

- Do not make destructive schema changes without clearly explaining the risk.
- Alembic migrations must be reversible where practical.
- Preserve existing data unless the task explicitly requires a data migration.
- Consider PostgreSQL as the primary supported database unless stated otherwise.

## Testing and Verification

When changing backend code, consider running or updating relevant tests.

When changing frontend code, consider lint/build impact.

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
