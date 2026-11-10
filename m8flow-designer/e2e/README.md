# M8Flow E2E tests

Playwright (Chromium) tests that run against a **live stack** (UI → backend →
Keycloak → database), not mocks. Run all commands from `m8flow-designer/`.

## Setup (once)

```sh
npm install
npx playwright install chromium
```

## Before a run

1. Start the backend stack with Docker Compose (backend `:6840`, Keycloak `:6842`).
2. Make sure the seed users exist (password = username):
   - Tenant `m8flow`: `admin`, `editor`, `submitter`, `viewer`, `reviewer`, `integrator`
   - Master realm: `super-admin / super-admin`
3. Leave SMTP **unset** in the local backend (invitation tests need it).

The UI (`:6853`) starts by itself. The seed (below) adds the test data on the
first run, so nothing has to be set up by hand.

## Test data (seeded catalog)

Before the first test, the seed (`seed/seed.ts`, list in `seed/baseline.json`)
signs in the users and adds what is missing; running it again changes nothing:

- **Templates** `e2e-<key>`, one per folder in `seed/catalog/templates/<key>/`
  (diagram, forms, decision table; `paths.json` lists the routes through it):
  - six use cases (Work From Home, Travel Request, Customer Complaint, Order
    Fulfilment, Invoice Approval, Content Publishing), each also seeded as a
    published process in the group **E2E Seed Catalog** (plus one Work From
    Home process kept **paused**; each seeded process has a status in
    `baseline.json`: draft, published or paused);
  - `flow-*`: small approval and task processes for the process-flow and run
    specs (single and two-step approval, decision buttons, routing by amount,
    parallel approval, failing step, HTTP call that is refused, a script step
    and a diagram with its BPMN test file, ...).
- **Refused files** in `seed/catalog/refused/` (diagrams and a broken BPMN test file), uploaded by the guard tests.
- The database connection `postgres_v2/e2e` for the templates' database steps. It
  lets processes run SQL with its login, so it is only made from the repository
  `.env` (`POSTGRES_USER` / `POSTGRES_PASSWORD`) on a local or CI stack. For any
  other stack set `M8FLOW_E2E_PG_DSN` (e.g. `host=... dbname=... user=e2e_user
  password=...`, a user that may only touch the `e2e_*` tables); without it the
  routes with a database step are skipped.

Tests never change the seeded data: a test that changes something works on its
own copy (a copy of a seeded process, or a model created from a seeded
template) and deletes it afterwards. Leftovers of a stopped run are removed by
the next run.

To change a template, edit `seed/tools/build_catalog.py` (or
`seed/tools/flow_templates.py`), then run
`python3 e2e/seed/tools/build_catalog.py` and check every route on the engine
with `python3 -I e2e/seed/tools/validate_catalog.py` (needs `SpiffWorkflow==3.2.0`).
The next test run imports the changed template as a new version.

## Run

| What | Command |
| --- | --- |
| Whole suite | `npm run test:e2e` |
| One spec file | `npm run test:e2e -- e2e/login.spec.ts` |
| One test by ID | `npm run test:e2e -- -g "FLW-28"` |
| Watch the browser | `npm run test:e2e -- --headed` |
| Debug | `npm run test:e2e -- --debug` |
| UI mode | `npm run test:e2e:ui` |

Anything after `--` goes to Playwright. Tests run one at a time.

Useful environment variables: `M8FLOW_DESIGNER_BASE_URL`, `M8FLOW_BACKEND_BASE_URL`,
`M8FLOW_E2E_TENANT_SLUG` (default `m8flow`), `E2E_REPORT_KEEP` (keep newest N runs).
User logins can be overridden with `M8FLOW_E2E_<ROLE>_USERNAME` / `_PASSWORD`.

## Reports

Each run saves `e2e/reports/<date_time>/` (git-ignored) with:

- `report.html`: summary and every test; failed tests include the error and a screenshot
- `results.json`: result and error of every test
- `artifacts/<test>/`: screenshot and page snapshot (failed tests only)

`e2e/reports/index.html` is a dashboard of all runs. Open either file in a browser.
Rebuild without running tests: `node scripts/e2e-dashboard.mjs`.

## Modules and specs

[`modules.json`](modules.json) maps each module to its source paths and specs.
Every spec must be listed there.

| Module | Specs | Status |
| --- | --- | --- |
| `auth` | `login.spec.ts`, `identity-auth-parity.spec.ts` | Covered |
| `processes` | `processes.spec.ts`, `process-models.spec.ts` | Covered |
| `process-flow` | `e2e-flow*.spec.ts` (FLW-01..59), `run-user-task.spec.ts`, `run-service-task.spec.ts` | Covered |
| `modeler` | `modeler*.spec.ts`, `run-seeded-processes.spec.ts` (every route of the use cases) | Covered |
| `home`, `task-review`, `process-instances`, `templates` | `e2e-flow*.spec.ts` | Partly covered |
| `configuration`, `monitoring` | – | Planned |

### Process-flow tests

- Each spec file creates its models from the seeded `flow-*` templates in a group of its own, and deletes them with their instances afterwards.
- Setup is done through the API; the UI is used only for the step being checked.
- No fixed waits: tasks and statuses are polled.
- A possible product defect uses `expect.soft` with a message starting `POSSIBLE DEFECT`.
- Tags: `@smoke`, `@workflow`, `@permissions`, `@validation`, `@import`, `@reliability`, `@counts`.
  Run `@counts` tests with `--workers=1`.

## E2E gate on pull requests

Workflow: [`.github/workflows/e2e-gate.yaml`](../../.github/workflows/e2e-gate.yaml).
It runs on every PR to `main` or `refactor/next-gen`:

1. Picks the specs to run from the changed files (`scripts/select-e2e-tests.mjs`).
   Docs-only changes skip E2E; shared code runs the full suite.
2. Starts a fresh stack with Docker Compose and runs the selected specs.
3. Posts the result as a PR comment and attaches the report to the run.

Add the label `e2e:full` to force the full suite. To preview the selection:
`node e2e/scripts/select-e2e-tests.mjs --base origin/refactor/next-gen`.

The gate **fails** if any test fails or times out, the stack does not start, or no
test runs. A test that fails once and passes on retry is reported as flaky and passes.

### When the gate fails

Open the failed run (PR → Checks → E2E Gate). Its **Summary** lists the failed tests. The
run id is `ci-<PR number>-<run id>-<attempt>`; download these artifacts from the run page:

| Artifact | Contains | Kept |
| --- | --- | --- |
| `e2e-report-<run id>` | `report.html`, `results.json`, screenshots of failed tests | 14 days |
| `e2e-stack-logs-<run id>` | `stack-logs.txt`: logs of every stack service (only when the job failed) | 7 days |
| `e2e-selection` | `selection.json`: which modules and specs were picked, and why | default |

Unzip the report and open `report.html` in a browser. `[seed] …` lines at the start of the
test log show whether the baseline was ready.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Browser not found | `npx playwright install chromium` |
| Every test fails at login | Check backend and Keycloak are up and seed users exist |
| Invitation tests fail ("no invitation_link") | Unset SMTP in the local backend |
| Service Task tests skipped | The connector catalog is empty here |
| "Specs not mapped to any module" | Add the spec to `modules.json` |
