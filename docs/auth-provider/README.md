# Auth provider

m8flow does not authenticate users itself. It delegates sign-in to an external
OpenID Connect identity provider (IdP) and talks to it only through one
pluggable seam, the **auth provider**. Keycloak is the built-in provider.

This folder explains how that seam works and how to extend it.

| Document | Read it when you want to... |
|---|---|
| [How it works](./how-it-works.md) | understand the architecture, the request lifecycle, login, tenant switching and logout |
| [Identity provider prerequisites](./prerequisites.md) | know what an IdP must provide, and how Keycloak must be configured |
| [JWT token shape](./jwt-token-shape.md) | see exactly which token claims m8flow reads, with examples |
| [Write an auth provider](./writing-a-provider.md) | implement your own provider, using multi-tenant Keycloak as the worked example |

## In one paragraph

The browser logs in at the IdP and gets an access token. On every request the
backend verifies that token through the provider (`verify_token`), which turns
the vendor's claims into a neutral `VerifiedClaims` object: who the user is,
which tenants they belong to, and which roles they hold there. The host then
picks the active tenant (the `m8flow_selected_tenant` cookie is authoritative),
syncs the user's tenant-scoped groups into the database, and applies RBAC.
Flows that span several steps (login finalization, tenant switch, logout
cleanup) are owned by `AuthService`, so a provider only states facts about its
IdP and never re-implements a flow.

## Where the code lives

All paths are relative to `m8flow-backend/src/m8flow_backend/`.

| Path | What it is |
|---|---|
| `integrations/auth/base/` | The contract: `AuthProvider`, neutral models (`VerifiedClaims`, `Membership`, `TenantRef`, `TrustDomain`, ...), capability interfaces, errors, role names, and the generic OIDC engine (`base/oidc.py`). |
| `integrations/auth/core/` | Provider-agnostic flows: `AuthService`, switch modes, the membership-authority rule, the opt-in membership cache, and the m8flow claim contract. |
| `integrations/auth/keycloak/` | The Keycloak provider. Only code inside `integrations/auth/` may import it (enforced by ruff `TID251`). |
| `integrations/auth/testing/` | The provider conformance suite and an in-memory reference provider. |
| `integrations/auth/factory.py` | Picks the active provider from `M8FLOW_AUTH_PROVIDER`. |
| `auth/` | Host side: token decoding, request authentication middleware, tenant binding (`bind.py`), active-tenant selection (`resolve.py`). |
| `keycloak-extensions/realm-info-mapper/` (repo root) | The Keycloak protocol mappers that put tenant information into tokens. |

## Rules that always hold

- Host code never imports a vendor package. It calls `get_auth_provider()` and
  `AuthService`.
- The `m8flow_selected_tenant` cookie decides the active tenant. A token's
  tenant claim is a hint, and frontend `localStorage` is never authoritative.
- A token that lists organizations is **not** proof of the user's roles in a
  tenant. Unless the provider marks a membership `roles_complete`, the host
  enriches it from the provider's directory.
- Backend route authorization (`allow_uri` and the dispatcher) is the final
  enforcement layer. Provider capabilities say what the IdP *can* do, never
  what a user *may* do.

## Related pages

- [About multi-tenancy and access control](../explanation/multi-tenancy-and-access.md)
- [Configuration](../reference/configuration.md#keycloak-and-sign-in)
