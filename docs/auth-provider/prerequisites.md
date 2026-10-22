# Identity provider prerequisites

This page lists what any identity provider (IdP) must offer, then the exact
Keycloak setup m8flow ships with, then the related environment variables.

## What any identity provider must provide

| Requirement | Why |
|---|---|
| **OpenID Connect** with a discovery document (`/.well-known/openid-configuration`) and a `jwks_uri` | `base/oidc.py` fetches signing keys from discovery and caches them for 10 minutes. |
| **Authorization-code flow** with a confidential client (client id + secret, or a private-key JWT) | `/v1.0/login` and `/v1.0/login_return`. |
| **Refresh tokens** | `/v1.0/refresh`, and the `REMINT` tenant switch. |
| **RS256-signed JWT access tokens** | Only `RS256` is accepted (`SUPPORTED_ALGS`). Opaque or encrypted access tokens are rejected. |
| **Required claims `sub`, `iss`, `exp`** | Verification fails without them. |
| **An audience the backend can check** (`azp` or `aud` naming the client) | See [JWT token shape](./jwt-token-shape.md#standard-claims). |
| **RP-initiated logout** (`end_session_endpoint`) | `/v1.0/logout`. |
| **A user identifier** in `preferred_username` (or `username`) | Directory lookups and local user rows use it. |
| **A way to express tenants** in the token, or a directory API that lists a user's tenants | Multi-tenancy. With Keycloak this is Organizations plus the m8flow mapper. |
| **A directory/admin API** (optional) | Needed only for tenant management features: inviting users, assigning roles, creating tenants. |

## Keycloak setup (the built-in provider)

The Docker image and scripts in the following sections do all of this for you. Use this list to
check a custom or managed Keycloak.

### Version and extension

- **Keycloak 26.x** (the mappers are built and tested against 26.6.1, Java 17).
- The m8flow mapper JAR from `keycloak-extensions/realm-info-mapper/` must be
  installed at `/opt/keycloak/providers/realm-info-mapper.jar`.
  `docker/m8flow.keycloak.Dockerfile` builds and installs it; for a local
  Keycloak, run `./build.sh` in that folder and restart Keycloak.

The JAR adds three protocol mappers:

| Mapper id | Adds to tokens |
|---|---|
| `oidc-realm-info-mapper` | Realm identity (`m8flow_authentication_identifier`, `m8flow_realm_name`, `m8flow_realm_id`) and the **active organization** (`m8flow_tenant_id`, `m8flow_tenant_alias`, `m8flow_tenant_name`, and a one-entry `organization` claim). |
| `oidc-normalized-organization-membership-mapper` | Rewrites the `organization` claim's `groups` entries without leading `/`. |
| `oidc-normalized-group-membership-mapper` | A `groups` claim with group paths without leading `/`. |

### Realms

| Realm | Env var (default) | Purpose |
|---|---|---|
| Shared realm | `M8FLOW_KEYCLOAK_SHARED_REALM` (`m8flow`) | All tenant users. **Organizations must be enabled** (`organizationsEnabled=true`). Each organization is one m8flow tenant; the organization id is the tenant id. |
| Master realm | `M8FLOW_KEYCLOAK_MASTER_REALM` (`master`) | Platform administrators. Tokens from it are platform sessions. |

The shared realm is imported from
`m8flow-backend/keycloak/realm_exports/m8flow-tenant-template.json` by
`docker/keycloak-entrypoint.sh`. The entrypoint replaces the client id and
redirect URIs, and `docker/keycloak-init-realms.sh` reconciles the rest.

### Client

A confidential client in the shared realm, id `M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID`
(default `m8flow-backend`), with:

- standard (authorization-code) flow enabled;
- a redirect URI for the backend's `/v1.0/login_return`;
- these mappers on the client:
  - `oidc-realm-info-mapper` (access token and ID token);
  - `oidc-usermodel-realm-role-mapper` with claim `roles` (multivalued);
- the realm's default `roles` scope (claim `realm_access.roles`);
- the `organization` client scope (added by `keycloak-init-realms.sh`) with the
  organization-membership, organization-group-membership and normalized
  organization mappers.

### Organization groups and roles

Each organization gets the default groups in the following table. A group name maps to one
neutral tenant role (`integrations/auth/keycloak/role_mapping.py`):

| Organization group | Tenant role |
|---|---|
| `Administrators` | `tenant-admin` |
| `Designers` | `editor` |
| `Support` | `integrator` |
| `Approvers` | `reviewer` |
| `Submitters` | `submitter` |
| `Viewers` | `viewer` |

Custom groups can carry the attributes `m8flow_role_names` and
`m8flow_role_mapping_configured`; see
[Multi-tenancy and access control](../explanation/multi-tenancy-and-access.md#roles).

### The active-tenant user attribute

`RealmInfoMapper` reads the user attribute **`m8flow_active_tenant`** (an
organization id or alias) to decide which organization the token is for. The
backend writes it through the Admin API when the user switches tenant, then
refreshes the token. The mapper only honours it if the user is a member of
that organization. The attribute must be writable through the Admin API: if
your realm's user profile drops unmanaged attributes, either declare
`m8flow_active_tenant` in the user profile or allow unmanaged attributes for
administrators. Check this by switching tenant and confirming the new token's
`m8flow_tenant_id` changes.

### Backend access to the Admin API

The backend calls the Admin API for directory lookups (thin-token enrichment,
the tenant switcher list), the active-tenant attribute, and tenant management.
It gets an admin token from the master realm with a username and password:
`KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD` (or the `M8FLOW_KEYCLOAK_`
variants). That account needs rights to manage users, organizations and groups
in the shared realm.

### Login page

Both realms must keep the **single-page username and password** login form
(`Username Password Form`). Do not switch to a username-first or
identity-first flow. See `AGENTS.md`, section "Keycloak Login UX".

## Environment variables

Full list: [Configuration](../reference/configuration.md). The ones the auth seam reads:

| Variable | Default | Purpose |
|---|---|---|
| `M8FLOW_AUTH_PROVIDER` | `keycloak` | Which registered provider to use. |
| `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL` | `http://localhost:6842` | Back-channel URL the backend uses (discovery, JWKS, token endpoint, Admin API). |
| `KEYCLOAK_HOSTNAME` / `M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE` | `KEYCLOAK_URL` | Public base URL. It must match the `iss` claim Keycloak puts in tokens. |
| `M8FLOW_KEYCLOAK_SHARED_REALM` | `m8flow` | Shared realm. |
| `M8FLOW_KEYCLOAK_MASTER_REALM` | `master` | Platform realm. |
| `M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS` / `_NAME` | shared realm name | Default tenant (first-login fallback). |
| `M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID` | `m8flow-backend` | OIDC client id (also the accepted audience). |
| `M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET` / `M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET` | none | Client secret. Required outside unit tests. |
| `M8FLOW_TENANT_CLAIM` | `m8flow_tenant_id` | Raw claim name used as a last-resort token tenant. |
| `FLASK_SESSION_SECRET_KEY` | none | Signs m8flow's local HS256 tokens. Required outside unit tests. |
| `M8FLOW_BACKEND_SESSION_COOKIE_SECURE` | on, except in local/test envs | `Secure` flag on auth cookies. |

## Opt-in switches

All of these are **off by default**, so existing behaviour is unchanged until
you turn them on.

| Variable | Effect | Recommendation |
|---|---|---|
| `M8FLOW_AUTH_STRICT_ISSUERS=true` | Trust only the shared realm, the master realm and `M8FLOW_KEYCLOAK_TRUSTED_REALMS` (comma list), and reject tokens that name neither `aud` nor `azp`. Without it, **any realm on the configured Keycloak host is trusted**. | Turn on in production once you've confirmed no other realm needs access. |
| `M8FLOW_AUTH_MEMBERSHIP_CACHE_TTL_SECONDS=<n>` | Cache directory membership lookups for up to `n` seconds (max 60). The cache is per process; membership changes made through m8flow invalidate it on the worker that made them, other workers catch up within `n` seconds. Login finalization and tenant switch always bypass it. Entries are keyed by token issuer + username, so the same username in different realms never shares an entry; lookups with no issuer are not cached. A role removed directly in Keycloak is visible after at most `n` seconds. | 30–60 if the per-request Admin API calls are a measurable cost. |
| `M8FLOW_AUTH_CONTRACT_CLAIMS=true` | Read the versioned m8flow claim (key `M8FLOW_AUTH_CONTRACT_CLAIM_KEY`, default `https://m8flow.io/claims`) instead of the legacy Keycloak claim parsing. See [JWT token shape](./jwt-token-shape.md#the-m8flow-claim-contract-v1). | Only once your IdP emits the claim. The Keycloak mapper does not emit it yet. |

## Checking a setup

1. Sign in as a non-admin user (for example `editor`) and decode the access
   token (for example with `jwt.io` on a non-production token). Check the
   claims against [JWT token shape](./jwt-token-shape.md#a-real-shared-realm-token).
2. Call `GET /v1.0/m8flow/session`. You should see `trust_domain: "shared"` and
   the expected `token_active_tenant`.
3. Call `GET /v1.0/onboarding` and `GET /v1.0/tasks` as that user. Both must
   succeed.
4. Add the user to a second organization, switch to it in the UI, and repeat
   step 3.
5. Sign in on the platform admin page (master realm) and check
   `is_platform_session: true` on `/v1.0/m8flow/session`.

## Related pages

- [JWT token shape](./jwt-token-shape.md)
- [Write an auth provider](./writing-a-provider.md)
