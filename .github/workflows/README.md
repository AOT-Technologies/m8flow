# Workflow Configuration Guide

## Overview

These workflows handle CI, Docker builds, AWS deployments, release tagging, and PR notifications for m8flow.

## Workflows

### `ci.yml`

**Purpose:** Runs linting, type checks, and tests on pull requests and pushes to `main`.

**Triggers:** Push or PR to `main`, manual dispatch (`workflow_dispatch`).

**Manual dispatch:** From the Actions tab → CI → Run workflow. Input
`run_upstream_copy_gates` (default **true**) runs both duplicate-code license
gates (`upstream-copy-check` + `upstream-cpd-check`) without needing a PR. The
raw-line gate uses `--all` (full tree) on manual runs; PR runs still use `--diff`.

**Jobs (path-filtered):**
- **extensions-backend** — Ruff lint, MyPy type check, Pytest for `m8flow-backend/`
- **extensions-frontend** — Lint, typecheck, and tests for `m8flow-frontend/`
- **upstream-copy-check** — Fails PRs that copy gitignored LGPL upstream (spiff-arena) source into the Apache-2.0 m8flow trees (raw-line similarity; see below)
- **upstream-cpd-check** — Token-level (PMD CPD) copy detection that also catches reformatted/renamed copies (see below)
- **codeql** — CodeQL security scan (Python + JS) on PRs
- **trivy** — Filesystem vulnerability scan (CRITICAL/HIGH) on PRs
- **migration-check** — Calls `check-migrations.yml` when migration files change on PRs
- **docker-dry-run** — Builds all Docker images without pushing on PRs

---

### `upstream-copy-check` (job in `ci.yml`)

**Purpose:** License-boundary guard. Fails a PR when a changed file in the
Apache-2.0 m8flow trees (`m8flow-backend/`, `m8flow-frontend/`, …) is a copy of
its gitignored LGPL-2.1 upstream (spiff-arena) counterpart.

**Runs on:** PRs touching `m8flow-backend/**`, `m8flow-frontend/**`, or the gate
scripts/baselines; also on **manual CI dispatch** when `run_upstream_copy_gates`
is true. It fetches the upstream trees via `bin/fetch-upstream.sh`, then a
gate-specific `bin/fetch-upstream-extra.sh connector-proxy-demo connector-proxies`
(extra trees the default pull omits, so `m8flow-connector-proxy/` can be compared;
does not change the default pull). PRs run
`bin/check-upstream-copying.py --diff origin/<base>` over changed files; manual
runs use `--all`.

**What fails it (layered detection):**
1. Whole-file line similarity ≥ 50% vs the upstream counterpart
2. A run of ≥ 40 contiguous identical lines (catches partial copies under 50%)
3. Verbatim distinctive comments matching upstream
4. LGPL/GPL license header text or upstream attribution (author handles,
   `sartography/` URLs) — **never grandfathered**

**Baseline:** `bin/upstream-copy-baseline.json` grandfathers the copying that
already exists, so the gate only blocks *new* copying and *regressions*. Files
drop out as they are remediated. Regenerate after an intentional, reviewed change
with `bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json`.

**Findings output:** the job always writes a markdown table of findings to the
GitHub **job summary**, and on failure **upserts a PR comment** with the same table
(same-repo PRs only — fork PRs get a read-only token, so they rely on the job
summary). See `--summary-md` in `bin/check-upstream-copying.py`.

---

### `upstream-cpd-check` (job in `ci.yml`)

**Purpose:** Token-level companion to `upstream-copy-check`. Uses **PMD CPD** to
find cross-tree token clones (owned m8flow file ↔ upstream file). Because it
tokenizes source, it catches copies that were reformatted, reindented, or had
identifiers renamed — evasion that the raw-line gate misses.

**Runs on:** Same path filters / manual dispatch as `upstream-copy-check`.
Installs Java 17 + PMD (pinned `PMD_VERSION`), fetches upstream via
`bin/fetch-upstream.sh`, then runs `bin/check-upstream-cpd.py` over the whole tree.

**Details:**
- Python is scanned directly; frontend `.tsx`/`.jsx` are staged into a `.ts`-named
  temp tree first (CPD's `typescript` language only reads `.ts`, though its lexer
  handles JSX once the extension is `.ts`).
- Runs with `--ignore-identifiers --ignore-literals` (rename/literal resistant),
  minimum 75 tokens.
- **Baseline:** `bin/upstream-cpd-baseline.json` grandfathers existing cross-tree
  clones; the gate blocks only new clones and regressions (larger duplicated
  blocks). Regenerate with `bin/check-upstream-cpd.py --write-baseline bin/upstream-cpd-baseline.json`.
- **Fail-closed:** missing upstream trees, CPD parse/launch errors, or recovering
  fewer than half of on-disk baseline pairs fail the job (no silent empty PASS).
- **Findings output:** like `upstream-copy-check`, it always writes a markdown clone
  table to the job summary and upserts a PR comment on failure (same-repo PRs only).

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


