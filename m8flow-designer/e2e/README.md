# M8Flow Next-Gen E2E tests

End-to-end tests for M8Flow Next-Gen, written with Playwright (Chromium). They
run against a **live stack** (M8Flow UI → backend → Keycloak → database), not
mocks. This README covers how to run them, the reports, and the module-wise E2E
gate that runs them on pull requests.

All commands are run from `m8flow-designer/`.

## 1. Approach

- **What an E2E test covers:** a real user journey through the live stack.
  Unit tests (Vitest, pytest) stay the first line of defence; E2E covers what
  only works end to end: login and roles, tenant isolation, and the main workflows.
- **Isolated test data:** tests never rely on, or change, data that already
  exists on an instance. Each spec creates the mock data it needs through the
  API (mock users `e2e-*@example.test`, mock process groups and models, mock
  files in `fixtures/`) and deletes it afterwards. Expected counts are read from
  the API, so tests pass on an empty instance or a busy one.
- **UI and API:** access rules are checked in the UI and with a direct API
  call, so a hidden button cannot be bypassed.
- **Result line:** every test ends with one line, e.g.
  `[LGN-04] Platform Admin access is restricted for Viewer users ...`, printed
  only when all its checks passed.
- **Speed:** one browser session per user is reused across tests
  (`useSession` in `helpers/auth.ts`). Tests about login itself always log in fresh.

## 2. One-time setup

```sh
cd m8flow-designer
npm install
npx playwright install chromium
```

## 3. Before every run

1. Start the backend stack with Docker Compose from the repo root:

   > Backend: `http://localhost:6840`
   > Keycloak: `http://localhost:6842`

2. Check the seed users exist (created by the Keycloak setup scripts):

   > Tenant `m8flow`: `admin`, `editor`, `submitter`, `viewer`, `reviewer`, `integrator` (password = username)
   > Master realm: `super-admin / super-admin`

   No seed process models are needed: the Processes and Modeler specs create
   and delete their own mock groups, models and files.

3. Leave SMTP **unset** in the local backend. The invitation tests read the
   invitation link from the API/dialog, which only happens without SMTP.

4. The UI (`http://localhost:6853`) does not need to be started by hand:
   Playwright runs `npm run dev` itself, or reuses it if it is already running.

## 4. Run the tests

| What to run | Command |
| --- | --- |
| Whole suite | `npm run test:e2e` |
| One spec file | `npm run test:e2e -- e2e/login.spec.ts` |
| One test by ID or name | `npm run test:e2e -- -g "CHK-08"` |
| All modeler specs | `npm run test:e2e -- e2e/modeler` |
| Watch the browser | `npm run test:e2e -- --headed` |
| Watch one spec file in the browser | `npm run test:e2e -- e2e/identity-auth-parity.spec.ts --headed` |
| Watch one test in the browser | `npm run test:e2e -- -g "PAR-03" --headed` |
| Debug step by step | `npm run test:e2e -- --debug` |
| Interactive UI mode | `npm run test:e2e:ui` |

Anything after `--` is passed straight to Playwright. The command exits with
code `1` if any test fails.

**Seeing what happens during a run**

- By default the browser runs hidden (headless). Add `--headed` to watch every click and page.
- Tests run one at a time (`workers: 1`), so the window shows one test after another.
- `--debug` opens the Playwright Inspector: **Step over** runs the next action, **Resume** continues.
- `npm run test:e2e:ui` opens UI mode: pick tests, watch them run, and replay each step.
- Every passed test prints its result line in the terminal.

**Optional settings** (environment variables):

| Variable | Default | Purpose |
| --- | --- | --- |
| `M8FLOW_DESIGNER_BASE_URL` | `http://localhost:6853` | UI URL |
| `M8FLOW_BACKEND_BASE_URL` | `http://localhost:6840` | Backend URL |
| `M8FLOW_E2E_EDITOR_USERNAME` / `_PASSWORD` | `editor` / `editor` | Editor login |
| `M8FLOW_E2E_SUPER_ADMIN_USERNAME` / `_PASSWORD` | `super-admin` / `super-admin` | Platform admin login |
| `M8FLOW_E2E_TENANT_ADMIN_USERNAME` / `_PASSWORD` | `admin` / `admin` | Tenant admin login |
| `M8FLOW_E2E_SUBMITTER_USERNAME` / `_PASSWORD` | `submitter` / `submitter` | Submitter login |
| `M8FLOW_E2E_VIEWER_USERNAME` / `_PASSWORD` | `viewer` / `viewer` | Viewer login |
| `M8FLOW_E2E_REVIEWER_USERNAME` / `_PASSWORD` | `reviewer` / `reviewer` | Reviewer login |
| `M8FLOW_E2E_INTEGRATOR_USERNAME` / `_PASSWORD` | `integrator` / `integrator` | Integrator login (also used by PAR-03) |
| `M8FLOW_E2E_MASTER_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | `admin` / `admin` | Keycloak master admin: LGN-05b and cleanup of mock invited users |
| `M8FLOW_E2E_KEYCLOAK_URL` | `http://localhost:6842` | Keycloak URL used for cleanup |
| `E2E_REPORT_KEEP` | keep all | Keep only the newest N run folders |
| `E2E_RUN_ID` | date and time | Custom name for the run folder |

Setting a variable for one run:

```sh
# macOS / Linux / Git Bash
E2E_REPORT_KEEP=30 npm run test:e2e

# Windows PowerShell
$env:E2E_REPORT_KEEP=30; npm run test:e2e

# Windows Command Prompt
set E2E_REPORT_KEEP=30 && npm run test:e2e
```

## 5. Results and reports

At the end of each run the console prints where the results were saved:

```text
Run report: e2e/reports/2026-10-14_17-40-00/report.html
Dashboard:  .../m8flow-designer/e2e/reports/index.html
```

Both are plain HTML files: double-click to open them in a browser.

- **Run report** (`reports/<run>/report.html`): one run. Summary (total,
  passed, failed, flaky, skipped, pass rate, duration); every test with status,
  ID, spec and duration; for failed tests the error, stack trace, screenshot
  and a text snapshot of the page; results grouped per spec.
- **Dashboard** (`reports/index.html`): all saved runs. Same views with a
  **Run** dropdown, a trend of the last 30 runs, and the run history.

To serve the reports over http instead: `npm run test:e2e:dashboard`, then
open **http://localhost:9323**.

**What is saved for each run** (`reports/<YYYY-MM-DD_HH-mm-ss>/`):

| Path | Contents |
| --- | --- |
| `report.html` | Report of this run |
| `results.json` | Result and error of every test |
| `gate-summary.md` | Gate result (written by `scripts/e2e-gate-report.mjs`) |
| `artifacts/<test>/test-failed-1.png` | Full-page screenshot, **failed tests only** |
| `artifacts/<test>/error-context.md` | Text snapshot of the page at failure, **failed tests only** |

No video or trace is kept, so a run takes a few hundred KB to a few MB.
`reports/` is git-ignored; to share a run, zip its folder.

Rebuild the reports without running tests: `node scripts/e2e-dashboard.mjs`.
Gate result for your latest run: `node e2e/scripts/e2e-gate-report.mjs`.

## 6. Modules and coverage

The module map is [`modules.json`](modules.json). Each module lists the source
paths it owns and the specs that cover it.

| Module | Critical workflows | Priority | Specs | Status |
|---|---|---|---|---|
| `auth` | Login for every role (LGN), Platform Admin access restricted to super-admin, tenant selection, invitations, logout (PAR) | P0 | `login.spec.ts`, `identity-auth-parity.spec.ts` | Covered |
| `processes` | Process catalog, search, All groups filter, model detail, super-admin all-tenants view (CHK) | P1 | `processes.spec.ts` | Covered |
| `modeler` | Open/edit/save diagrams and files; task configuration (user task forms, service task connectors, DMN); unsupported elements hidden | P1 | `modeler*.spec.ts` (8 files) | Covered |
| `home` | Dashboard counts, My tasks, recent instances | P0 | – | Planned |
| `task-review` | Work and submit tasks | P0 | – | Planned |
| `process-instances` | Instance list/detail, suspend/resume/retry/terminate | P1 | – | Planned |
| `templates` | Templates, create model from template | P1 | – | Planned |
| `configuration` | Secrets, connectors, API keys | P1 | – | Planned |
| `monitoring` | NATS, messages, MCP connection pages | P2 | – | Planned |

Every spec must be listed under a module in `modules.json`; test selection
fails if a spec is missing from it.

## 7. The E2E gate on pull requests

Workflow: [`.github/workflows/e2e-gate.yaml`](../../.github/workflows/e2e-gate.yaml).

1. **Select:** `scripts/select-e2e-tests.mjs` compares the PR with its base
   branch and applies `modules.json`, file by file:
   - docs, unit tests, other products (`m8flow-frontend`, `m8flow-mcp`, …) → no E2E
   - shared code (app shell, layout, `lib/api.ts`, package files, Playwright
     config, e2e helpers, backend config/API spec/migrations, compose file) → **full suite**
   - a module's paths → **that module's specs**
   - any other UI/backend source file → **full suite** (safe default)
2. **Run:** starts a fresh M8Flow stack with Docker Compose in the runner, runs
   the selected specs, then removes the stack and its data.
3. **Report:** `scripts/e2e-gate-report.mjs` applies the criteria below and
   publishes the result as the job summary and a PR comment (updated on each
   push). The run's report folder is attached to the run for 14 days.
4. **Gate:** the **E2E Gate** check passes or fails the PR. Mark it as a
   required status check for `main` and `refactor/next-gen`.

### Using the gate on your PR

Nothing to configure per PR. Open the PR against `main` or
`refactor/next-gen` and the gate runs on every push.

1. **Check what will run (optional, before pushing):**
   `node e2e/scripts/select-e2e-tests.mjs --base origin/refactor/next-gen`
   (from `m8flow-designer`). It prints the mode, modules and specs CI will pick.
2. **Wait for the checks:** *Select E2E tests* → *Run E2E (…)* → **E2E Gate**.
   A docs-only PR skips *Run E2E* and the gate passes.
3. **Read the result:** the sticky **E2E Gate** comment on the PR (updated on
   each push), or the run's *Summary* page.
4. **On a failure:** open the run → *Artifacts* → download
   `e2e-report-<run id>` → open `report.html` (error, screenshot per failed
   test). If the stack itself failed, download `e2e-stack-logs-<run id>`.
   Fix and push again, or use *Re-run failed jobs* for an infrastructure blip.
5. **Run more than the selection:**
   - full suite on this PR: add the label **`e2e:full`**
   - any branch, by hand: Actions → **E2E Gate** → *Run workflow* → pick the
     branch → `suite: full`, or `suite: modules` with e.g. `auth,processes`

PRs from a fork run the tests but cannot post the PR comment (GitHub gives
forks a read-only token); the result is still on the run's *Summary* page.

### One-time repository setup (maintainers)

| What | Where | Why |
|---|---|---|
| Merge the gate files into the base branch | — | PRs run the workflow from their own branch, so it works on the PR that adds it; once merged, every new PR gets it. *Run workflow* appears only after it is on the default branch (`main`). |
| Create the label `e2e:full` | Issues → Labels → New label | Used to request the full suite on a PR. |
| Allow Actions to comment | Settings → Actions → General → *Workflow permissions* | The workflow asks for `pull-requests: write`; if the org restricts it, only the comment is lost. |
| Make the gate required | Settings → Branches → rule for `main` and `refactor/next-gen` → *Require status checks* → **E2E Gate** | Blocks merging on a failed gate. The check name appears in the list after the workflow has run once. |

**Files the gate needs (commit together):**
`.github/workflows/e2e-gate.yaml`, `m8flow-designer/e2e/` (specs, `helpers/`,
`fixtures/`, `scripts/`, `modules.json`, this README),
`m8flow-designer/scripts/e2e-run.mjs`, `e2e-dashboard.mjs`,
`e2e-dashboard.template.html`, `m8flow-designer/package.json` and
`m8flow-designer/playwright.config.ts`. The CI stack uses `sample.env` and
`docker/m8flow-docker-compose.yml` as they are in the repo; no secrets needed.

### Pass / fail criteria

| Result | When |
|---|---|
| ✅ **PASS** | No E2E-relevant changes, **or** every selected test passed (a test may be skipped only with a stated reason, e.g. no connector configured). |
| ✅ **PASS (with flaky tests)** | A test failed once and passed on its automatic retry (CI retries once). Listed in the report; fix it before it becomes a failure. |
| ❌ **FAIL** | Any test failed or timed out; a setup/global error; the stack did not start; tests were selected but none ran; or every test was skipped. |

A module that changed but has no specs yet does not block the PR; the report
lists it under *Changed modules with no E2E coverage yet*.

## 8. Troubleshooting

| Problem | Fix |
| --- | --- |
| `Executable doesn't exist` / browser not found | `npx playwright install chromium` |
| Screenshots don't show in the report | Keep `report.html` inside its run folder; it loads images from `artifacts/` next to it |
| Every test fails at login | Check backend `:6840` and Keycloak `:6842` are up and the seed users exist |
| Invitation tests (PAR-04/07) fail with "did not return invitation_link" | Unset SMTP in the local backend |
| `[cleanup] ... skipped` warnings | Cleanup could not reach Keycloak or the API; the test result is not affected. Leftover mock data is removed on the next run |
| Service Task tests are skipped | The connector catalog is empty in this environment |
| Test selection fails with "Specs not mapped to any module" | Add the new spec to `modules.json` |
| Port 9323 already in use | Set another port: `E2E_REPORT_PORT=9400 npm run test:e2e:dashboard` |
