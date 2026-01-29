RLS Notes (PostgreSQL)

Tenant context
The tenant context is passed via:
  SET LOCAL app.current_tenant = '<tenant_id>';

RLS policies compare m8f_tenant_id to current_setting('app.current_tenant', true). If the
setting is unset or empty, queries return no rows and writes are rejected.

Role hardening
Runtime roles must not be superuser and must not have BYPASSRLS. Suggested roles:

1) Admin role (trusted, can bypass RLS explicitly)
   - SUPERUSER or ALTER ROLE admin_role BYPASSRLS

2) Migration role (used by Alembic)
   - Member of admin role OR granted BYPASSRLS
   - Should set app.current_tenant explicitly for tenant-scoped data changes when possible.

3) Runtime role (used by the app)
   - No SUPERUSER
   - No BYPASSRLS
   - Only normal DML permissions on tables

Example role setup (adjust names as needed):
```sql
  CREATE ROLE m8flow_admin LOGIN PASSWORD '...';
  ALTER ROLE m8flow_admin BYPASSRLS;

  CREATE ROLE m8flow_migrate LOGIN PASSWORD '...';
  GRANT m8flow_admin TO m8flow_migrate;

  CREATE ROLE m8flow_runtime LOGIN PASSWORD '...';
  REVOKE BYPASSRLS FROM m8flow_runtime;
```

Tenant context in app sessions
Set the tenant at session start or per-transaction:
```sql
  SET LOCAL app.current_tenant = 'tenant-a';
```

Background jobs and async workers must set a tenant context before queries or writes.
In Python, use m8flow_backend.tenancy.set_context_tenant_id(...) around the job.

PostgreSQL strict mode
The ORM now sets the tenant context per transaction using:
```sql
  SET LOCAL app.current_tenant = '<tenant_id>'
```
and raises if the tenant is missing. To allow admin/migration workflows without a tenant:
  M8FLOW_ALLOW_MISSING_TENANT_CONTEXT=true
When missing is allowed, the session executes:
  RESET app.current_tenant

Non-PostgreSQL databases
MySQL/SQLite rely on ORM filtering only (no DB-level RLS enforcement).

FORCE ROW LEVEL SECURITY
If you want RLS to apply even to table owners, use:
  ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
Only do this if your admin/migration workflows set tenant context or use a bypass role.

Operational verification (examples)
```sql
  -- No tenant set: should return 0 rows
  RESET app.current_tenant;
  SELECT * FROM process_instance LIMIT 1;

  -- Tenant set: should return only that tenant's rows
  SET LOCAL app.current_tenant = 'tenant-a';
  SELECT count(*) FROM process_instance;

  -- Writes without tenant should fail
  RESET app.current_tenant;
  INSERT INTO process_instance (...) VALUES (...);

```

RLS verification steps (PostgreSQL)
Non-superuser setup:

```sql
  -- Create a runtime role for RLS testing
  CREATE ROLE m8flow_runtime_test LOGIN PASSWORD 'change_me';
  ALTER ROLE m8flow_runtime_test NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

  -- Allow it to connect to the database
  GRANT CONNECT ON DATABASE postgres TO m8flow_runtime_test;

  -- Grant usage on schema (assuming public)
  GRANT USAGE ON SCHEMA public TO m8flow_runtime_test;

  -- Grant DML on all tables (adjust schema if not public)
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO m8flow_runtime_test;

  -- Ensure future tables are accessible too
  ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO m8flow_runtime_test;

RLS test setup:
  -- Create two tenants.
  INSERT INTO m8flow_tenant (id, name) VALUES ('tenant-a', 'tenant-a') ON CONFLICT (id) DO NOTHING;
  INSERT INTO m8flow_tenant (id, name) VALUES ('tenant-b', 'tenant-b') ON CONFLICT (id) DO NOTHING;

  -- Example: use process_instance table. Adjust columns for your schema.
  -- Ensure you can insert rows for each tenant.
  BEGIN;
  SET LOCAL app.current_tenant = 'tenant-a';
  INSERT INTO process_instance (
      id,
      process_model_identifier,
      process_model_display_name,
      process_initiator_id,
      status,
      updated_at_in_seconds,
      created_at_in_seconds,
      m8f_tenant_id
  ) VALUES (
      100001,
      'rls_test_a',
      'rls_test_a',
      1,
      'running',
      0,
      0,
      'tenant-a'
  );
  COMMIT;

  BEGIN;
  SET LOCAL app.current_tenant = 'tenant-b';
  INSERT INTO process_instance (
      id,
      process_model_identifier,
      process_model_display_name,
      process_initiator_id,
      status,
      updated_at_in_seconds,
      created_at_in_seconds,
      m8f_tenant_id
  ) VALUES (
      100002,
      'rls_test_b',
      'rls_test_b',
      1,
      'running',
      0,
      0,
      'tenant-b'
  );
  COMMIT;

Verification queries:
  -- Tenant A should only see A rows.
  BEGIN;
  SET LOCAL app.current_tenant = 'tenant-a';
  SELECT id, m8f_tenant_id FROM process_instance WHERE id IN (100001, 100002) ORDER BY id;
  COMMIT;

  -- Tenant B should only see B rows.
  BEGIN;
  SET LOCAL app.current_tenant = 'tenant-b';
  SELECT id, m8f_tenant_id FROM process_instance WHERE id IN (100001, 100002) ORDER BY id;
  COMMIT;

  -- No tenant set: reads should return zero rows.
  BEGIN;
  RESET app.current_tenant;
  SELECT id, m8f_tenant_id FROM process_instance WHERE id IN (100001, 100002) ORDER BY id;
  COMMIT;

  -- No tenant set: writes should fail.
  BEGIN;
  RESET app.current_tenant;
  INSERT INTO process_instance (
      id,
      process_model_identifier,
      process_model_display_name,
      process_initiator_id,
      status,
      updated_at_in_seconds,
      created_at_in_seconds,
      m8f_tenant_id
  ) VALUES (
      100003,
      'rls_test_none',
      'rls_test_none',
      1,
      'running',
      0,
      0,
      'tenant-a'
  );
  COMMIT;
```