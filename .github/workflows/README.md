# Workflow Configuration Guide

## Overview

These workflows handle CI, Docker builds, AWS deployments, release tagging, and PR notifications for m8flow.

## Workflows

### `ci.yml`

**Purpose:** Runs linting, type checks, and tests on pull requests and pushes to `main`.

**Triggers:** Push or PR to `main`, manual dispatch.

**Jobs (path-filtered):**
- **extensions-backend** — Ruff lint, MyPy type check, Pytest for `m8flow-backend/`
- **extensions-frontend** — Lint, typecheck, and tests for `m8flow-frontend/`
- **codeql** — CodeQL security scan (Python + JS) on PRs
- **trivy** — Filesystem vulnerability scan (CRITICAL/HIGH) on PRs
- **migration-check** — Calls `check-migrations.yml` when migration files change on PRs
- **docker-dry-run** — Builds all Docker images without pushing on PRs

---

### `check-migrations.yml`

**Purpose:** Reusable workflow (called by `ci.yml`) that validates migration files in PRs.

**Triggers:** `workflow_call` only.

**What it checks:**
1. PR description contains a `Migration Plan` section with `Backward Compatibility`, `Rollback`, and `Expand/Contract` entries
2. No destructive operations (`DROP TABLE`, `DROP COLUMN`, etc.) without explicit `Destructive Migration Approved` in the PR body
3. All Alembic revision files in `m8flow-backend/migrations/versions/` are valid Python

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

**Purpose:** Builds and pushes all four Docker images to Docker Hub.

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


