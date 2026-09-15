# CI Validations

This document describes the CI checks enforced for `m8flow`, what each job validates, and what should be tested locally before pushing code.

## CI Flow

The main workflow is [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). It runs on every `push`, every pull request targeting `main`, and manual dispatch.

### Path Filters

The `Path Filters` job decides which repo-owned areas changed so later jobs can skip safely on pull requests:

- `backend`: `m8flow-backend/**`
- `frontend`: `m8flow-frontend/**`
- `migrations`: `m8flow-backend/migrations/versions/*.py`
- `mcp`: `m8flow-mcp/**`
- `docker_m8flow`: `docker/**` and `m8flow-connector-proxy/**`

On `push`, the main backend, frontend, mcp, and migration jobs run regardless of path filters. On pull requests, path filters are used to avoid unnecessary work.

## Required CI Jobs

`Required CI` is the merge-gate job. It summarizes the results of the required checks and fails if any required upstream job fails.

### Always required on push

- `Backend Lint`
- `Backend Unit Tests`
- `Frontend Lint`
- `Frontend Build and Unit`
- `MCP Lint`
- `MCP Unit Tests`
- `Migration Compatibility Check`

### Required on pull requests

- `Backend Lint` when backend files change
- `Backend Unit Tests` when backend files change
- `Frontend Lint` when frontend files change
- `Frontend Build and Unit` when frontend files change
- `MCP Lint` / `MCP Unit Tests` when mcp files change
- `Migration Compatibility Check`
- `CodeQL Scan`
- `Trivy Security Scan`
- `Docker Build Dry Run` when backend, frontend, Docker, or connector-proxy files change

Upstream SpiffArena copy/CPD license gates were removed with the wheel-based
`m8flow-bpmn-core` cutover. See [upstream-recovery.md](upstream-recovery.md).

## What Each Job Checks

### Backend Lint

Runs Ruff against repo-owned backend code using [`m8flow-backend/ruff.toml`](../m8flow-backend/ruff.toml).

### Backend Unit Tests

Runs the repo-owned backend test suite from `m8flow-backend/` via `uv sync --group dev` and `uv run pytest`, using the pinned `m8flow-bpmn-core` wheel under `m8flow-backend/vendor/`.

### Frontend Lint

Runs ESLint against the repo-owned frontend using [`m8flow-frontend/eslint.config.js`](../m8flow-frontend/eslint.config.js).

### Frontend Build and Unit

Builds the repo-owned frontend bundle and runs the frontend unit tests. This is the main frontend regression gate in CI.

### MCP Lint

Runs Ruff check and format against `m8flow-mcp/`.

### MCP Unit Tests

Installs MCP deps with `uv sync --extra dev` (required so `[tool.uv.sources]` resolves the local sibling `m8flow-telemetry`) and runs `uv run pytest` under `m8flow-mcp/`. Plain `pip install` cannot resolve that path override.

### Migration Compatibility Check

Runs the reusable workflow in [`.github/workflows/check-migrations.yml`](../.github/workflows/check-migrations.yml).

This is intentionally a minimal check:

- if no migration files changed, it exits cleanly
- if migration files changed, it:
  - scans for destructive patterns and warns
  - compiles migration files as Python to catch invalid revisions

### CodeQL Scan

Runs on pull requests only for:

- Python
- JavaScript

### Trivy Security Scan

Runs on pull requests only and performs a filesystem scan for critical vulnerabilities.

### Docker Build Dry Run

Runs on pull requests when backend, frontend, Docker, or connector-proxy files changed. It validates that the main images still build without pushing them. It does **not** yet build `m8flow-node-wire-proxy` (see [known-gaps.md](known-gaps.md)).

## Local Checks Before Pushing

Run the checks that match the area you changed.

### Backend changes

```powershell
cd C:\dev\repos\m8flow\m8flow-backend
uv sync --group dev
python -m ruff check . --config ruff.toml
uv run pytest
```

### Frontend changes

```powershell
cd C:\dev\repos\m8flow\m8flow-frontend
npm ci
npm run lint
npm run build
npm test
```

### MCP changes

```powershell
cd C:\dev\repos\m8flow\m8flow-mcp
uv sync --extra dev
uv run pytest tests/ --cov=src --cov-report=term-missing
```

### Migration changes

At minimum, make sure the file is valid Python and reversible where practical. CI will compile migration files and warn on destructive operations.

### Docker or connector-proxy changes

If you touched:

- `docker/**`
- `m8flow-connector-proxy/**`
- backend code that affects image build
- frontend code that affects image build

then validate the relevant image builds locally if practical.

## Rules For Keeping CI Green

- Do not reintroduce SpiffArena vendor trees (`spiffworkflow-backend/`, `spiffworkflow-frontend/`, `spiff-arena-common/`).
- Keep backend lint-clean: unused imports, stale test seams, and import-order issues now fail CI.
- Keep frontend tests aligned with current UI behavior. If the UI contract changes, update the tests in the same PR.
- If a change affects workflows, read the workflow diff carefully and sanity-check the local commands that the workflow now expects to pass.
