# Integration tests

These tests run the host modules on the real `m8flow-core` wheel against
PostgreSQL, with nothing in core mocked. Run them before and after swapping the
core wheel: a difference between the two runs is a regression caused by core.

They are opt-in. PostgreSQL tests require `M8FLOW_TEST_POSTGRES_URI`; live Vault
tests require `M8FLOW_TEST_VAULT_ADDR` and `M8FLOW_TEST_VAULT_TOKEN`. Each group
skips independently when its service is not configured, so the default
`uv run pytest` run is unchanged.

## Run

Point `M8FLOW_TEST_POSTGRES_URI` at a PostgreSQL 13+ role that can
`CREATE DATABASE` and `CREATE ROLE`. Any database on that server works as the
entry point:

```sh
cd m8flow-backend
M8FLOW_TEST_POSTGRES_URI=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
  uv run pytest tests/integration -n auto
```

The live Vault tests require an operator token for a disposable Vault instance
with the configured KV v2 and AppRole mounts. They create uniquely prefixed
tenant policies, AppRoles, and probe secrets, and remove those resources after
the test. Run only those tests with:

```sh
M8FLOW_TEST_VAULT_ADDR=http://localhost:8200 \
M8FLOW_TEST_VAULT_TOKEN=<operator-token> \
  uv run pytest tests/integration/test_vault_tenant_isolation.py
```

Optional settings are `M8FLOW_TEST_VAULT_KV_MOUNT` (default `kv`),
`M8FLOW_TEST_VAULT_APPROLE_MOUNT` (default `approle`),
`M8FLOW_TEST_VAULT_NAMESPACE`, and `M8FLOW_TEST_VAULT_SKIP_VERIFY=true` for a
disposable local instance with an untrusted development certificate.

Each pytest worker creates its own database, migrates it with `alembic upgrade
head`, and creates a login role without `SUPERUSER` or `BYPASSRLS`. The host
connects as that role, so core's queries run under the same row-level security
as production. The database and role are dropped when the worker finishes.

### Test a local core wheel for collaboration publishing

Collaboration publishing requires a core version that accepts caller-owned
`process_xml_digest` values. The host uses a distinct digest for each model
generation, release, and BPMN filename so identical BPMN cannot merge separate
deployments. Core `1.1.0b2` rejects these digests for collaborations. Keep the
registry dependency and lockfile unchanged until the fixed core is published,
then update both to that exact published version.

To verify the fix before publication, build the core wheel and add it to the
Python import path for a test invocation. On PowerShell, from
`m8flow-backend` with the backend virtual environment already synced:

```powershell
$env:PYTHONPATH = "C:\path\to\m8flow_core-1.1.0-py3-none-any.whl"
.\.venv\Scripts\python.exe -m pytest tests/unit/m8flow_backend/routes/test_templates_controller.py -k collaboration_template
.\.venv\Scripts\python.exe -m pytest tests/unit/m8flow_backend/workflow/test_workflow_operations.py -k versioned_collaboration
.\.venv\Scripts\python.exe -m pytest tests/integration/test_collaboration.py tests/integration/test_schema_matches_core.py
Remove-Item Env:PYTHONPATH
```

Do not commit a local wheel dependency or vendor core source. This fix does
not change the database schema. The existing scheduler poller delivers
collaboration messages, and the PostgreSQL tests exercise versioned publishing
under tenant RLS.

The HTTP regression builds its template archive in memory from the existing
`order-fulfilment-collaboration.bpmn` fixture and a small approval form. It
imports and publishes the template, creates two process models, and publishes
a form-only second release while checking that existing instances retain their
original source and form. No ZIP fixture is stored in the repository.

## What is covered

| File | Covers |
|---|---|
| `test_process_lifecycle.py` | Start, claim, complete to the end; suspend, resume, terminate; claim-before-complete and double-completion rules |
| `test_authorization.py` | Core commands allowed or denied by the host policy from `m8flow.yml` grants, for `editor`, `submitter`, `reviewer`, and `viewer` |
| `test_tenant_isolation.py` | RLS hides other tenants' core rows; host listings are tenant-scoped; cross-tenant claims fail |
| `test_lane_assignment.py` | BPMN lanes reach lane members only, late joiners after reconcile, and never another tenant's lane |
| `test_service_tasks.py` | Service tasks through the host registry and a stub connector proxy: success, secret sentinels, failure recording |
| `test_scheduler.py` | Intermediate timer jobs created by core and released by `workflow.run_due` |
| `test_vault_tenant_isolation.py` | Live Vault tenant-token isolation, concurrent first-use provisioning, and fresh-client reconciliation after restart |
| `test_error_escalation_events.py` | Uncaught escalation and error end events finish the instance; error and escalation event subprocesses run only when thrown, and an interrupting one cancels the waiting user task beside it (M8F-665) |
| `test_multi_instance_bpmn.py` | Sequential and parallel multi-instance loops: collection and cardinality inputs, output mapping errors, completion conditions, and a parallel review through claim and complete in which each iteration keeps its own data (M8F-640) |
| `test_schema_matches_core.py` | The migrated schema matches core's ORM; the runtime role is subject to RLS |
| `test_message_correlation.py` | HTTP delivery, replay, ambiguous or missing matches, tenant isolation, and upgrades from both previous host heads |
| `test_collaboration.py` | Modeled collaboration messages and delivery across isolated tenants |
| `test_seed_complaint.py` | All four complaint paths with real signal events, losing-branch cancellation, separate role users, and tenant RLS |

`tests/unit/m8flow_backend/test_core_contract.py` is the fast companion: it
checks the core imports, attributes, call signatures, and string protocols the
host depends on, without a database.

## Conventions

- Tests share one database per worker and isolate by using a fresh tenant id
  (`support.new_tenant_id`).
- Act through `support.tenant_session(tenant_id)`, which binds the tenant before
  the transaction starts so the RLS hook sets `app.current_tenant`.
- Provision users with `support.provision_member`, which uses the same identity
  calls as login and the real `m8flow.yml` grants. Do not grant core's built-in
  `admin` role: it bypasses the host policy these tests exist to exercise.
- Use the `admin_engine` fixture only for cross-tenant assertions.
