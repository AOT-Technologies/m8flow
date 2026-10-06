# m8flow-bpmn-core 0.2.0 migration

This runbook covers upgrading the M8Flow backend to the vendored
`m8flow-bpmn-core` 0.2.0 wheel. The backend compatibility migration is
`b2c3d4e5f6a7`, after `a1b2c3d4e5f6`. The follow-up core timestamp cleanup
is `d4e5f6a7b8c9`, after the host timestamp cleanup `c3d4e5f6a7b8`.

The migration is additive and data-preserving where possible. It adds native
timestamps, normalized `work_item` state, event categories, authorization
resource fields, and tenant-scoped JSON storage. A follow-up host migration,
`c3d4e5f6a7b8`, removes the legacy epoch timestamp columns from M8Flow-owned
tables after their native datetime values have been backfilled. The final host
migration, `d4e5f6a7b8c9`, removes the corresponding legacy columns from
core-owned tables after upgrading to the 0.2.0 wheel.

## Before upgrading

1. Stop workflow writers, schedulers, and Celery workers.
2. Take and test a database backup. JSON re-keying cannot be safely reversed by
   an Alembic downgrade because one legacy hash may become multiple
   tenant-qualified rows.
3. Confirm the backend is using the matching wheel:

   ```powershell
   .\.venv\Scripts\python.exe -m pip show m8flow-bpmn-core
   Get-FileHash .\m8flow-backend\vendor\m8flow_bpmn_core-0.2.0-py3-none-any.whl -Algorithm SHA256
   ```

4. Check the current migration revision and review the generated SQL for the
   production database.

## Apply the migration

From the repository root, with the backend environment configured:

```powershell
.\m8flow-backend\bin\run_m8flow_alembic.ps1 upgrade head
```

```bash
./m8flow-backend/bin/run_m8flow_alembic.sh upgrade head
```

The command uses `M8FLOW_BACKEND_DATABASE_URI` (or
`M8FLOW_DATABASE_URI`). Do not use `stamp head` for an unverified database;
stamping records a revision without applying its data migration.

## What is validated during upgrade

The JSON phase validates all references from `bpmn_process.json_data_hash`,
`task.json_data_hash`, and `task.python_env_data_hash` before replacing the
legacy `json_data` table. It aborts before re-keying if it finds:

- a null tenant or payload reference;
- a referenced payload that is missing;
- a payload row with no tenant-qualified reference;
- a reference to a tenant that does not exist; or
- invalid/ambiguous authorization data needed for a safe backfill.

Repair the source data and rerun the migration after an abort. The migration
does not silently discard or assign an unowned payload.

### Lane groups and RBAC groups

Workflow lane groups are local runtime subjects and may legitimately have the
same `identifier` as an IdP-backed RBAC group, for example
`m8flow:Submitters`. During the authorization backfill, lane rows are assigned
an id-based key (`authorization:lane:<group-id>`), while RBAC rows retain the
identifier-based key (`authorization:<identifier>`). The migration therefore
continues only to reject duplicate identifiers among RBAC rows themselves.

After the migration, identity synchronization prefers the IdP-backed row when
both rows share an identifier. This prevents permissions from being granted to
the workflow-only lane subject. A duplicate-RBAC-identifier failure still
requires operator cleanup before retrying the upgrade.

## Post-upgrade checks

Verify the revision and the compatibility shape:

```sql
SELECT version_num FROM alembic_version_m8flow;

SELECT m8f_tenant_id, hash
FROM json_data
ORDER BY m8f_tenant_id, hash;

SELECT COUNT(*) FROM work_item;

SELECT COUNT(*)
FROM permission_target
WHERE (resource_type IS NULL) <> (resource_id IS NULL);
```

The final query must return zero. Also verify representative process starts,
task review, event history, and authorization checks for both a tenant user and
a super-admin. Run the backend compatibility suite before re-enabling workers:

```powershell
cd m8flow-backend
..\.venv\Scripts\python.exe -m pytest
```

## Rollback and retained compatibility

The `human_task` table, legacy event values, and URI-based authorization
targets remain intentionally available for compatibility. Both host and
core-owned epoch timestamp columns are removed by `c3d4e5f6a7b8` and
`d4e5f6a7b8c9`; all M8Flow runtime and API consumers use native timezone-aware
datetime fields. The migration tests retain legacy names only when creating
pre-upgrade schemas for upgrade coverage.

The host timestamp cleanup can recreate nullable columns on downgrade for
schema round-trips, but the dropped epoch values cannot be reconstructed
exactly from timezone-aware datetimes. For production recovery, restore the
tested database backup rather than relying on downgrade to recover historical
values or attempting to reverse the JSON re-key manually.
