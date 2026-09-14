# Auth provider seam

This package is the **provider-agnostic auth seam**. The rest of the backend
authenticates users, verifies tokens, and reads/writes the identity directory
*only* through the neutral interface defined here — it never sees a vendor
vocabulary (Keycloak organizations, realm roles, groups, ...) directly.

```
integrations/auth/
├── base/            # the neutral contract (interface + domain objects)
│   ├── provider.py      # AuthProvider (the ABC concrete providers implement)
│   ├── models.py        # neutral domain objects the seam speaks in
│   ├── capabilities.py  # optional capability ABCs
│   ├── roles.py         # canonical neutral role vocabulary
│   ├── errors.py        # neutral error hierarchy raised across the seam
│   └── oidc.py          # spec-defined OIDC engine (OidcClient/OidcAuthProvider) — subclass this for a new OIDC-compliant provider
├── settings.py      # AuthSettings envelope (provider selection + raw env snapshot)
├── factory.py       # register_auth_provider / get_auth_provider
├── testing/         # AuthProviderConformance suite + InMemoryAuthProvider fake — see "Proving a new provider" below
└── keycloak/        # the reference implementation (KeycloakAuthProvider)
```

Call sites resolve the active provider with `get_auth_provider()` and speak only
in `base` terms:

```python
from m8flow_backend.integrations.auth import get_auth_provider

claims = get_auth_provider().verify_token(access_token)
```

## The contract (`base/`)

### `AuthProvider` (`base/provider.py`)

`ABC` with `@abstractmethod` on every required member — a concrete provider
must override all of them to be instantiable at all (enforced at
construction, not at first call). Four groups:

- **Session / OIDC**, keyed by `issuer: IssuerRef` rather than a raw realm
  string (see below): `build_login_url`, `exchange_code`, `refresh`,
  `build_logout_url`
- **Token + directory read:** `verify_token → VerifiedClaims`, `get_user`,
  `search_users`, `list_memberships`, `set_active_tenant`
- **Provider self-description** — small, mostly-static facts a caller needs
  before/without a request in flight: `default_issuer`, `default_tenant_ref`,
  `authorization_endpoint_url`, `default_issuer_claim`. `is_master_issuer` is
  the **one deliberate exception** to the ABC rule — it has a safe concrete
  default (`return False`) rather than `@abstractmethod`, since a plain
  yes/no question with an always-safe default doesn't need capability
  ceremony.
- **Optional capability accessors (properties):** `user_admin`,
  `tenant_admin`, `group_admin`, `role_admin`, `directory_admin` (a
  compatibility aggregate composing all four), and `provisioning`. Each
  raises `CapabilityNotSupported` by default, so callers use the typed
  accessors rather than sniffing with `hasattr`.

### `IssuerRef` (`base/models.py`)

```python
@dataclass(frozen=True)
class IssuerRef:
    value: str
```

Opaque routing hint for session-establishment calls (`build_login_url`,
`exchange_code`, `refresh`, `build_logout_url`, `get_user`, `search_users`).
Only the provider may interpret it — for Keycloak it's a realm name (the
shared realm, a tenant's spoke realm, or the master realm); another provider
might not need it, or might read a different field. **Never derived from
`TenantRef`**: it's often chosen *before* any tenant is known (the
shared-realm login entry point is the default case, not an edge case).
`KeycloakAuthProvider` unwraps `issuer.value` immediately and calls into
`oidc.py`/`directory.py`/`tenants.py`, whose own internal `realm: str`
parameters are unchanged — the rename never leaks past `keycloak/provider.py`.

### Neutral domain objects (`base/models.py`)

Frozen dataclasses that form the contract both sides depend on. A provider must
be able to express its data in exactly these terms, and the backend never needs
to know more than this:

| Object | Purpose |
|--------|---------|
| `TenantRef` | A tenant as a token/provider references it (`id` / `alias` / `name`) — **never** DB-canonicalized here; the backend resolves it to the local canonical row. |
| `Membership` | A user's membership in one tenant, with that tenant's neutral `roles` and `groups`. |
| `VerifiedClaims` | Authoritative result of verifying a token. Everything request-time authz needs — no per-request provider call. Includes `active_tenant_ref` (the finalized/active tenant, distinct from the full `memberships` list) and the verified `jwt_claims` payload. |
| `TokenSet` | Tokens from an authorization-code exchange or refresh. |
| `User` | A neutral directory user. |
| `Tenant` | A neutral tenant as the provider knows it (pre DB-canonicalization). |
| `Role` / `Group` | Neutral role/group identifiers, optionally tenant-scoped (`Group` also carries an optional `path`). |

### Optional capabilities (`base/capabilities.py`)

`ABC`s a provider may support, each with `@abstractmethod` on every member —
same enforced-at-construction idiom as `AuthProvider` itself:

- **`SupportsUserAdmin`** — `create_user`, `delete_user`. Both still take
  `authentication_identifier: str`, not `IssuerRef` — a deliberate scope
  boundary, not an inconsistency: the `IssuerRef` rename was scoped to
  `AuthProvider`'s own port boundary only, not the capability ABCs.
- **`SupportsTenantAdmin`** — tenant CRUD + membership: `get_tenant`,
  `create_tenant`, `update_tenant`, `delete_tenant`, `add_member`,
  `remove_member`, `get_member`, `list_members`.
- **`SupportsGroupAdmin`** — group CRUD + membership + roles:
  `list_groups`, `create_group`, `delete_group`, `rename_group`,
  `add_group_member`, `remove_group_member`, `list_group_members`,
  `list_member_groups`, `set_group_roles`, `roles_for_group`,
  `ensure_default_groups`.
- **`SupportsRoleAdmin`** — `assign_roles`, `remove_roles` (symmetric: removes
  from every candidate group a role maps to, not just the primary one).
- **`SupportsDirectoryAdmin`** — a compatibility aggregate composing all four
  above (no members of its own); call sites that only need "some directory
  admin capability" without caring which narrow slice can keep using it.
- **`SupportsProvisioning`** — tenant-realm and client provisioning
  (Keycloak-heavy; optional on the seam): `create_tenant_realm`,
  `delete_tenant_realm`, `update_tenant_realm`, `ensure_client_redirect_uri`.

Expose them from the `user_admin` / `tenant_admin` / `group_admin` /
`role_admin` / `directory_admin` / `provisioning` properties on your
provider. Callers reach them through those accessors, which raise
`CapabilityNotSupported` when a provider does not implement them — never
`hasattr`-sniff instead. A provider that can't compose all four narrow ABCs
into one aggregate raises `CapabilityNotSupported` from `directory_admin`
while still exposing whichever narrow accessors it does support standalone.

### Roles (`base/roles.py`)

m8flow's own provider-independent role vocabulary. A provider translates between
these names and its realization of them.

- `VALID_TENANT_ROLE_NAMES`: `tenant-admin`, `editor`, `integrator`, `reviewer`,
  `submitter`, `viewer`
- `SUPER_ADMIN_ROLE`: `super-admin` (global, non-tenant-scoped)
- Helpers: `normalize_tenant_role_name`, `normalize_tenant_role_names`

### Errors (`base/errors.py`)

Providers raise only these; no HTTP status codes or provider-native payloads
leak past the seam. The backend maps them to its own `ApiError` responses.

`AuthProviderError` (base) → `TokenInvalid`, `UserNotFound`, `TenantNotFound`,
`CapabilityNotSupported`, `ProviderUnavailable`.

## Selecting a provider (`factory.py`)

The process holds one provider instance (lazy singleton).

- Selection key: **`M8FLOW_AUTH_PROVIDER`** env var (default `keycloak`).
- `register_auth_provider(name, factory)` registers (or replaces) a provider
  factory under `name`. `factory` is `Callable[[AuthSettings], AuthProvider]`
  — it receives the neutral `AuthSettings` envelope (`integrations/auth/settings.py`:
  `provider` selection key + `raw`, a `dict` snapshot of the environment) and
  converts it into its own typed settings before constructing.
- `get_auth_provider()` keeps its zero-arg signature — it builds
  `AuthSettings.from_env()` internally before invoking the registered
  factory, so none of the ~20+ existing call sites change.
- `reset_auth_provider()` drops the cached instance (used by tests) and also
  clears Keycloak's process-global settings cache so a rebuilt provider can
  `configure()` cleanly.

Keycloak settings (`keycloak/settings.py`) are **process-global
single-active-config**, not per-provider-instance. Helpers read
`current_settings()`; constructing `KeycloakAuthProvider` with a second,
different `KeycloakSettings` raises until `reset_keycloak_settings()` (or
`reset_auth_provider()`) runs. Prefer `get_auth_provider()`.

Keycloak is auto-registered as a builtin in `factory._ensure_builtins`, which
converts the envelope into `KeycloakSettings.from_env(settings.raw)` before
constructing `KeycloakAuthProvider`.

## Authoring a new provider

Use `keycloak/` as the worked reference: `KeycloakAuthProvider` subclasses
`AuthProvider` and delegates each method to focused helper modules (`oidc`,
`directory`, `groups`, `tenants`, `jwks`, `provisioning`, ...), keeping the
provider class a thin translation layer.

1. **Subclass `AuthProvider`** and implement every abstract method — the
   session/verify/directory-read group plus the self-description group
   (`default_issuer`, `default_tenant_ref`, `authorization_endpoint_url`,
   `default_issuer_claim`; `is_master_issuer` already has a safe default and
   only needs overriding if your provider has a real master/root issuer
   concept). Session methods take `issuer: IssuerRef` — your provider decides
   what its `value` means (Keycloak: a realm name). Accept and return only
   `base.models` objects, and raise only `base.errors`. Keep vendor
   vocabulary inside your provider package. Because `AuthProvider` is an
   `ABC`, a subclass missing any abstract method fails at construction, not
   at first call.

   **If your provider speaks standard OIDC** (most will), don't implement the
   session/verify group from scratch — subclass `base/oidc.py`'s
   `OidcAuthProvider` instead. It already owns discovery/JWKS caching, RS256
   verification, and the authorization-code/refresh grants (RFC 6749 / RFC
   7517 / OIDC Core), the same spec every OIDC-compliant IdP implements; you
   only implement `OidcClient`'s hooks (`discovery_url`, `token_url`,
   `authorization_endpoint`, `logout_endpoint`, `realm_from_issuer`,
   `issuer_is_allowed`, `audience_is_allowed`, `client_id`,
   `client_auth_params` — `internalize_url` has a no-op default, override
   only if you have a public/internal URL split like Keycloak's Docker
   networking) plus `OidcAuthProvider.map_claims`. `keycloak/oidc.py` is the
   worked example: it shrinks to realm-URL templating plus Keycloak's own
   issuer/audience rules on top of this base.
2. **Optional capabilities:** if your provider mutates the directory or
   provisions tenants, implement whichever of `SupportsUserAdmin` /
   `SupportsTenantAdmin` / `SupportsGroupAdmin` / `SupportsRoleAdmin` /
   `SupportsProvisioning` it supports (one class can inherit several, or all
   four narrow directory ABCs at once to also satisfy
   `SupportsDirectoryAdmin`) and return them from the corresponding
   `user_admin` / `tenant_admin` / `group_admin` / `role_admin` /
   `directory_admin` / `provisioning` properties.
3. **Register a factory** — it now takes the neutral `AuthSettings` envelope,
   not zero args, so it can build its own typed settings from `settings.raw`
   without `factory.py` needing to know your provider's env var names:

   ```python
   from m8flow_backend.integrations.auth import register_auth_provider
   from m8flow_backend.integrations.auth.settings import AuthSettings
   from myorg.auth import MyAuthProvider, MySettings

   def _build_myprovider(settings: AuthSettings) -> MyAuthProvider:
       return MyAuthProvider(MySettings.from_env(settings.raw))

   register_auth_provider("myprovider", _build_myprovider)
   ```

4. **Select it** at runtime with `M8FLOW_AUTH_PROVIDER=myprovider`. All call
   sites continue to use `get_auth_provider()` unchanged.

### Proving a new provider: the conformance suite

`testing/conformance.py`'s `AuthProviderConformance` is the acceptance bar, not
a suggestion — it is a subclassable pytest suite asserting the `AuthProvider`
*contract*, never any one provider's internals; a reviewer should be able to
read every `test_*` method without knowing what a Keycloak realm is. Subclass
it, override only the hooks above its "override above the divider, never
below it" marker (how to mint a token, how to register a test user, ...), and
leave every `test_*` method untouched. Both `InMemoryAuthProvider`
(`testing/fake.py`, via `test_fake_conformance.py`) and `KeycloakAuthProvider`
(via `test_keycloak_conformance.py`) run the identical suite — that is the
forcing function: an abstraction with only one implementation has no way to
notice it's leaking, which is how this package's original Keycloak-only
bypasses accumulated unseen. Where your provider's own shape genuinely can't
exercise a clause (no vendor-role-leaf translation to demonstrate, no network
dependency capable of being unavailable), its hook opts out with
`pytest.skip` rather than the suite quietly weakening the assertion for every
provider.

### Rules to preserve

- The backend depends on the neutral contract, not your vendor. Do not leak
  vendor types, HTTP status codes, or native payloads past the seam.
- `TenantRef` is a raw reference — resolving it to the local canonical tenant row
  is the backend's job, not the provider's.
- `VerifiedClaims` must be built only from a cryptographically verified token; it
  is treated as authoritative for request-time authorization.
- Callers must not `hasattr`-sniff capabilities — always go through the typed
  accessors.
