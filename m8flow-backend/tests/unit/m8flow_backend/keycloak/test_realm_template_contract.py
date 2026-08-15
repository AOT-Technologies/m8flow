"""Characterization tests for the Keycloak realm template.

These lock in the *functional contract* and the *structural invariants* of
``keycloak/realm_exports/m8flow-tenant-template.json`` so that the template can be
regenerated from a clean Keycloak 26.6.1 (see ``keycloak/REALM_REGENERATION_RUNBOOK.md``)
without silently changing behaviour.

Every assertion here holds for the template as it exists today and must still hold after
regeneration. A regenerated artifact that passes this module reproduces the contract; one
that fails it has drifted, and the failure names the drift.

Deliberately stdlib-only (json/re/pathlib) — the realm template is a static asset, so these
tests need neither the Flask app, the database, nor any Keycloak connection.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = BACKEND_ROOT.parent

# Point this at a candidate artifact to validate it BEFORE installing it, e.g.
#   M8FLOW_REALM_TEMPLATE_PATH=.../m8flow-tenant-template.json.new python -m pytest ...
# regenerate-realm-template.sh prints the exact command. Defaults to the installed file.
TEMPLATE_PATH = Path(
    os.environ.get(
        "M8FLOW_REALM_TEMPLATE_PATH",
        BACKEND_ROOT / "keycloak" / "realm_exports" / "m8flow-tenant-template.json",
    )
)
IS_CANDIDATE_ARTIFACT = "M8FLOW_REALM_TEMPLATE_PATH" in os.environ

TEMPLATE_REALM_NAME = "m8flow"
SPOKE_PLACEHOLDER = "__M8FLOW_SPOKE_CLIENT_ID__"
BACKEND_REDIRECT_SENTINEL = "https://replace-me-with-m8flow-backend-host-and-path/*"
FRONTEND_LOGOUT_SENTINEL = "https://replace-me-with-m8flow-frontend-host-and-path/*"


@pytest.fixture(scope="module")
def raw_template() -> str:
    """Template text with line endings normalized to LF.

    ``.gitattributes`` declares ``* text=auto``, so the committed blob is always LF while a
    Windows checkout materializes CRLF in the working tree. LF is what CI, the Docker build
    and the container runtime actually see, so the structural assertions below are written
    against the normalized form. ``read_text`` in default text mode performs that
    normalization; see ``test_committed_template_uses_lf_line_endings`` for the on-disk
    guarantee.
    """
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template(raw_template: str) -> dict:
    return json.loads(raw_template)


@pytest.fixture(scope="module")
def spoke_client(template: dict) -> dict:
    return next(c for c in template["clients"] if c.get("clientId") == SPOKE_PLACEHOLDER)


def _mapper(mappers: list[dict], name: str) -> dict:
    return next(m for m in mappers if m.get("name") == name)


def _user(template: dict, username: str) -> dict:
    return next(u for u in template["users"] if u.get("username") == username)


# ---------------------------------------------------------------------------
# Structural invariants.
#
# These guard the bootstrap paths that manipulate the file as TEXT rather than as
# JSON. Their failure mode in production is silent, so it has to be loud here.
# ---------------------------------------------------------------------------


def test_template_uses_canonical_two_space_serialization(raw_template: str, template: dict) -> None:
    """The file must round-trip through json.dumps(indent=2, ensure_ascii=False) + newline.

    docker/keycloak-entrypoint.sh rewrites the realm name with a line-anchored sed that
    depends on exactly this layout. `kc.sh export` emits a different indentation, so a
    regenerated artifact has to be re-serialized before it is committed.
    """
    expected = json.dumps(template, indent=2, ensure_ascii=False) + "\n"
    assert raw_template == expected, (
        "Realm template is not in canonical form. Re-serialize with "
        "json.dumps(obj, indent=2, ensure_ascii=False) + '\\n' before committing."
    )


def test_template_ends_with_exactly_one_trailing_newline(raw_template: str) -> None:
    assert raw_template.endswith("\n")
    assert not raw_template.endswith("\n\n")


def test_committed_template_uses_lf_line_endings() -> None:
    """The blob git stores must be LF, whatever the local checkout looks like.

    The entrypoint's realm-rename sed anchors on ``,$``. Against a CRLF line the content is
    ``  "id": "m8flow",\\r``, the anchor does not match, and the realm is imported under the
    wrong name with no error. Docker copies the checked-out file into the image, so a CRLF
    blob would carry that failure into the container.
    """
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", str(TEMPLATE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip("git is unavailable or the template is not tracked in this checkout")

    # Output looks like: "i/lf    w/crlf  attr/text=auto  <path>"; "i/" is the index form.
    index_eol = result.stdout.split()[0]
    assert index_eol == "i/lf", (
        f"Committed realm template must use LF line endings, got {index_eol}. "
        "Re-serialize the artifact with LF before committing."
    )


def test_realm_id_is_the_first_key_in_the_document(raw_template: str, template: dict) -> None:
    """`0,/^  "id": ...$/` in the entrypoint sed is an address range from the top of file."""
    assert next(iter(template)) == "id"
    lines = raw_template.split("\n")
    assert lines[0] == "{"
    assert lines[1] == f'  "id": "{TEMPLATE_REALM_NAME}",'


def test_entrypoint_realm_rename_sed_anchor_matches_exactly_once(raw_template: str) -> None:
    """Simulate the anchored sed in docker/keycloak-entrypoint.sh.

    If this regex stops matching, the realm is imported under the template's name instead
    of the deployment's realm name -- with no error reported by sed.
    """
    anchor = re.compile(rf'^  "id": "{re.escape(TEMPLATE_REALM_NAME)}",$', re.MULTILINE)
    assert len(anchor.findall(raw_template)) == 1


@pytest.mark.parametrize(
    ("sentinel", "expected_count"),
    [
        # 6, not the pre-regeneration 9: the old KC 22 export carried three extra references
        # inside the client's UMA authorizationSettings policies. Those policies were upstream
        # fixtures and are stripped by _sanitize_client_for_partial_import() on every tenant
        # import anyway, so the regenerated realm does not recreate them.
        (SPOKE_PLACEHOLDER, 6),
        (f'"containerId": "{TEMPLATE_REALM_NAME}"', 11),
        (f"default-roles-{TEMPLATE_REALM_NAME}", 9),
        (BACKEND_REDIRECT_SENTINEL, 1),
        (FRONTEND_LOGOUT_SENTINEL, 1),
    ],
)
def test_substitution_sentinels_are_present_in_expected_counts(
    raw_template: str, sentinel: str, expected_count: int
) -> None:
    """start_keycloak.sh (jq) and keycloak-entrypoint.sh (sed) string-replace these.

    A regenerated export is built under a real client id and real URLs, so these have to be
    substituted back out before committing. A count of 0 means that step was skipped.
    """
    assert raw_template.count(sentinel) == expected_count


def test_template_contains_no_literal_localhost_frontend_logout_leak(spoke_client: dict) -> None:
    post_logout = spoke_client["attributes"]["post.logout.redirect.uris"]
    assert FRONTEND_LOGOUT_SENTINEL in post_logout


# ---------------------------------------------------------------------------
# Realm-level settings: the m8flow-owned delta.
# ---------------------------------------------------------------------------


def test_realm_identity_and_owned_settings(template: dict) -> None:
    assert template["id"] == TEMPLATE_REALM_NAME
    assert template["realm"] == TEMPLATE_REALM_NAME
    assert template["enabled"] is True
    assert template["loginTheme"] == "m8flow"
    assert template["sslRequired"] == "none"
    assert template["organizationsEnabled"] is True
    assert template["registrationAllowed"] is False


def test_realm_login_identity_policy(template: dict) -> None:
    """Username-based login. Changing any of these changes how users sign in."""
    assert template["loginWithEmailAllowed"] is False
    assert template["registrationEmailAsUsername"] is False
    assert template["duplicateEmailsAllowed"] is False
    assert template["verifyEmail"] is False
    assert template["resetPasswordAllowed"] is False


def test_realm_event_auditing_configuration(template: dict) -> None:
    assert template["eventsEnabled"] is True
    assert template["adminEventsEnabled"] is True
    assert template["adminEventsDetailsEnabled"] is True
    assert set(template["enabledEventTypes"]) == {
        "LOGIN",
        "LOGIN_ERROR",
        "LOGOUT",
        "REGISTER",
        "CODE_TO_TOKEN",
        "CODE_TO_TOKEN_ERROR",
    }


def test_realm_default_client_scope_defaults(template: dict) -> None:
    """Compared as sets: Keycloak does not guarantee the order it emits these in.

    `saml_organization` is Keycloak 26 stock scaffolding, absent from the old KC 22 export.
    """
    assert set(template["defaultDefaultClientScopes"]) == {
        "email",
        "profile",
        "role_list",
        "roles",
        "acr",
        "web-origins",
        "basic",
        "saml_organization",
    }
    assert set(template["defaultOptionalClientScopes"]) == {
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt",
        "organization",
    }


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("accessTokenLifespan", 1800),
        ("accessTokenLifespanForImplicitFlow", 900),
        ("ssoSessionIdleTimeout", 86400),
        ("ssoSessionMaxLifespan", 864000),
        ("offlineSessionIdleTimeout", 2592000),
        ("offlineSessionMaxLifespan", 5184000),
        ("accessCodeLifespan", 60),
        ("accessCodeLifespanUserAction", 300),
        ("accessCodeLifespanLogin", 1800),
        ("actionTokenGeneratedByAdminLifespan", 43200),
        ("actionTokenGeneratedByUserLifespan", 300),
        ("oauth2DeviceCodeLifespan", 600),
    ],
)
def test_session_and_token_lifespans_are_unchanged(template: dict, setting: str, expected: int) -> None:
    """Regeneration must not silently shorten or lengthen sessions."""
    assert template[setting] == expected


# ---------------------------------------------------------------------------
# The spoke client -- the only genuinely m8flow client in the realm.
# ---------------------------------------------------------------------------


def test_spoke_client_flow_configuration(spoke_client: dict) -> None:
    assert spoke_client["protocol"] == "openid-connect"
    assert spoke_client["enabled"] is True
    assert spoke_client["publicClient"] is False
    assert spoke_client["standardFlowEnabled"] is True
    assert spoke_client["implicitFlowEnabled"] is False
    assert spoke_client["directAccessGrantsEnabled"] is True
    assert spoke_client["serviceAccountsEnabled"] is True
    assert spoke_client["authorizationServicesEnabled"] is True
    assert spoke_client["fullScopeAllowed"] is True
    assert spoke_client["frontchannelLogout"] is False
    assert spoke_client["clientAuthenticatorType"] == "client-secret"


def test_spoke_client_redirect_uris(spoke_client: dict) -> None:
    assert BACKEND_REDIRECT_SENTINEL in spoke_client["redirectUris"]
    assert "http://localhost:6840/*" in spoke_client["redirectUris"]


def test_spoke_client_scope_assignment(spoke_client: dict) -> None:
    """`organization` must stay OPTIONAL.

    Promoting it to a default scope puts organization claims in every token and changes
    tenant resolution for every client of the realm.
    """
    # `service_account` is added automatically by Keycloak 26 to any client with service
    # accounts enabled; it is stock scaffolding, not an m8flow choice.
    assert set(spoke_client["defaultClientScopes"]) == {
        "web-origins",
        "acr",
        "profile",
        "roles",
        "basic",
        "email",
        "service_account",
    }
    assert set(spoke_client["optionalClientScopes"]) == {
        "organization",
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt",
    }
    assert "organization" not in spoke_client["defaultClientScopes"]


def test_spoke_client_protocol_mapper_set(spoke_client: dict) -> None:
    assert {m["name"] for m in spoke_client["protocolMappers"]} == {
        "Client IP Address",
        "Client Host",
        "Client ID",
        "realm_id",
        "roles",
        "m8flow-backend-audience",
    }


def test_spoke_client_roles_claim_mapper(spoke_client: dict) -> None:
    """RBAC depends on a flat, multivalued `roles` claim in the access token."""
    roles_mapper = _mapper(spoke_client["protocolMappers"], "roles")
    assert roles_mapper["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert roles_mapper["config"]["claim.name"] == "roles"
    assert roles_mapper["config"]["access.token.claim"] == "true"
    assert roles_mapper["config"]["multivalued"] == "true"


def test_spoke_client_realm_info_mapper_is_the_m8flow_extension(spoke_client: dict) -> None:
    """Provided by keycloak-extensions/realm-info-mapper; emits the tenant claims."""
    realm_id_mapper = _mapper(spoke_client["protocolMappers"], "realm_id")
    assert realm_id_mapper["protocolMapper"] == "oidc-realm-info-mapper"
    assert realm_id_mapper["config"]["access.token.claim"] == "true"


def test_spoke_client_audience_mapper_targets_itself(spoke_client: dict) -> None:
    audience_mapper = _mapper(spoke_client["protocolMappers"], "m8flow-backend-audience")
    assert audience_mapper["protocolMapper"] == "oidc-audience-mapper"
    assert audience_mapper["config"]["included.client.audience"] == SPOKE_PLACEHOLDER
    assert audience_mapper["config"]["access.token.claim"] == "true"


def test_spoke_client_has_no_realm_role_groups_mapper(spoke_client: dict) -> None:
    """Deliberate deletion of upstream behaviour -- must not come back on regeneration."""
    assert not any(
        m.get("name") == "groups" and m.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        for m in spoke_client["protocolMappers"]
    )


def test_spoke_client_roles_are_defined(template: dict) -> None:
    client_roles = template["roles"]["client"][SPOKE_PLACEHOLDER]
    assert {r["name"] for r in client_roles} == {
        "m8flow-admin",
        "uma_protection",
        "repeat-form-role-2",
    }


def test_only_expected_clients_exist(template: dict) -> None:
    """Six Keycloak built-ins plus the single m8flow spoke client.

    `account-console` is Keycloak 26 stock; the old KC 22 export predates it. Keycloak
    creates it in every realm regardless, so carrying it matches the running server.
    """
    assert {c["clientId"] for c in template["clients"]} == {
        "account",
        "account-console",
        "admin-cli",
        "broker",
        "realm-management",
        "security-admin-console",
        SPOKE_PLACEHOLDER,
    }


# ---------------------------------------------------------------------------
# Roles, users, scopes.
# ---------------------------------------------------------------------------


def test_realm_roles_are_exactly_the_m8flow_rbac_set(template: dict) -> None:
    assert {r["name"] for r in template["roles"]["realm"]} == {
        f"default-roles-{TEMPLATE_REALM_NAME}",
        "uma_authorization",
        "offline_access",
        "repeat-form-role-realm",
        "tenant-admin",
        "editor",
        "integrator",
        "reviewer",
        "submitter",
        "viewer",
    }


def test_default_role_points_at_the_realm_default_composite(template: dict) -> None:
    default_role = template["defaultRole"]
    assert default_role["name"] == f"default-roles-{TEMPLATE_REALM_NAME}"
    assert default_role["composite"] is True
    assert default_role["clientRole"] is False
    assert default_role["containerId"] == TEMPLATE_REALM_NAME


def test_seed_users_are_exactly_the_expected_set(template: dict) -> None:
    assert {u["username"] for u in template["users"]} == {
        "admin",
        "editor",
        "integrator",
        "reviewer",
        "submitter",
        "viewer",
        f"service-account-{SPOKE_PLACEHOLDER}",
    }


@pytest.mark.parametrize("username", ["admin", "editor", "integrator", "reviewer", "submitter", "viewer"])
def test_seed_users_carry_only_the_realm_default_role(template: dict, username: str) -> None:
    """Role grants happen at runtime via organization group mappings, not in the template."""
    user = _user(template, username)
    assert user["enabled"] is True
    assert user["realmRoles"] == [f"default-roles-{TEMPLATE_REALM_NAME}"]
    assert user["groups"] == []


@pytest.mark.parametrize("username", ["editor", "integrator", "reviewer", "submitter", "viewer"])
def test_non_admin_seed_users_bypass_verify_profile(template: dict, username: str) -> None:
    """Empty email + emailVerified=true is what keeps VERIFY_PROFILE off the login path.

    Giving these users real addresses, or flipping emailVerified to false, makes Keycloak
    interrupt first login with the profile-completion form.
    """
    user = _user(template, username)
    assert user["email"] == ""
    assert user["emailVerified"] is True
    assert user["firstName"] == username.capitalize()


def test_admin_seed_user_holds_realm_management_roles(template: dict) -> None:
    admin = _user(template, "admin")
    assert "realm-management" in admin["clientRoles"]
    assert admin["email"] == "admin@example.com"


def test_service_account_user_is_bound_to_the_spoke_client(template: dict) -> None:
    service_account = _user(template, f"service-account-{SPOKE_PLACEHOLDER}")
    assert service_account["serviceAccountClientId"] == SPOKE_PLACEHOLDER
    assert SPOKE_PLACEHOLDER in service_account["clientRoles"]


def test_realm_seeds_no_groups(template: dict) -> None:
    """Organization role groups are created at runtime by start_keycloak.sh."""
    assert template["groups"] == []


def test_client_scopes_are_the_stock_set(template: dict) -> None:
    """The Keycloak 26 stock scope set.

    `basic`, `organization`, `saml_organization` and `service_account` are all KC 26
    scaffolding absent from the old KC 22 export. `organization` shipping as a stock scope
    is why the realm needs KC_FEATURES to include `organization`. The runtime-created
    `organization-groups` scope is still not seeded here.
    """
    assert {s["name"] for s in template["clientScopes"]} == {
        "acr",
        "address",
        "basic",
        "email",
        "microprofile-jwt",
        "offline_access",
        "organization",
        "phone",
        "profile",
        "role_list",
        "roles",
        "saml_organization",
        "service_account",
        "web-origins",
    }
    assert "organization-groups" not in {s["name"] for s in template["clientScopes"]}


def test_profile_scope_emits_no_groups_claim(template: dict) -> None:
    profile = next(s for s in template["clientScopes"] if s["name"] == "profile")
    assert not any(m.get("name") == "groups" for m in profile["protocolMappers"])


def test_microprofile_scope_emits_roles_but_no_groups(template: dict) -> None:
    microprofile = next(s for s in template["clientScopes"] if s["name"] == "microprofile-jwt")
    roles_mapper = _mapper(microprofile["protocolMappers"], "roles")
    assert roles_mapper["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert roles_mapper["config"]["claim.name"] == "roles"
    assert not any(m.get("name") == "groups" for m in microprofile["protocolMappers"])


def test_offline_access_scope_mapping_is_present(template: dict) -> None:
    assert {"clientScope": "offline_access", "roles": ["offline_access"]} in template["scopeMappings"]


# ---------------------------------------------------------------------------
# Consumer contracts: the three code paths that read this file.
# ---------------------------------------------------------------------------


def test_keys_required_by_minimal_realm_creation_are_present(template: dict) -> None:
    """keycloak_service._minimal_realm_creation_payload() reads these.

    partialImport does not apply realm-level settings, so anything not carried here is lost
    for newly created tenant realms.
    """
    for key in ("realm", "enabled", "sslRequired", "registrationAllowed", "loginTheme"):
        assert key in template, f"{key} is consumed by _minimal_realm_creation_payload()"


def test_keys_required_by_partial_import_are_present(template: dict) -> None:
    """keycloak_service._partial_import_payload() reads exactly these collections."""
    for key in (
        "clients",
        "roles",
        "groups",
        "users",
        "clientScopes",
        "identityProviders",
        "defaultDefaultClientScopes",
        "defaultOptionalClientScopes",
    ):
        assert key in template, f"{key} is consumed by _partial_import_payload()"


def test_full_import_paths_receive_a_complete_realm_document(template: dict) -> None:
    """start_keycloak.sh and keycloak-entrypoint.sh POST/import the WHOLE document.

    A hand-assembled partial JSON would satisfy the tenant-creation path but fail these two,
    so the artifact must remain a complete Keycloak realm export.
    """
    for key in (
        "authenticationFlows",
        "requiredActions",
        "browserSecurityHeaders",
        "components",
        "clientProfiles",
        "clientPolicies",
        "defaultRole",
    ):
        assert key in template, f"{key} is required for a full realm import"
    assert len(template["authenticationFlows"]) >= 1
    assert any(f["alias"] == "browser" for f in template["authenticationFlows"])


def test_browser_flow_keeps_single_page_username_password_login(template: dict) -> None:
    """AGENTS.md: login must stay one page. `Username Password Form` must remain bound.

    An identity-first / username-only step becoming the user-facing path is a regression.
    """
    executions = [
        execution
        for flow in template["authenticationFlows"]
        for execution in flow.get("authenticationExecutions", [])
    ]
    authenticators = {e.get("authenticator") for e in executions}
    assert "auth-username-password-form" in authenticators
    assert "auth-username-form" not in authenticators, (
        "A username-only form would split login into two pages; AGENTS.md forbids this."
    )


# ---------------------------------------------------------------------------
# Provenance guards.
#
# The template is currently LGPL-derived (see REALM_REGENERATION_RUNBOOK.md). These
# tests hold BOTH before and after regeneration: they ratchet contamination downward
# and never allow it to grow.
# ---------------------------------------------------------------------------


UPSTREAM_REALM_EXPORT = (
    REPO_ROOT / "spiffworkflow-backend" / "keycloak" / "realm_exports" / "spiffworkflow-realm.json"
)

# 0 since the realm was regenerated from scratch on a clean Keycloak 26.6.1
# (regenerate-realm-template.sh). It was 126 while the template was upstream-derived.
# This is a ratchet: it must never go back up.
MAX_UUIDS_SHARED_WITH_UPSTREAM = 0

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


@pytest.mark.skipif(
    not UPSTREAM_REALM_EXPORT.exists(),
    reason="upstream SpiffArena tree is gitignored and not present in this checkout",
)
def test_uuid_overlap_with_upstream_never_increases(raw_template: str) -> None:
    """Shared random UUIDs are copy fingerprints -- they cannot collide independently.

    Ratchet only: this must never grow. After regeneration it should be 0, at which point
    MAX_UUIDS_SHARED_WITH_UPSTREAM should be lowered to 0 to lock the gain in.
    """
    upstream_raw = UPSTREAM_REALM_EXPORT.read_text(encoding="utf-8")
    shared = set(_UUID_RE.findall(raw_template)) & set(_UUID_RE.findall(upstream_raw))
    assert len(shared) <= MAX_UUIDS_SHARED_WITH_UPSTREAM, (
        f"UUID overlap with the upstream LGPL realm export grew to {len(shared)} "
        f"(ceiling {MAX_UUIDS_SHARED_WITH_UPSTREAM}). Do not copy fragments from "
        f"spiffworkflow-backend/; see keycloak/REALM_REGENERATION_RUNBOOK.md."
    )


@pytest.mark.skipif(
    not UPSTREAM_REALM_EXPORT.exists(),
    reason="upstream SpiffArena tree is gitignored and not present in this checkout",
)
def test_template_does_not_reuse_the_upstream_realm_name(raw_template: str) -> None:
    assert "spiffworkflow" not in raw_template.lower()


def test_template_carries_no_lgpl_or_attribution_markers(raw_template: str) -> None:
    lowered = raw_template.lower()
    for marker in ("lgpl", "gnu lesser", "sartography", "copyright"):
        assert marker not in lowered, f"license/attribution marker {marker!r} must not appear"


# ---------------------------------------------------------------------------
# Secret rotation consistency.
# ---------------------------------------------------------------------------


# Every file that hardcodes the spoke client secret as a default. Regenerating the realm
# means rotating the secret, and it has to move in ALL of these at once or local dev,
# docker, and the bootstrap scripts disagree about how to authenticate.
#
# REALM_REGENERATION_RUNBOOK.md intentionally still quotes the OLD secret as provenance
# evidence, so it is deliberately excluded here.
SECRET_CONSUMERS = {
    "m8flow-backend/src/m8flow_backend/config.py": 1,
    "m8flow-backend/src/m8flow_backend/services/upstream_auth_defaults_patch.py": 1,
    "m8flow-backend/keycloak/start_keycloak.sh": 1,
    "m8flow-backend/bin/ensure_keycloak_master_super_admin.sh": 1,
    "m8flow-backend/bin/local_development_environment_setup": 1,
    "m8flow-backend/bin/get_token": 1,
    "m8flow-backend/tests/unit/m8flow_backend/services/test_upstream_auth_defaults_patch.py": 1,
    "docker/keycloak-entrypoint.sh": 1,
    "sample.env": 3,
}


@pytest.mark.skipif(
    IS_CANDIDATE_ARTIFACT,
    reason="a freshly generated candidate carries a new secret; rotation is runbook step 6.5",
)
@pytest.mark.parametrize(("relative_path", "expected_count"), sorted(SECRET_CONSUMERS.items()))
def test_spoke_client_secret_matches_every_consumer(
    spoke_client: dict, relative_path: str, expected_count: int
) -> None:
    """Catches a partial rotation, which would otherwise only surface at runtime."""
    secret = spoke_client["secret"]
    assert secret, "spoke client must define a secret in the template"

    path = REPO_ROOT / relative_path
    assert path.exists(), f"expected secret consumer is missing: {relative_path}"
    assert path.read_text(encoding="utf-8").count(secret) == expected_count, (
        f"{relative_path} does not carry the template's spoke client secret "
        f"{expected_count}x. Rotating the secret must update the template and all "
        f"{len(SECRET_CONSUMERS)} consumers together."
    )
