# Shared-Realm Organization Group Role Mapping

This document explains how M8Flow derives tenant-scoped permissions from
Keycloak organization groups in the shared-realm model.

It is written around cases like:

- user: `mary`
- tenant alias: `org1`
- tenant id: `a787d38c-53fe-44d7-992d-5b2e8e590cec`
- organization groups: `Approvers`, `Finance`, `HR`
- group attributes on `Approvers`:
  - `m8flow_role_names = editor`
  - `m8flow_role_names = integrator`
  - `m8flow_role_names = reviewer`
  - `m8flow_role_mapping_configured = true`

## Short Version

In the shared-realm design, Keycloak organization groups are the source of truth
for tenant roles.

The token does **not** carry the organization-group attributes. It only carries
the selected tenant and the selected tenant's group names:

```json
{
  "organization": {
    "org1": {
      "id": "a787d38c-53fe-44d7-992d-5b2e8e590cec",
      "groups": ["Approvers", "Finance", "HR"]
    }
  }
}
```

M8Flow then uses those group names to fetch the full organization-group records
from Keycloak, reads the `m8flow_role_names` attributes server-side, and mirrors
the resulting tenant roles into local tenant-scoped groups such as:

- `a787d38c-53fe-44d7-992d-5b2e8e590cec:editor`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:integrator`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:reviewer`

Those local groups are what the backend permission checks actually use.

## Why The Attributes Are Not In The Token

The token is intentionally carrying **group membership**, not the full group
configuration.

Two different pieces of information are involved:

1. Group membership:
   Which organization groups the user belongs to in the selected tenant.

2. Group-to-role mapping:
   Which tenant roles a given organization group grants.

The first is placed in the token under the `organization` claim. The second is
kept on the Keycloak organization group itself as attributes.

This separation is why you see:

- `organization.org1.groups = ["Approvers", "Finance", "HR"]`

but you do **not** see:

- `m8flow_role_names`
- `m8flow_role_mapping_configured`

inside the token payload.

## Important Distinction: This Token Is An M8Flow Token

The payload you pasted has:

- `"iss": "http://localhost:6840"`
- `"sub": "service:http://localhost:6842/realms/m8flow::service_id:..."`

That means it is the **M8Flow-issued internal token**, not a raw Keycloak token.

M8Flow uses the Keycloak sign-in result, resolves the selected tenant, rewrites
the `organization` claim to the active tenant, and then issues its own internal
token for the frontend/backend session.

The selected-tenant claim rewrite happens in:

- [authentication_controller_patch.py](../m8flow-backend/src/m8flow_backend/routes/authentication_controller_patch.py)
  - `_synchronize_selected_organization_claims()`

That function fetches the selected member's organization groups from Keycloak
and writes only the normalized group names into the token:

- `organization.<tenant_alias>.groups = [...]`

It does **not** embed the Keycloak group attributes in the token.

## Where The Group Attributes Live

The shared-realm group-role mapping is stored on the Keycloak organization group
attributes using two keys defined in:

- [tenant_group_mapping.py](../m8flow-backend/src/m8flow_backend/services/tenant_group_mapping.py)

Those keys are:

- `m8flow_role_names`
- `m8flow_role_mapping_configured`

The values are interpreted like this:

- `m8flow_role_mapping_configured = true`
  means "this group has an explicit M8Flow role mapping"
- each `m8flow_role_names` value is one tenant role granted by the group

Example:

```text
Approvers
  m8flow_role_names = editor
  m8flow_role_names = integrator
  m8flow_role_names = reviewer
  m8flow_role_mapping_configured = true
```

## Where M8Flow Checks Those Attributes

The main attribute-reading logic is in:

- [keycloak_service.py](../m8flow-backend/src/m8flow_backend/services/keycloak_service.py)
  - `organization_group_role_names()`

That function does this:

1. Reads the group's `attributes`
2. Checks whether `m8flow_role_mapping_configured` is enabled
3. If enabled, returns the normalized `m8flow_role_names`
4. If not enabled, falls back to the built-in default mapping based on the group name

So for `Approvers` with explicit attributes, the returned role list is taken
from the attributes, not from the default static mapping.

The corresponding write path is also in:

- [keycloak_service.py](../m8flow-backend/src/m8flow_backend/services/keycloak_service.py)
  - `set_organization_group_role_names()`

That function persists:

- `m8flow_role_mapping_configured = ["true"]`
- `m8flow_role_names = [...]`

back to the Keycloak organization group.

## How Those Attributes Become Permissions For The User

The auth flow is:

1. Keycloak authenticates the user
2. M8Flow finalizes the selected tenant
3. M8Flow reads the selected tenant's organization groups from the token
4. M8Flow fetches the full Keycloak organization-group records
5. M8Flow reads `m8flow_role_names`
6. M8Flow mirrors the resulting tenant roles into local tenant-scoped groups
7. Permission checks use those local groups

The most important code is in:

- [authorization_service_patch.py](../m8flow-backend/src/m8flow_backend/services/authorization_service_patch.py)
  - `_openid_group_identifiers_from_user_info()`
  - `_shared_realm_role_identifiers_from_organization_groups()`
  - `patched_create_user_from_sign_in()`

### Step 1: Read The Group Names From The Token

The token-side organization group names are normalized by:

- [tenant_identity_helpers.py](../m8flow-backend/src/m8flow_backend/services/tenant_identity_helpers.py)
  - `organization_group_identifiers_from_payload()`

That function returns only the selected tenant's organization group names, such
as:

- `Approvers`
- `Finance`
- `HR`

### Step 2: Fetch The Full Group Records From Keycloak

For shared-realm users, auth sync then resolves the full group records through:

- [authorization_service_patch.py](../m8flow-backend/src/m8flow_backend/services/authorization_service_patch.py)
  - `_shared_realm_role_identifiers_from_organization_groups()`

That helper:

1. Resolves the active organization from the token
2. Looks up each organization group by name
3. Loads the full group by id
4. Calls `organization_group_role_names()` on the full record

This "by id" step matters because Keycloak's brief group list does not reliably
contain the `attributes` block. The full group record does.

### Step 3: Derive Local Tenant-Scoped Groups

After reading the mapped roles, `_openid_group_identifiers_from_user_info()`
builds the local group identifiers for the active tenant.

For `mary` in tenant `org1`, that can become:

- `a787d38c-53fe-44d7-992d-5b2e8e590cec:Approvers`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:Finance`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:HR`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:editor`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:integrator`
- `a787d38c-53fe-44d7-992d-5b2e8e590cec:reviewer`

Then:

- `patched_create_user_from_sign_in()`

synchronizes those groups onto the local mirrored user row.

## Why The Top-Level `roles` Claim Still Looks Small

In the shared-realm model, M8Flow does **not** rely on direct Keycloak user-role
assignments for tenant authorization.

That is why you may still see:

```json
"roles": ["default-roles-m8flow"]
```

even though the user effectively behaves like an editor, integrator, or reviewer
inside the selected tenant.

The tenant-scoped permissions are coming from the local mirrored group set,
not from direct top-level role claims in the token.

## How The Tenant Management UI Shows The Mapped Roles

The tenant-management UI is using the same Keycloak group attributes.

The lookup path is:

- [tenant_role_service.py](../m8flow-backend/src/m8flow_backend/services/tenant_role_service.py)
  - `_organization_group_role_lookup()`
  - `_roles_for_group()`
  - `_normalized_member_roles()`

That service loads the full organization-group records and calls:

- `organization_group_role_names()`

so the UI and the auth sync are both using the same source of truth.

## Default Mapping vs Explicit Mapping

There are two supported ways an organization group can resolve to tenant roles.

### 1. Explicit mapping through attributes

This is what your `Approvers` example is doing.

If:

- `m8flow_role_mapping_configured = true`

then M8Flow uses:

- `m8flow_role_names`

as the authoritative role list.

### 2. Built-in fallback mapping

If the explicit attributes are absent, M8Flow falls back to the static defaults
in:

- [tenant_group_mapping.py](../m8flow-backend/src/m8flow_backend/services/tenant_group_mapping.py)
  - `DEFAULT_TENANT_ROLE_TO_ORGANIZATION_GROUP`
  - `DEFAULT_ORGANIZATION_GROUP_TO_TENANT_ROLE`
  - `tenant_roles_for_organization_group()`

For example:

- `Administrators -> tenant-admin`
- `Designers -> editor`
- `Approvers -> reviewer`
- `Support -> integrator`
- `Submitters -> submitter`
- `Viewers -> viewer`

Explicit attributes override this fallback.

## Example: `mary` In `org1`

Given:

- `mary` is in `Approvers`, `Finance`, and `HR`
- `Approvers` explicitly maps to `editor`, `integrator`, `reviewer`
- `Finance` maps to `reviewer`
- `HR` maps to `reviewer`

then the important outcome is not that those roles appear in the token
attributes. The important outcome is that, after sign-in and tenant
finalization, the local user is synchronized into the corresponding
tenant-scoped groups.

That is what permission checks use.

## Operational Notes

- If you change organization-group role attributes in Keycloak, the user usually
  needs a fresh login or tenant-finalization pass so M8Flow can resynchronize
  the local mirrored groups.
- If a custom group does not grant the expected permissions, verify the group
  has:
  - `m8flow_role_mapping_configured = true`
  - one or more `m8flow_role_names` values
- If the group is a default built-in name and has no explicit attributes, M8Flow
  will still apply the static fallback mapping.
