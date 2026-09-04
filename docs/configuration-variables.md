# Configuration Variables

M8Flow exposes one tenant-scoped **Configuration Variables** catalog. The catalog is
stored in `m8flow_named_value` and is the source for names, descriptions, sensitivity,
configured state, authorization, and tenant isolation.

## Storage

- Non-sensitive variables have `is_sensitive = false` and their value is stored in
  `m8flow_named_value.value`.
- Sensitive variables have `is_sensitive = true`, `is_configured = true`, and a `NULL`
  database value. Their actual value is stored by the configured secret provider.
- With Vault enabled, the provider key is immutable and uses the catalog row ID:

  ```text
  kv/m8flow/tenants/{tenant_id}/secrets/configuration-variable/{named_value_id}
  ```

  The Vault KV document is exactly `{"value": "..."}`. It contains no variable
  name, tenant metadata, user metadata, descriptions, timestamps, or state flags.
  `m8flow_named_value` remains the sole source of that metadata.
- Sensitive values are never returned by list/detail APIs. Editing leaves the value
  blank; an empty submission retains the existing provider value.
- A sensitive-to-non-sensitive change requires a newly supplied value. A
  non-sensitive-to-sensitive change writes to the provider before clearing the database
  value.

Connector-specific fields are not named values. Non-sensitive connector fields remain
in `m8flow_connector_variable.value`; sensitive connector fields are stored in one
Vault KV document at:

```text
kv/m8flow/tenants/{tenant_id}/secrets/connector-configuration/{configuration_id}
```

The Configuration Variables list reads only `m8flow_named_value`; it does not enumerate
Vault paths.

## Validation

Creation and edition use the same validation rules:

- `name` is trimmed before validation and storage.
- `name` is required and must contain at least 1 character after trimming.
- `name` may contain only letters, numbers, underscores (`_`), and hyphens (`-`).
- `name` may contain at most 255 characters after trimming.
- Names are compared case-insensitively within a tenant. For example, `Test`,
  `test`, and `TEST` cannot coexist in the same tenant, but the original casing is
  preserved for display.
- `value` is required when creating a variable. Sensitive values must be non-empty
  when first configured or when changing a non-sensitive variable to sensitive.
- When editing an already-sensitive variable, its current value is not loaded into
  the form. Supplying a value replaces the provider value; leaving it empty keeps the
  existing provider value.
- `description` is optional and has no application-level length limit beyond the
  database column capacity.

The UI displays validation failures in red helper text directly below the affected
input. The backend repeats the validation and the database functional unique index is
the final authority for concurrent requests.

## Legacy Vault Rollout

Earlier builds stored manual sensitive values at
`.../secrets/{named_value_id}` and some older builds used a mutable name-keyed path.
They could also include copied metadata. After deploying this change, run the migration
once with Vault enabled:

```bash
docker compose -f docker/m8flow-docker-compose.yml exec m8flow-backend \
  python m8flow-backend/bin/migrate_named_value_vault_payloads.py --dry-run
docker compose -f docker/m8flow-docker-compose.yml exec m8flow-backend \
  python m8flow-backend/bin/migrate_named_value_vault_payloads.py
```

The command checks the namespaced path first. It reads only a known legacy row path's
`value`, writes the new `{"value": "..."}` document, verifies it, then deletes the old
document. If copying, verification, or cleanup fails, the old document is retained and
the command exits non-zero. If an existing new-path value differs, it reports a conflict
and does not overwrite either value. It never prints plaintext values.

## API

The API is available at `/v1.0/m8flow/named-values` and requires an active tenant context.
Super-admin users must select a concrete tenant before creating, updating, or deleting
a variable. The request body accepts `name`, optional `description`, `value`, and
`is_sensitive`.

Do not send sensitive values to logs, shell history, or support tickets. The server
rejects invalid sensitivity transitions and enforces the tenant/name uniqueness and
database storage constraint.
