# CI Validations

This document describes the CI checks enforced for `m8flow`, what each job validates, and what should be tested locally before pushing code.

## CI Flow

The main workflow is [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). It runs on every `push`, every pull request targeting `main`, and manual dispatch.

### Path Filters

The `Path Filters` job decides which repo-owned areas changed so later jobs can skip safely on pull requests:

- `backend`: `m8flow-backend/**`
- `frontend`: `m8flow-frontend/**`
- `migrations`: `m8flow-backend/migrations/versions/*.py` and `spiffworkflow-backend/migrations/versions/*.py`
- `docker_m8flow`: `docker/**` and `m8flow-connector-proxy/**`

On `push`, the main backend, frontend, and migration jobs run regardless of path filters. On pull requests, path filters are used to avoid unnecessary work.

## Required CI Jobs

`Required CI` is the merge-gate job. It summarizes the results of the required checks and fails if any required upstream job fails.

### Always required on push

- `Backend Lint`
- `Backend Unit Tests`
- `Frontend Lint`
- `Frontend Build and Unit`
- `Migration Compatibility Check`

### Required on pull requests

- `Backend Lint` when backend files change
- `Backend Unit Tests` when backend files change
- `Frontend Lint` when frontend files change
- `Frontend Build and Unit` when frontend files change
- `Migration Compatibility Check`
- `CodeQL Scan`
- `Trivy Security Scan`
- `Docker Build Dry Run` when backend, frontend, Docker, or connector-proxy files change

## What Each Job Checks

### Backend Lint

Runs Ruff against repo-owned backend code using [`m8flow-backend/ruff.toml`](../m8flow-backend/ruff.toml).

Current scope is intentionally narrow:

- `F`: unused imports, undefined names, and similar correctness issues
- `E402`: import/module-order issues in files where top-level execution matters

### Backend Unit Tests

Runs the repo-owned backend test suite from `m8flow-backend/tests`. The job fetches upstream folders first because the extension layer depends on them at runtime.

### Frontend Lint

Runs ESLint against the repo-owned frontend using [`m8flow-frontend/eslint.config.js`](../m8flow-frontend/eslint.config.js).

### Frontend Build and Unit

Builds the repo-owned frontend bundle and runs the frontend unit tests. This is the main frontend regression gate in CI.

### Migration Compatibility Check

Runs the reusable workflow in [`.github/workflows/check-migrations.yml`](../.github/workflows/check-migrations.yml).

This is intentionally a minimal check:

- if no migration files changed, it exits cleanly
- if migration files changed, it:
  - scans for destructive patterns and warns
  - compiles migration files as Python to catch invalid revisions

It does not require a migration plan in the PR description.

### CodeQL Scan

Runs on pull requests only for:

- Python
- JavaScript

### Trivy Security Scan

Runs on pull requests only and performs a filesystem scan for critical vulnerabilities.

### Docker Build Dry Run

Runs on pull requests when backend, frontend, Docker, or connector-proxy files changed. It validates that the main images still build without pushing them.

## Local Checks Before Pushing

Run the checks that match the area you changed.

### Backend changes

Fetch upstream once if needed:

```powershell
cd C:\dev\repos\m8flow
.\bin\fetch-upstream.ps1
```

Run backend lint:

```powershell
cd C:\dev\repos\m8flow\m8flow-backend
python -m ruff check . --config ruff.toml
```

Run backend unit tests in the upstream backend environment:

```powershell
cd C:\dev\repos\m8flow\spiffworkflow-backend
uv sync --group dev
$env:PYTHONPATH = "$(Get-Location);$(Get-Location)\src;C:\dev\repos\m8flow\m8flow-backend\src"
uv run pytest ../m8flow-backend/tests
```

### Frontend changes

```powershell
cd C:\dev\repos\m8flow\m8flow-frontend
npm ci
npm run lint
npm run build
npm test
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

## Current Non-Required Checks

Browser E2E tests under `extensions/m8flow-frontend/test/browser` are not part of the required default CI flow right now. They can still be run manually when a change affects login flows, tenant selection, or other browser-only behavior.

## Rules For Keeping CI Green

- Do not modify upstream/vendor folders directly:
  - `spiffworkflow-backend/`
  - `spiffworkflow-frontend/`
  - `spiff-arena-common/`
- Keep fixes repo-owned and patch-based.
- Do not commit browser test result artifacts.
- Keep backend lint-clean: unused imports, stale test seams, and import-order issues now fail CI.
- Keep frontend tests aligned with current UI behavior. If the UI contract changes, update the tests in the same PR.
- If a change affects workflows, read the workflow diff carefully and sanity-check the local commands that the workflow now expects to pass.
