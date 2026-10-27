# Write an auth provider

This guide builds a provider step by step, using **multi-tenant Keycloak** as
the example: one shared realm where each Keycloak **Organization** is an
m8flow tenant, plus the master realm for platform administrators. That is the
setup m8flow ships with, so you can compare every step with the built-in
provider in `integrations/auth/keycloak/`.

The example is deliberately self-contained (about 200 lines, plain `requests`
calls) so the shape stays visible. The code from [Settings](#settings) through
[The directory and the provider](#the-directory-and-the-provider) was assembled
into a package and smoke-tested against this repo's auth seam (login URL, claim
mapping, issuer trust, directory memberships, tenant switch through
`AuthService`). For production Keycloak use the built-in
provider; use this guide when you add a different IdP or a different Keycloak
topology. [Variant: Keycloak with a realm per tenant](#variant-keycloak-with-a-realm-per-tenant)
covers the realm-per-tenant variant.

Paths are relative to `m8flow-backend/src/m8flow_backend/`.

> Read [How it works](./how-it-works.md) and [JWT token shape](./jwt-token-shape.md)
> first. They define the terms used here.

## Answer four questions first

Every design decision on this page follows from these answers.

| Question | Multi-tenant Keycloak (Organizations) |
|---|---|
| **Which issuers do you trust, and what kind is each?** | Shared realm `m8flow` → `SHARED` (many tenants). Master realm → `PLATFORM`. |
| **How does a token say which tenant it is for, and which roles the user has there?** | `RealmInfoMapper` emits `m8flow_tenant_id`/`m8flow_tenant_alias` and a one-entry `organization` claim. Roles are *not* in the token (the mapper cannot read organization groups), so memberships are incomplete. |
| **How does a token come to carry a different tenant?** | Write the `m8flow_active_tenant` user attribute, then refresh: `SwitchMode.REMINT`. |
| **Where is the full list of a user's tenants and roles?** | The Keycloak Admin API: the user's organizations, and their groups in each organization. |

If your IdP can put complete, neutral tenant roles into the token, you can skip
most of [The OIDC client](#the-oidc-client) and [Mapping claims](#mapping-claims).
See [The shortcut: emit the contract claim](#the-shortcut-emit-the-contract-claim).

## Package layout and rules

The example provider uses the following package layout:

```text
integrations/auth/example_keycloak/
├── __init__.py
├── settings.py      # typed settings, built from AuthSettings.raw
├── oidc.py          # OidcClient subclass: URLs, issuer + audience rules, client auth
├── directory.py     # Admin API calls (user lookup, memberships, attribute writes)
└── provider.py      # the AuthProvider subclass
```

Rules (enforced by review, and by ruff `TID251` for the built-in package):

- Only code inside `integrations/auth/` may import your package. Host code
  goes through `get_auth_provider()` and `AuthService`.
- Accept and return only `base.models` types; raise only `base.errors` types
  (`TokenInvalid`, `UserNotFound`, `TenantNotFound`, `ProviderUnavailable`,
  `CapabilityNotSupported`).
- Read configuration once, into a settings object held **on the instance**.
  Don't read `os.environ` inside methods.
- Never decide the active tenant, set cookies, or write the database. Return
  facts; the host and `AuthService` decide.

## Settings

The settings module reads the provider's configuration from the environment:

```python
# integrations/auth/example_keycloak/settings.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleKeycloakSettings:
    internal_base: str          # back-channel URL, e.g. http://keycloak:8080
    public_base: str            # must match the "iss" Keycloak puts in tokens
    shared_realm: str
    master_realm: str
    client_id: str
    client_secret: str
    default_org_alias: str
    admin_client_id: str        # service-account client with realm-management roles
    admin_client_secret: str

    @classmethod
    def from_raw(cls, raw: Mapping[str, str]) -> ExampleKeycloakSettings:
        def get(key: str, default: str = "") -> str:
            return (raw.get(key) or default).strip()

        internal = get("EXAMPLE_KC_URL", "http://localhost:6842").rstrip("/")
        shared = get("EXAMPLE_KC_SHARED_REALM", "m8flow")
        return cls(
            internal_base=internal,
            public_base=get("EXAMPLE_KC_PUBLIC_URL", internal).rstrip("/"),
            shared_realm=shared,
            master_realm=get("EXAMPLE_KC_MASTER_REALM", "master"),
            client_id=get("EXAMPLE_KC_CLIENT_ID", "m8flow-backend"),
            client_secret=get("EXAMPLE_KC_CLIENT_SECRET"),
            default_org_alias=get("EXAMPLE_KC_DEFAULT_ORG", shared),
            admin_client_id=get("EXAMPLE_KC_ADMIN_CLIENT_ID"),
            admin_client_secret=get("EXAMPLE_KC_ADMIN_CLIENT_SECRET"),
        )
```

The factory receives an `AuthSettings` envelope whose `raw` field is a snapshot
of the environment; your settings class is the only place that interprets it.

## The OIDC client

`base/oidc.py::OidcClient` already implements discovery, JWKS caching, RS256
verification, and the authorization-code and refresh grants. You only fill in
the hooks. Keycloak's routing key (the `realm` argument everywhere) is the
realm name, which is also what `IssuerRef.value` carries. The client looks like
this:

```python
# integrations/auth/example_keycloak/oidc.py
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from m8flow_backend.integrations.auth.base.oidc import OidcClient
from m8flow_backend.integrations.auth.example_keycloak.settings import ExampleKeycloakSettings


class ExampleKeycloakOidcClient(OidcClient):
    def __init__(self, settings: ExampleKeycloakSettings) -> None:
        super().__init__()
        self._s = settings

    # --- URLs: back-channel calls use the internal base, browser URLs the public one
    def discovery_url(self, realm: str) -> str:
        return f"{self._s.internal_base}/realms/{realm}/.well-known/openid-configuration"

    def token_url(self, realm: str) -> str:
        return f"{self._s.internal_base}/realms/{realm}/protocol/openid-connect/token"

    def authorization_endpoint(self, realm: str) -> str:
        return f"{self._s.public_base}/realms/{realm}/protocol/openid-connect/auth"

    def logout_endpoint(self, realm: str) -> str:
        return f"{self._s.public_base}/realms/{realm}/protocol/openid-connect/logout"

    def internalize_url(self, url: str) -> str:
        # Discovery returns public URLs (jwks_uri); fetch them via the internal base.
        if url.startswith(self._s.public_base):
            return self._s.internal_base + url[len(self._s.public_base):]
        return url

    # --- trust: an explicit allow-list, checked before any key is fetched
    def realm_from_issuer(self, issuer: str) -> str | None:
        parts = [p for p in urlparse(issuer).path.split("/") if p]
        return parts[1] if len(parts) >= 2 and parts[0] == "realms" else None

    def issuer_is_allowed(self, issuer: str, *, realm: str) -> bool:
        if realm not in {self._s.shared_realm, self._s.master_realm}:
            return False
        allowed = {f"{base}/realms/{realm}" for base in (self._s.public_base, self._s.internal_base)}
        return issuer.rstrip("/") in allowed

    def audience_is_allowed(self, payload: dict[str, Any]) -> bool:
        aud = payload.get("aud")
        audiences = set(aud) if isinstance(aud, list) else {aud}
        return payload.get("azp") == self._s.client_id or self._s.client_id in audiences

    # --- client authentication for the token endpoint (client_secret_post)
    def client_id(self) -> str:
        return self._s.client_id

    def client_auth_params(self) -> dict[str, str]:
        return {"client_id": self._s.client_id, "client_secret": self._s.client_secret}
```

Two optional hooks exist for IdPs that need them: `scopes()` (default
`openid email profile`) and `extra_authorize_params(realm)` (for example
Auth0's `audience` and `organization`).

Note the trust rules: this example is stricter than the built-in provider's
default (the equivalent of `M8FLOW_AUTH_STRICT_ISSUERS=true`). Start strict.

## Mapping claims

`map_claims(payload)` turns a verified payload into `VerifiedClaims`. Rules:

- Raise `ValueError` for a payload you can't map; `OidcAuthProvider` turns it
  into `TokenInvalid`.
- Put only **neutral** role names into roles; translate vendor names here.
- Set `roles_complete` / `memberships_complete` to `True` **only** if the
  token really is complete. When unsure, leave them `False`: the host will
  enrich from your directory, which is slower but safe.
- Set `trust_domain` from your own issuer configuration, never from a claim.

The following `map_claims` applies these rules:

```python
# part of integrations/auth/example_keycloak/provider.py
# (imports are in the module header shown in "The provider class")
GROUP_TO_ROLE = {
    "Administrators": "tenant-admin", "Designers": "editor", "Support": "integrator",
    "Approvers": "reviewer", "Submitters": "submitter", "Viewers": "viewer",
}


def _leaf(value: str) -> str:
    return value.strip().strip("/").split("/")[-1].strip()


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def map_keycloak_claims(payload: dict, *, trust_domain: TrustDomain, realm: str | None) -> VerifiedClaims:
    subject, issuer = _text(payload.get("sub")), _text(payload.get("iss"))
    if not subject or not issuer:
        raise ValueError("Verified payload is missing sub or iss")

    # Top-level roles: "super-admin" lives here. Translate org-group names.
    raw_roles = [*payload.get("roles", []), *payload.get("realm_access", {}).get("roles", [])]
    roles = list(dict.fromkeys(GROUP_TO_ROLE.get(_leaf(r), _leaf(r)) for r in raw_roles if isinstance(r, str)))

    # The mapper's one-entry organization claim: {"<alias>": {"id": ..., "name": ...}}
    memberships = [
        Membership(tenant_ref=TenantRef(id=_text(d.get("id")), alias=alias, name=_text(d.get("name"))))
        for alias, d in (payload.get("organization") or {}).items()
        if isinstance(d, dict)
    ]  # roles unknown here -> roles_complete stays False -> the host enriches

    tenant_id, tenant_alias = _text(payload.get("m8flow_tenant_id")), _text(payload.get("m8flow_tenant_alias"))
    active = TenantRef(id=tenant_id, alias=tenant_alias) if (tenant_id or tenant_alias) else None

    return VerifiedClaims(
        subject=subject,
        issuer=issuer,
        username=_text(payload.get("preferred_username")),
        email=_text(payload.get("email")),
        roles=roles,
        memberships=memberships,
        active_tenant_ref=active,
        jwt_claims=dict(payload),
        issuer_key=realm,
        trust_domain=trust_domain,
        memberships_complete=False,  # the mapper emits only the active organization
    )
```

The built-in `keycloak/claims.py` also accepts two older `organization` shapes
and organization `groups`; add that only if your tokens need it.

## The directory and the provider

### Directory calls

The host needs three things from the Admin API: look up a user, list their
organizations with groups (thin-token enrichment and the tenant switcher), and
write the active-tenant attribute (tenant switch). The directory module looks
like this:

```python
# integrations/auth/example_keycloak/directory.py
from __future__ import annotations

import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, UserNotFound
from m8flow_backend.integrations.auth.example_keycloak.settings import ExampleKeycloakSettings

_TIMEOUT = 10


class ExampleKeycloakDirectory:
    def __init__(self, settings: ExampleKeycloakSettings) -> None:
        self._s = settings

    def _admin_headers(self) -> dict[str, str]:
        response = self._call("post", f"{self._s.internal_base}/realms/{self._s.shared_realm}"
                              "/protocol/openid-connect/token", data={
            "grant_type": "client_credentials",
            "client_id": self._s.admin_client_id,
            "client_secret": self._s.admin_client_secret,
        })
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _call(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = requests.request(method, url, timeout=_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Keycloak request failed: {method.upper()} {url}") from exc
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Keycloak returned {response.status_code}")
        return response

    def _admin(self, method: str, *segments: str, **kwargs) -> requests.Response:
        url = "/".join([f"{self._s.internal_base}/admin/realms/{self._s.shared_realm}", *segments])
        return self._call(method, url, headers=self._admin_headers(), **kwargs)

    def find_user(self, username: str) -> dict:
        users = self._admin("get", "users", params={"username": username, "exact": "true"}).json()
        match = next((u for u in users if u.get("username") == username), None)
        if match is None:
            raise UserNotFound(username)
        return match

    def organizations_with_groups(self, username: str) -> list[tuple[dict, list[str]]]:
        user_id = self.find_user(username)["id"]
        # Keycloak 26: a user's organizations live under organizations/members/{id}/organizations
        orgs = self._admin("get", "organizations", "members", user_id, "organizations").json()
        result = []
        for org in orgs:
            groups = self._admin("get", "organizations", org["id"], "members", user_id, "groups",
                                 params={"briefRepresentation": "true"}).json()
            result.append((org, [g["name"] for g in groups if g.get("name")]))
        return result

    def set_attribute(self, username: str, name: str, value: str | None) -> None:
        user = self.find_user(username)
        attributes = dict(user.get("attributes") or {})
        if value:
            attributes[name] = [value]
        else:
            attributes.pop(name, None)
        self._admin("put", "users", user["id"], json={**user, "attributes": attributes})
```

### The provider class

The provider class ties the client and the directory together:

```python
# integrations/auth/example_keycloak/provider.py (continued)
from __future__ import annotations

from typing import Any

from m8flow_backend.integrations.auth.base.errors import UserNotFound
from m8flow_backend.integrations.auth.base.models import (
    IssuerRef, Membership, TenantRef, TrustDomain, User, VerifiedClaims,
)
from m8flow_backend.integrations.auth.base.oidc import OidcAuthProvider
from m8flow_backend.integrations.auth.core import SwitchMode
from m8flow_backend.integrations.auth.example_keycloak.directory import ExampleKeycloakDirectory
from m8flow_backend.integrations.auth.example_keycloak.oidc import ExampleKeycloakOidcClient
from m8flow_backend.integrations.auth.example_keycloak.settings import ExampleKeycloakSettings

ACTIVE_TENANT_ATTRIBUTE = "m8flow_active_tenant"  # read by RealmInfoMapper


class ExampleKeycloakOrgsProvider(OidcAuthProvider):
    def __init__(self, settings: ExampleKeycloakSettings) -> None:
        self._s = settings
        self._client = ExampleKeycloakOidcClient(settings)
        self._directory = ExampleKeycloakDirectory(settings)
        super().__init__(self._client)

    # --- topology facts consumed by AuthService --------------------------
    @property
    def switch_mode(self) -> SwitchMode:
        return SwitchMode.REMINT                     # attribute write + refresh

    def trust_domain(self, claims: VerifiedClaims) -> TrustDomain:
        realm = self._client.realm_from_issuer(claims.issuer)
        return TrustDomain.PLATFORM if realm == self._s.master_realm else TrustDomain.SHARED

    def is_master_issuer(self, claims: VerifiedClaims) -> bool:
        return self.trust_domain(claims) is TrustDomain.PLATFORM

    # --- verification ------------------------------------------------------
    def map_claims(self, payload: dict[str, Any]) -> VerifiedClaims:
        realm = self._client.realm_from_issuer(str(payload.get("iss") or ""))
        domain = TrustDomain.PLATFORM if realm == self._s.master_realm else TrustDomain.SHARED
        return map_keycloak_claims(payload, trust_domain=domain, realm=realm)

    # --- directory reads ---------------------------------------------------
    def get_user(self, *, username: str, issuer: IssuerRef) -> User:
        raw = self._directory.find_user(username)
        return User(subject=raw["id"], username=raw.get("username"), email=raw.get("email"))

    def search_users(self, *, query: str, issuer: IssuerRef, limit: int = 50, offset: int = 0) -> list[User]:
        raw = self._directory._admin("get", "users", params={"search": query, "first": offset, "max": limit}).json()
        return [User(subject=u["id"], username=u.get("username"), email=u.get("email")) for u in raw]

    def list_memberships(self, *, username: str) -> list[Membership]:
        memberships = []
        for org, group_names in self._directory.organizations_with_groups(username):
            leaves = [_leaf(name) for name in group_names]
            memberships.append(Membership(
                tenant_ref=TenantRef(id=org["id"], alias=org.get("alias"), name=org.get("name")),
                roles=list(dict.fromkeys(GROUP_TO_ROLE[g] for g in leaves if g in GROUP_TO_ROLE)),
                groups=leaves,
                roles_complete=True,   # read straight from the directory
            ))
        return memberships

    # --- active tenant (REMINT) ---------------------------------------------
    def set_active_tenant(self, *, username: str, tenant_id: str) -> None:
        self._directory.set_attribute(username, ACTIVE_TENANT_ATTRIBUTE, tenant_id)

    def clear_active_tenant(self, *, username: str) -> None:
        self._directory.set_attribute(username, ACTIVE_TENANT_ATTRIBUTE, None)

    # --- self-description ---------------------------------------------------
    def default_issuer(self) -> IssuerRef:
        return IssuerRef(value=self._s.shared_realm)

    def default_tenant_ref(self) -> TenantRef:
        return TenantRef(alias=self._s.default_org_alias, name=self._s.default_org_alias)

    def authorization_endpoint_url(self, issuer: IssuerRef) -> str:
        return self._client.authorization_endpoint(issuer.value)

    def default_issuer_claim(self) -> str:
        return f"{self._s.public_base}/realms/{self._s.shared_realm}"
```

What you got for free, without writing it:

- Login, code exchange, refresh, logout URLs, JWKS caching and signature
  checks (`OidcAuthProvider`, `OidcClient`).
- Tenant switching, including graceful degradation when the refresh fails
  (`AuthService.switch_tenant`, because `switch_mode` is `REMINT`).
- Thin-token enrichment with the AGENTS.md multi-organization rules, and the
  optional cache (`core/membership.py`, `AuthService.directory_memberships`).
- Platform-session detection for tenant binding (`AuthService.is_platform_session`).
- The tenant switcher list (`AuthService.memberships_for_switcher`) and the
  neutral `/v1.0/m8flow/session` endpoint.

### Admin capabilities (optional)

The tenant-management UI (invitations, roles, groups, creating tenants) uses
the capability accessors `user_admin`, `tenant_admin`, `group_admin`,
`role_admin`, `directory_admin` and `provisioning`. By default they raise
`CapabilityNotSupported`, and `AuthService.capabilities()` reports them as
`false`. To support them, return an object implementing the matching interface
from `base/capabilities.py`. The built-in `keycloak/provider.py::_KeycloakDirectoryAdmin`
implements all of them over the Organizations Admin API.

## The shortcut: emit the contract claim

If your IdP can run code when it mints tokens, have it emit the
[m8flow claim contract](./jwt-token-shape.md#the-m8flow-claim-contract-v1)
with neutral role names and honest completeness flags. Then `map_claims`
shrinks to the standard claims plus one call:

```python
from dataclasses import replace

from m8flow_backend.integrations.auth.core.contract import parse_contract_claim


def map_claims(self, payload):
    claims = map_keycloak_claims(payload, trust_domain=domain, realm=realm)   # sub, iss, username, roles
    contract = parse_contract_claim(payload, trust_domain=domain)           # None if the claim is absent
    if contract is None:
        return claims
    return replace(
        claims,
        memberships=contract.memberships,
        memberships_complete=contract.memberships_complete,
        active_tenant_ref=contract.active_tenant_ref,
        roles=list(dict.fromkeys([*claims.roles, *contract.platform_roles])),
    )
```

When a grant has `roles_complete: true` (and `groups` if you use BPMN lanes),
the host stops calling your directory on every request. Test your IdP-side code
against the fixtures in `m8flow-backend/tests/fixtures/auth/contract/`.

The built-in Keycloak provider does this when `M8FLOW_AUTH_CONTRACT_CLAIMS=true`.

## Variant: Keycloak with a realm per tenant

Here each tenant has its own realm instead of an organization. What changes:

| Concern | Organizations (preceding sections) | Realm per tenant |
|---|---|---|
| Trusted issuers | Shared realm + master | Master + every realm that maps to a live tenant row. Look this up from the database through an injected tenant lookup, **before** fetching keys. |
| `trust_domain` | `SHARED` / `PLATFORM` | `TENANT` for tenant realms, `PLATFORM` for master. |
| Active tenant | `m8flow_tenant_*` claims | The issuer's realm *is* the tenant: set `active_tenant_ref` from it. |
| Token completeness | Incomplete (enrich from directory) | Realm roles and groups are readable by mappers, so the token can be complete: set `roles_complete=True` and `memberships_complete=True` for the single membership. |
| `default_issuer` | Shared realm | None is meaningful: login needs a tenant first (a tenant picker before login). |
| `switch_mode` | `REMINT` | `REAUTHENTICATE`: log in again at the other realm. |
| Directory | Organization members and groups | Realm users and groups. |
| Provisioning | Create an organization | Create a realm from `keycloak/realm_exports/m8flow-tenant-template.json` (`keycloak/provisioning.py` already has this logic). |

The changed pieces, as a sketch:

```python
from dataclasses import replace

from m8flow_backend.integrations.auth.base.roles import VALID_TENANT_ROLE_NAMES


class ExampleKeycloakRealmPerTenantProvider(ExampleKeycloakOrgsProvider):
    @property
    def switch_mode(self) -> SwitchMode:
        return SwitchMode.REAUTHENTICATE

    def trust_domain(self, claims: VerifiedClaims) -> TrustDomain:
        realm = self._client.realm_from_issuer(claims.issuer)
        return TrustDomain.PLATFORM if realm == self._s.master_realm else TrustDomain.TENANT

    def map_claims(self, payload):
        claims = super().map_claims(payload)
        if claims.trust_domain is TrustDomain.PLATFORM:
            return claims
        tenant = TenantRef(alias=claims.issuer_key)        # the realm is the tenant
        roles = [r for r in claims.roles if r in VALID_TENANT_ROLE_NAMES]
        return replace(
            claims,
            trust_domain=TrustDomain.TENANT,
            active_tenant_ref=tenant,
            memberships=[Membership(tenant_ref=tenant, roles=roles, roles_complete=True)],
            memberships_complete=True,
        )
```

`issuer_is_allowed` must also accept a tenant realm only if a tenant row with
that alias exists.

**Not yet supported by the host:** `REAUTHORIZE` and `REAUTHENTICATE` are
declared, but `AuthService.switch_tenant` raises `CapabilityNotSupported` for
them until `/v1.0/login` and `/v1.0/login_return` handle the redirect (and set
`m8flow_selected_tenant` only after the new token arrives). A realm-per-tenant
provider also needs a pre-login tenant picker in the designer, and gives one
person a separate local user per realm. Plan these as product work, not only a
provider.

## Register the provider

The active provider is chosen by `M8FLOW_AUTH_PROVIDER`. `create_app()` calls
`get_auth_provider()` during startup, so registration must happen before that.

For a provider in this repo, register it next to Keycloak in
`integrations/auth/factory.py::_ensure_builtins`:

```python
from m8flow_backend.integrations.auth.example_keycloak.provider import ExampleKeycloakOrgsProvider
from m8flow_backend.integrations.auth.example_keycloak.settings import ExampleKeycloakSettings

register_auth_provider(
    "example-keycloak",
    lambda settings: ExampleKeycloakOrgsProvider(ExampleKeycloakSettings.from_raw(settings.raw)),
)
```

Then run with `M8FLOW_AUTH_PROVIDER=example-keycloak`.

## Prove it: tests

### The conformance suite

`integrations/auth/testing/conformance.py::AuthProviderConformance` is the
contract every provider must pass: login and refresh round trip, rejection of
bad signatures, wrong issuers and expired tokens, neutral errors, honest
capabilities, active-tenant switching through `AuthService`, and known trust
domains. Subclass it and fill in the hooks; leave the `test_*` methods alone.
For example:

```python
# tests/unit/m8flow_backend/integrations/auth/test_example_keycloak_conformance.py
class TestExampleKeycloakConformance(AuthProviderConformance):
    declined_capabilities = frozenset(
        {"user_admin", "tenant_admin", "group_admin", "role_admin", "directory_admin", "provisioning"}
    )

    @pytest.fixture(autouse=True)
    def _fake_keycloak(self, monkeypatch):
        self.server = FakeKeycloakServer()       # discovery, JWKS, token endpoint, Admin API
        monkeypatch.setattr("requests.get", self.server.fake_get)
        monkeypatch.setattr("requests.post", self.server.fake_post)
        monkeypatch.setattr("requests.request", self.server.fake_request)

    def build_provider(self):
        return ExampleKeycloakOrgsProvider(ExampleKeycloakSettings.from_raw({...}))

    def issue_authorization_code(self, *, username):
        return self.server.issue_authorization_code(username)

    def tampered_access_token(self, *, username): ...
    def expired_access_token(self, *, username): ...
    def wrong_issuer_access_token(self, *, username): ...
    def access_token_with_multiple_memberships(self, *, username, tenant_refs): ...
```

`tests/unit/m8flow_backend/integrations/auth/test_keycloak_conformance.py`
has a complete fake Keycloak server (`_FakeKeycloakServer`) you can copy.

### Golden claim tests

Record real tokens from your IdP (single tenant, multi-tenant, platform admin,
thin token), strip secrets, and assert the exact `VerifiedClaims` each one
produces. `test_keycloak_behavior_pins.py` together with
`tests/fixtures/auth/keycloak_claims_golden.json` is the pattern. These tests
catch claim-shape drift between your IdP configuration and your mapping code.

### Route-level regressions

Run the host suites against your provider, especially:

- `tests/unit/m8flow_backend/auth/test_auth_flow_pins.py` (enrichment,
  platform detection, default tenant);
- `tests/unit/m8flow_backend/routes/test_login_controller.py` (login,
  finalization, logout);
- `tests/unit/m8flow_backend/routes/test_onboarding_and_tasks.py`.

Then check by hand with a **non-admin** user (`editor` or `reviewer`) that
`GET /v1.0/onboarding` and `GET /v1.0/tasks` work, including after the user
joins a second tenant and switches to it. Admin-only testing hides tenant and
RBAC bugs.

## Checklist

- [ ] Issuers are an explicit allow-list, checked before any key fetch.
- [ ] `trust_domain` comes from your configuration; `PLATFORM` only for the platform issuer.
- [ ] Only neutral role names leave `map_claims`.
- [ ] `roles_complete` / `memberships_complete` are `True` only when really complete.
- [ ] `list_memberships` returns every tenant with roles and lane groups, and raises (never returns `[]`) when the IdP is unavailable.
- [ ] `switch_mode` matches how your IdP re-scopes a token.
- [ ] Only `base.errors` exceptions escape the provider.
- [ ] Settings are held on the instance; nothing reads `os.environ` per call.
- [ ] The conformance suite and golden claim tests pass.
- [ ] Non-admin, multi-tenant manual check done.

## Related pages

- [How the auth provider works](./how-it-works.md)
- [JWT token shape](./jwt-token-shape.md)
