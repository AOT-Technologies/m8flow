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
| `test_schema_matches_core.py` | The migrated schema matches core's ORM; the runtime role is subject to RLS |

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
