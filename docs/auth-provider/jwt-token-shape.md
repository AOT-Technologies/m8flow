# JWT token shape

This page lists exactly what m8flow reads from an access token. The Keycloak
mapping lives in
`m8flow-backend/src/m8flow_backend/integrations/auth/keycloak/claims.py`. The
examples on this page are taken from the golden fixtures in
`m8flow-backend/tests/fixtures/auth/keycloak_claims_golden.json`, which tests
keep in sync with the code.

## Verification rules

Before any claim is read, `base/oidc.py` checks:

| Check | Rule |
|---|---|
| Format | A JWT with a header. Malformed tokens get `TokenInvalid("Token is malformed")`. |
| Algorithm | `RS256` only. |
| Issuer (`iss`) | Must be trusted before any key is fetched. Keycloak: `<public or internal base>/realms/<realm>`. By default any realm on the configured host is trusted; with `M8FLOW_AUTH_STRICT_ISSUERS=true`, only the shared realm, the master realm and `M8FLOW_KEYCLOAK_TRUSTED_REALMS`. |
| Signature | Against the issuer's JWKS, found via discovery. Keys are cached for 10 minutes and refetched once on an unknown `kid`. |
| Required claims | `exp` and `iss`. `sub` is required by the claim mapping. |
| Expiry | `exp` in the past is rejected. |
| Audience | Accepted if `azp` equals the client id, or `aud` (string or list) contains the client id or `account`. A token with neither `aud` nor `azp` is accepted by default and rejected in strict mode. |

## Standard claims

| Claim | Maps to | Notes |
|---|---|---|
| `sub` | `VerifiedClaims.subject` | Required. Local users are keyed on `(iss, sub)`. |
| `iss` | `VerifiedClaims.issuer` | Required. For Keycloak, the realm segment becomes `issuer_key`. |
| `preferred_username`, else `username` | `username` | Used for directory lookups and the local user name. |
| `email` | `email` | Optional. |
| `azp` / `aud` | (verification only) | See [Verification rules](#verification-rules). |

## A real shared-realm token

A user signed in to the shared realm `m8flow`, active in organization `acme`,
as produced by the `m8flow-backend` client's mappers (realm info mapper, realm
roles):

```json
{
  "iss": "https://kc.example.com/realms/m8flow",
  "sub": "s1",
  "azp": "m8flow-backend",
  "exp": 1760000000,
  "preferred_username": "editor",
  "email": "e@x",
  "realm_access": { "roles": ["default-roles-m8flow", "offline_access"] },

  "m8flow_authentication_identifier": "m8flow",
  "m8flow_realm_name": "m8flow",
  "m8flow_realm_id": "3f0c...",

  "m8flow_tenant_id": "org-1",
  "m8flow_tenant_alias": "acme",
  "m8flow_tenant_name": "Acme",
  "organization": { "acme": { "id": "org-1", "name": "Acme" } }
}
```

It becomes:

```python
VerifiedClaims(
    subject="s1",
    issuer="https://kc.example.com/realms/m8flow",
    username="editor",
    email="e@x",
    roles=["default-roles-m8flow", "offline_access"],
    memberships=[Membership(tenant_ref=TenantRef(id="org-1", alias="acme", name="Acme"),
                            roles=[], groups=[], roles_complete=False)],
    active_tenant_ref=TenantRef(id="org-1", alias="acme"),
    issuer_key="m8flow",
    trust_domain=TrustDomain.SHARED,
    memberships_complete=False,
)
```

The membership has no roles because the mapper cannot read organization groups,
so on each request the host fetches this user's groups in `acme` from the
directory (see [How it works: Membership authority and group sync](./how-it-works.md#membership-authority-and-group-sync)).

## Claim-by-claim reference (Keycloak)

### Tenant claims

| Claim | Emitted by | Read as |
|---|---|---|
| `m8flow_tenant_id` | `RealmInfoMapper` | `active_tenant_ref.id`. Also the default `M8FLOW_TENANT_CLAIM` raw fallback in `bind.py`. |
| `m8flow_tenant_alias` | `RealmInfoMapper` | `active_tenant_ref.alias` |
| `m8flow_tenant_name` | `RealmInfoMapper` | The organization's display name. Also the last fallback when looking for a realm name (legacy). |
| `organization` | `RealmInfoMapper` (active org only), stock organization mappers | `memberships`, one per entry |

`RealmInfoMapper` chooses the organization like this:

1. The user attribute `m8flow_active_tenant` (an organization id or alias), if
   the user is a member of that organization.
2. Otherwise Keycloak's own resolution, for example a user with exactly one
   organization.

**Active tenant fallback:** if `m8flow_tenant_id` and `m8flow_tenant_alias` are
both missing and the token has exactly one membership, that membership becomes
the active tenant.

#### Accepted `organization` shapes

All three shapes are accepted. `groups` entries are reduced to their last path
segment (`/acme/Designers` → `Designers`) and translated to roles. The three
shapes look like this:

```jsonc
// 1. Map of alias -> details (RealmInfoMapper, stock mapper)
"organization": { "a": { "id": "A", "groups": ["/Reviewers", "/Submitters"] },
                  "b": { "id": "B", "groups": ["Administrators"] } }

// 2. List of aliases
"organization": ["a", "b"]

// 3. List of objects
"organization": [{ "alias": "a", "id": "A", "name": "Alpha", "groups": ["Designers"] }]
```

Results (from the golden fixtures):

| Shape | Memberships |
|---|---|
| 1 | `a` (id `A`): groups `Reviewers`, `Submitters` → roles `submitter`; `b` (id `B`): group `Administrators` → role `tenant-admin` |
| 2 | `a` and `b`, aliases only, no roles |
| 3 | `a` (id `A`, name `Alpha`): group `Designers` → role `editor`; also the active tenant (single membership) |

Group names not in the role table (such as `Reviewers` in the preceding example) stay in `groups`
for BPMN lanes but grant no role.

### Role claims

Roles are collected from `roles`, `realm_access.roles` and `groups`, in that
order. Each value is reduced to its last path segment, de-duplicated, and
translated with the organization group table (`Administrators` → `tenant-admin`,
`Designers` → `editor`, `Support` → `integrator`, `Approvers` → `reviewer`,
`Submitters` → `submitter`, `Viewers` → `viewer`). Values without a mapping are
kept unchanged. Tenant roles from every `organization` entry are then appended.

Example: `groups: ["/acme/Administrators", "Designers", "unknown-group"]` plus
`roles: ["editor"]` gives `roles == ["editor", "tenant-admin", "unknown-group"]`.

**`super-admin`** in `roles` is the platform administrator role. It is synced
as the global `super-admin` group, never tenant-qualified. It is honoured
**only from a platform (master realm) issuer**: from any other issuer it is
dropped from `roles` and from every membership's roles and groups at
verification time (`integrations/auth/core/trust.py`), whatever claim carried it.

### Realm identity claims

These decide whether a token is a **platform session**
(`trust_domain == PLATFORM`):

| Claim | Emitted by |
|---|---|
| `m8flow_authentication_identifier` | `RealmInfoMapper` (realm name) |
| `m8flow_realm_name` | `RealmInfoMapper` (realm name) |
| `realm_name` | legacy |
| `m8flow_tenant_name` | legacy last fallback |

A token is a platform session only if the realm segment of the verified `iss`
equals the master realm name. The preceding claims are informational: a token
from another realm that names the master realm in them is **not** a platform
session. Otherwise a token from the shared realm is `SHARED`, and a
token from any other realm is `TENANT`.

A master-realm administrator token looks like:

```json
{
  "iss": "https://kc.example.com/realms/master",
  "sub": "s5",
  "preferred_username": "admin",
  "roles": ["super-admin"],
  "realm_access": { "roles": ["admin"] },
  "m8flow_authentication_identifier": "master"
}
```

→ `roles == ["super-admin", "admin"]`, no memberships, `trust_domain == PLATFORM`.

### Claims m8flow ignores

Everything else (`scope`, `session_state`, `sid`, `resource_access`,
`allowed-origins`, ...) is kept in `jwt_claims` for debugging only.

## The m8flow claim contract v1

An IdP that can run code when it mints a token (a Keycloak protocol mapper, an
Auth0 post-login Action, an Okta inline hook) can emit **one** claim in
m8flow's own shape, so no vendor-specific claim parsing is needed. Enable it
with `M8FLOW_AUTH_CONTRACT_CLAIMS=true`. The claim key defaults to
`https://m8flow.io/claims` (`M8FLOW_AUTH_CONTRACT_CLAIM_KEY`); Auth0 requires a
namespaced key like this.

Schema:
`m8flow-backend/src/m8flow_backend/integrations/auth/core/m8flow-claims.v1.schema.json`.
Golden fixtures for IdP-side tests: `m8flow-backend/tests/fixtures/auth/contract/`.

A contract claim looks like this:

```json
{
  "https://m8flow.io/claims": {
    "v": 1,
    "domain": "shared",
    "active_tenant": { "id": "org_abc123", "alias": "acme", "name": "Acme Inc" },
    "tenants": [
      {
        "tenant": { "id": "org_abc123", "alias": "acme", "name": "Acme Inc" },
        "roles": ["tenant-admin"],
        "groups": ["Administrators"],
        "roles_complete": true
      }
    ],
    "tenants_complete": false,
    "platform_roles": []
  }
}
```

| Field | Required | Meaning |
|---|---|---|
| `v` | yes | Contract version. Only `1` is accepted. |
| `domain` | no | `platform`, `shared` or `tenant`. A hint only: if it disagrees with the trust domain m8flow derives from the issuer, the token is rejected. |
| `active_tenant` | no | The tenant this token was minted for. Becomes `active_tenant_ref`. |
| `tenants[]` | no | Up to 50 grants: `tenant` (`id`/`alias`/`name`, at least one), `roles` (neutral names only), `groups` (lane group names), `roles_complete`. |
| `tenants_complete` | no | `true` only if `tenants` lists every membership the user has. Becomes `memberships_complete`. |
| `platform_roles` | no | Only `super-admin`. **Honoured only from a platform issuer**; silently dropped otherwise. |

Rules m8flow applies to the contract:

- It is read only from a token whose signature and issuer were already verified.
- A malformed claim, an unknown version, or a domain mismatch rejects the token
  (fail closed). A missing claim falls back to the legacy parsing.
- A `tenant`-domain issuer may assert at most one tenant, and only its own:
  the tenant's `alias` must equal the issuer's realm name, or the token is
  rejected. m8flow keeps only that alias (an asserted `id` or `name` is
  ignored), and it becomes the active tenant.
- `roles_complete: true` lets the host skip the directory call for that tenant,
  except where BPMN lanes need `groups` and the grant has none.
- Top-level realm roles (`roles`, `realm_access.roles`) are still read with
  the legacy rules.

The Keycloak mapper does not emit this claim yet. For a new IdP it is the
recommended path: see [Write an auth provider](./writing-a-provider.md#the-shortcut-emit-the-contract-claim).

## Related pages

- [How the auth provider works](./how-it-works.md)
- [Identity provider prerequisites](./prerequisites.md)
