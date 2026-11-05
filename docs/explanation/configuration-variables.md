# Configuration Variables and Vault Integration Contract

**Status: integration design for current `main`; implementation is in progress.**

This document records the data and API contract for bringing the configuration
variable and connector-secret work from `upstream/main-v1` into the current
M8Flow architecture. It is intended to keep the database, backend, Vault,
runtime, and designer changes aligned.

## Concepts

### Manual configuration variables

A configuration variable is a tenant-owned, reusable name and value maintained
under **Configuration**. It is distinct from a connector profile field and
from a process variable. This slice provides the catalog and CRUD API; it does
not implicitly interpolate variables into BPMN expressions or arbitrary
service-task parameters. A future consumer must request resolution through an
explicit, tenant-scoped backend interface.

Each row has an immutable UUID, tenant ID, display name, optional description,
sensitivity flag, configured flag, creator, and timestamps. Non-sensitive
values may be JSON and are stored in the catalog row. Sensitive rows have no
value in the database row; only their provider reference and configured state
are represented there.

Names are trimmed, 1–255 characters, and limited to ASCII letters, digits,
underscores, and hyphens. Names are unique case-insensitively within a tenant;
the spelling first supplied is retained for display.

### Connector profile fields

Connector fields remain owned by a connector profile and its registered
backend descriptor. The backend descriptor, not a client-supplied flag,
determines whether a field is sensitive. A field must never be treated as
non-sensitive merely because the UI omits or changes a sensitivity property.

The target schema records field metadata and non-sensitive values in
tenant-scoped connector-variable rows. Sensitive field values are kept outside
those rows in one provider document per profile. The current profile ID is
retained as the stable document identifier; converting the current integer ID
to a UUID is not required for this contract.

## Storage invariants

- A sensitive value is never stored in plaintext in PostgreSQL, emitted in an
  API response, included in an audit event, or written to logs.
- Sensitive-value metadata lives in PostgreSQL; the value lives only in the
  configured secret provider. Database mode continues to use the existing
  encrypted secret provider. Vault mode uses KV v2.
- With Vault enabled, a manual variable uses its immutable row UUID as the
  document identifier:

  ```text
  kv/m8flow/tenants/{tenant_id}/secrets/configuration-variable/{named_value_id}
  ```

  Its KV document is exactly `{"value": "..."}`. It contains no variable
  name, description, user, or timestamps.
- With Vault enabled, a connector profile uses its stable profile ID:

  ```text
  kv/m8flow/tenants/{tenant_id}/secrets/connector-configuration/{profile_id}
  ```

  The document contains only the profile's sensitive field names and values.
  Updates use Vault KV versions for compare-and-set so concurrent edits do not
  silently overwrite one another.
- Vault paths include the tenant ID and are protected by that tenant's AppRole
  policy. Provisioning credentials may create tenant identities but must not be
  used to read tenant secret values.
- Runtime resolution is tenant-scoped and fail-closed: a missing provider value
  or invalid profile must stop execution before a connector request is sent.
- The existing database secret provider remains the default until an
  environment explicitly enables Vault. Enabling Vault does not silently
  switch or delete existing values; that requires a verified migration.

## API contract

The named-value API is rooted at `/v1.0/m8flow/named-values`:

| Method and path | Behavior |
|---|---|
| `GET /v1.0/m8flow/named-values` | List metadata and safe values for the active tenant. |
| `POST /v1.0/m8flow/named-values` | Create a variable. Body: `name`, optional `description`, `value`, and `is_sensitive`. |
| `GET /v1.0/m8flow/named-values/{id}` | Read one tenant-owned variable by immutable ID. |
| `PUT /v1.0/m8flow/named-values/{id}` | Update metadata and, when supplied, its value or sensitivity. |
| `DELETE /v1.0/m8flow/named-values/{id}` | Delete the catalog row and its provider value. |

Responses contain `id`, `tenantId`, `name`, `description`, `isSensitive`,
`isConfigured`, and timestamps. A non-sensitive response may include `value`.
A sensitive response always contains `value: null`; `isConfigured` indicates
whether a value exists without revealing it.

Mutations require one concrete active tenant and the existing backend
authorization checks. A super-admin must select a tenant before writing.
Frontend visibility uses the backend permission-check result; the backend
route remains the enforcement point.

Sensitivity updates follow these rules:

- Creating a variable requires a non-empty value.
- Switching a non-sensitive variable to sensitive requires a newly supplied
  non-empty value. The old database value is not copied to Vault implicitly.
- Editing a configured sensitive variable leaves the existing value untouched
  when `value` is omitted or empty. A non-empty value replaces it.
- Switching a sensitive variable to non-sensitive requires a new value in the
  request. The API never fetches the hidden value to prefill the form.
- A provider write completes and is verified before the database points to the
  new value. If the database update fails, cleanup is best effort and must not
  delete the last known-good provider value.

## Current-main adaptation

Current `main` already has a generic tenant secret provider, Vault KV client,
Vault-backed secret API, connector profiles, and designer screens. The new
work must integrate with those seams rather than add a second general secret
API.

For connector profiles, the current implementation stores fields through
`secrets` and keeps references in `secret_refs`. The target per-field schema
must preserve that behavior while providing database storage for fields the
descriptor marks non-sensitive. Backfill and cutover must be reversible where
practical; do not clear the existing profile data or provider keys until the
new rows and Vault document have been read back and verified.

The API schema must be added to the current backend's `api.yml`, routes must
use current tenant and authorization helpers, and new UI must be implemented in
`m8flow-designer`. Do not copy the old `m8flow-frontend` pages or backend code
that depends on `spiffworkflow_backend`.

## Migration and rollout requirements

The migration files from `upstream/main-v1` are not directly reusable: their
revision chain is not the current `main` chain. New revisions must attach to the
current Alembic graph and retain tenant isolation and the storage constraints.
The additive migration copies ordinary connector settings into the new rows,
keeps legacy profile JSON and secret references intact, and stores only pointers
for sensitive fields. After migration, run
`python bin/backfill_configuration_variable_metadata.py` in read-only mode to
verify provider payloads; add `--apply` to persist configured flags,
unreferenced named-value metadata, and readback-verified per-profile secret
documents. This command never prints or deletes secret values. It refuses to
overwrite a different document at a target path. Keep the old provider keys
until the new backend has been deployed and verified.

Before writing a data migration, determine whether any environment has already
applied the `main-v1` migrations or written values to its Vault paths. Support
both the current-main and previously-migrated schema states, or provide a
separate, explicit operator migration. A migration must not overwrite a
conflicting value, print plaintext, or delete an old Vault document before the
replacement is verified.

Keep Vault disabled by default during rollout. First deploy additive schema and
backend compatibility, migrate and verify existing values, then enable Vault
in dev. Promote to QA and demo only after connector execution, tenant isolation,
secret redaction, and restore behavior are verified.
