# m8flow Browser Tests

Playwright E2E tests for the m8flow extension frontend.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- The m8flow frontend running at `http://localhost:6841` (or set `E2E_URL`)

## Setup

```bash
cd extensions/m8flow-frontend/test/browser
uv sync
uv run playwright install chromium
```

For **QA reports** (interactive HTML dashboard and/or stakeholder PDF), install the optional PDF stack:

```bash
uv sync --extra pdf
```

The HTML dashboard uses only Python stdlib; the **executive PDF** needs `fpdf2` and `matplotlib` from that extra.

## Running Tests

> Always invoke pytest as `uv run python -m pytest` (not `uv run pytest`).
> On systems with a system-wide Python install, `uv run pytest` can resolve
> to a `pytest` binary outside this project's `.venv`, which won't see the
> dependencies declared in `pyproject.toml` (e.g. `faker`) and will fail
> collection with `ModuleNotFoundError`. Running pytest as a module forces
> the venv's interpreter and avoids this.

```bash
# All tests
uv run python -m pytest -v

# Specific test file
uv run python -m pytest auth/test_login.py -v

# Run headed (visible browser)
uv run python -m pytest --headed

# Filter by keyword
uv run python -m pytest -k "template" -v

# Optional: headed browser + QA reports (combine flags as usual for pytest-playwright/pytest).
# `--qa-report` writes HTML under test-results/qa-report/ and an executive PDF (needs `uv sync --extra pdf` for PDF).
uv run python -m pytest PATH_OR_SELECTION -v --headed --qa-report

# Exclude the slow live-backend template E2E when the full stack is not up
uv run python -m pytest -k "not form_driven" -v

# Against a different URL
E2E_URL=http://localhost:6841 uv run python -m pytest -v
```

### QA HTML & PDF reports

Reporting runs at the **end** of the session (not with `--collect-only`). From `extensions/m8flow-frontend/test/browser`:

```bash
# HTML + PDF (PDF needs: uv sync --extra pdf)
uv run python -m pytest -v --qa-report

# HTML only
uv run python -m pytest -v --html-report

# One file example
uv run python -m pytest auth/test_login.py -v --qa-report

# Custom PDF path
uv run python -m pytest -v --pdf-report --pdf-report-file=test-results/my-summary.pdf
```

After the run the console shows **`QA HTML report:`** plus the absolute path (and prints it again so it stays visible above pytest’s summary). Wait until pytest finishes—the report is written in **`pytest_sessionfinish`**; **Ctrl+C** skips it.

Outputs are anchored to **pytest’s rootdir** (`extensions/m8flow-frontend/test/browser`, where `pytest.ini` lives), not always your terminal’s cwd:

- **HTML:** `test-results/qa-report/index.html` — open in a normal browser. Summary charts, searchable list, expandable details (logs, traces, steps where recorded). The screenshot grid only includes **failed/error** tests with images under `test-results/`.
- **PDF:** `test-results/m8flow-exec-summary-<timestamp>.pdf` (or the path you passed) — short run summary and failure notes, not a copy of the HTML.

| Flag | What it writes |
|------|----------------|
| `--qa-report` | HTML + executive PDF (PDF only if `fpdf2` / `matplotlib` are installed via `--extra pdf`) |
| `--html-report` | HTML only |
| `--pdf-report` | PDF only |
| `--pdf-report-file=...` | PDF destination instead of the timestamped default |

For a different long PDF you build yourself, `helpers/pdf_report.py` is separate; `--pdf-report` here is the executive PDF only.

Failure screenshots/traces are produced by the test run itself (configured in `conftest.py` and `pytest.ini`).
Per-test logs follow `log_cli_*` and `log_file_*` settings in `pytest.ini` when report flags are enabled.

### Troubleshooting: `ModuleNotFoundError: No module named 'faker'`

Cause: a `pytest` executable outside this project's `.venv` is being used.

Recommended fix (always works for this repo):

```bash
uv run python -m pytest ...
```

To confirm which `pytest` is on PATH:

```bash
# Windows (PowerShell)
where.exe pytest

# macOS / Linux
which pytest
```

If the first result is not under `test/browser/.venv/...`, either:

- keep using `uv run python -m pytest ...` (preferred), or
- activate the venv first:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_URL` | `http://localhost:6841` | Base URL of the frontend |
| `BROWSER_TEST_API_PREFIX` | `/v1.0` | API path prefix on that origin (Vite proxy to the backend); used by E2E helpers that `fetch` JSON from the browser |
| `BROWSER_TEST_USERNAME` | `admin` | Login username |
| `BROWSER_TEST_PASSWORD` | `admin` | Login password |
| `BROWSER_TEST_SAMPLE_TEMPLATE_SUBSTRING` | `Form Driven` | Substring to find the IT Support / form-driven sample card (matches ``_derive_display_name`` from the ZIP filename, not the hyphenated README title) |
| `BROWSER_TEST_TENANT` | `m8flow` | Tenant slug for `username@tenant` placeholders in sample BPMN scripts |
