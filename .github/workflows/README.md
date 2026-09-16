# Workflow Configuration Guide

## Overview

These workflows handle CI, Docker builds, AWS deployments, release tagging, and PR notifications for m8flow.

## Workflows

### `ci.yml`

**Purpose:** Runs linting, type checks, and tests for integration branches.

**Triggers:**
- **Push:** any branch (no branch filter)
- **PR:** base `main` or `refactor/next-gen`
- **Manual:** `workflow_dispatch`

**Path filtering:** On PRs, backend / legacy frontend / designer / MCP / migration / docker jobs run only when their path filters match. On push, those module jobs still run unconditionally (existing `main` behavior). CodeQL, Trivy, and docker dry-run remain PR-only.

**Jobs (path-filtered on PR):**
- **backend-lint** — Ruff lint for `m8flow-backend/`
- **backend** — Pytest for `m8flow-backend/` (uv sync against the pinned `m8flow-bpmn-core` wheel)
- **frontend-lint** — Lint for `m8flow-frontend/` (legacy UI)
- **frontend-build-unit** — Build and unit tests for `m8flow-frontend/` (legacy UI)
- **designer-lint** — ESLint for `m8flow-designer/` (primary UI)
- **designer-build-unit** — Build (`tsc --noEmit` + `vite build`) and Vitest run for `m8flow-designer/`
- **mcp-lint** / **mcp** — Lint and unit tests for `m8flow-mcp/` (`uv sync --extra dev` for sibling `m8flow-telemetry`)
- **codeql** — CodeQL security scan (Python + JS) on PRs
- **trivy** — Filesystem vulnerability scan (CRITICAL/HIGH) on PRs
- **migration-check** — Calls `check-migrations.yml` when migration files change
- **docker-dry-run** — Builds backend/frontend/keycloak/legacy connector-proxy images without pushing on PRs (no `m8flow-designer` image/Dockerfile yet — see `docs/known-gaps.md`)

`m8flow-frontend` (legacy) and `m8flow-designer` (primary) both get their own
lint/build/test jobs here because both trees are developed in parallel across
`main` and `refactor/next-gen`; don't remove either job while that's true.

Upstream SpiffArena copy/CPD license gates were removed with the wheel-based
`m8flow-bpmn-core` cutover. Do not reintroduce `bin/fetch-upstream.sh` or the
copy/CPD scripts. See [docs/upstream-recovery.md](../../docs/upstream-recovery.md).

---

### `check-migrations.yml`

**Purpose:** Reusable workflow (called by `ci.yml`) that validates migration files in PRs.

**Triggers:** `workflow_call` only.

**What it checks:**
1. No destructive operations (`DROP TABLE`, `DROP COLUMN`, etc.) without review
2. All Alembic revision files in `m8flow-backend/migrations/versions/` are valid Python

---

### `create-release-tag.yml`

**Purpose:** Creates an annotated RC release tag on a commit from `main`.

**Triggers:** Manual (`workflow_dispatch`).

**Inputs:**
- `commit_sha` — SHA to tag (defaults to latest on `main`)
- `tag_name` — Tag in `X.Y.Z-rc` format (auto-increments patch if omitted)

**Required permissions:** `contents: write` on the repo (enforced at runtime via collaborator check).

---

### `deploy-docker.yml`

**Purpose:** Builds and pushes Docker images to Docker Hub.

**Triggers:**
- Manual (`workflow_dispatch`) with an `rc_tag` input
- Automatically after `create-release-tag.yml` completes successfully on `main` (when `AUTO_BUILD` variable is `true`)

**Images built:** `m8flow-backend`, `m8flow-frontend`, `m8flow-keycloak`, `m8flow-connector-proxy`

---

### `deploy-aws.yml`

**Purpose:** Deploys the four app services to ECS (DEV or QA).

**Triggers:** Manual (`workflow_dispatch`).

**Inputs:**
- `environment` — `DEV` or `QA`
- `image_tag` — Docker image tag to deploy (e.g. `1.2.3-rc`)


---

### `pr-notification.yml`

**Purpose:** Sends a Google Chat notification when a non-draft PR targeting `main` is opened.

**Triggers:** `pull_request_target` opened on `main`.
