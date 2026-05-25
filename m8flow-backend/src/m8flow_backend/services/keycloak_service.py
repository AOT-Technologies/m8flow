"""Keycloak service: master token, create realm from template, tenant login, create user in realm."""
from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

from m8flow_backend.config import (
    keycloak_admin_password,
    keycloak_admin_user,
    keycloak_default_groups_path,
    keycloak_url,
    realm_template_path,
    redirect_uri_backend_host_and_path,
    redirect_uri_frontend_host,
    shared_realm_name,
    spoke_client_id,
    spoke_keystore_password,
    spoke_keystore_p12_path,
    template_realm_name,
)
from m8flow_backend.services.tenant_group_mapping import (
    ORGANIZATION_GROUP_ROLE_MAPPING_CONFIGURED_ATTRIBUTE,
    ORGANIZATION_GROUP_ROLE_NAMES_ATTRIBUTE,
    normalize_tenant_role_names,
    tenant_roles_for_organization_group,
)
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifiers

# Template source: m8flow-backend/keycloak/realm_exports/m8flow-tenant-template.json
# Only necessary values are changed for a new tenant; roles, groups, users, and clients are preserved.
# Placeholder in the JSON is replaced at load time with M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID (default: m8flow-backend).
SPOKE_CLIENT_ID_PLACEHOLDER = "__M8FLOW_SPOKE_CLIENT_ID__"
BACKEND_REDIRECT_PLACEHOLDER = "replace-me-with-m8flow-backend-host-and-path"
FRONTEND_REDIRECT_PLACEHOLDER = "replace-me-with-m8flow-frontend-host-and-path"
DEFAULT_ROLES_PREFIX = "default-roles-"  # role name "default-roles-{realm}" must be updated
REALM_URL_PREFIX = "/realms/"  # client baseUrl/redirectUris contain /realms/{realm}/
ADMIN_CONSOLE_URL_PREFIX = "/admin/"  # security-admin-console has /admin/{realm}/console/
BACKEND_URL_PLACEHOLDER = "https://replace-me-with-m8flow-backend-host-and-path/*"
FRONTEND_URL_PLACEHOLDER = "https://replace-me-with-m8flow-frontend-host-and-path/*"
FRONTEND_CLIENT_ID = "spiffworkflow-frontend"
POST_LOGOUT_REDIRECT_URIS_ATTR = "post.logout.redirect.uris"
GROUPS_CLAIM_NAME = "groups"
ROLES_CLAIM_NAME = "roles"
NORMALIZED_GROUP_MAPPER_PROVIDER_ID = "oidc-normalized-group-membership-mapper"
# Names reserved for global (non-tenant) administration; never cloned into tenant realms.
GLOBAL_ONLY_REALM_ROLE_NAMES = frozenset({"super-admin"})
GLOBAL_ONLY_USERNAMES = frozenset({"super-admin"})
def _substitute_spoke_client_id(obj: Any, client_id: str) -> Any:
    """Recursively replace SPOKE_CLIENT_ID_PLACEHOLDER with client_id in dict keys and string values."""
    if isinstance(obj, dict):
        return {
            (client_id if k == SPOKE_CLIENT_ID_PLACEHOLDER else k): _substitute_spoke_client_id(v, client_id)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_substitute_spoke_client_id(item, client_id) for item in obj]
    if isinstance(obj, str) and SPOKE_CLIENT_ID_PLACEHOLDER in obj:
        return obj.replace(SPOKE_CLIENT_ID_PLACEHOLDER, client_id)
    return obj


def _replace_redirect_placeholders_in_place(
    obj: Any, backend_val: str | None, frontend_val: str | None
) -> None:
    """Recursively replace redirect host placeholders in string values (mutates in place)."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                s = v
                if backend_val is not None and BACKEND_REDIRECT_PLACEHOLDER in s:
                    s = s.replace(BACKEND_REDIRECT_PLACEHOLDER, backend_val)
                if frontend_val is not None and FRONTEND_REDIRECT_PLACEHOLDER in s:
                    s = s.replace(FRONTEND_REDIRECT_PLACEHOLDER, frontend_val)
                if s != v:
                    obj[k] = s
            else:
                _replace_redirect_placeholders_in_place(v, backend_val, frontend_val)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                s = item
                if backend_val is not None and BACKEND_REDIRECT_PLACEHOLDER in s:
                    s = s.replace(BACKEND_REDIRECT_PLACEHOLDER, backend_val)
                if frontend_val is not None and FRONTEND_REDIRECT_PLACEHOLDER in s:
                    s = s.replace(FRONTEND_REDIRECT_PLACEHOLDER, frontend_val)
                if s != item:
                    obj[i] = s
            else:
                _replace_redirect_placeholders_in_place(item, backend_val, frontend_val)


def load_default_organizational_group_paths() -> list[str]:
    """Load the repo-owned default organizational groups for Keycloak tenant provisioning."""
    config_path = Path(keycloak_default_groups_path())
    if not config_path.exists():
        raise FileNotFoundError(f"Default Keycloak groups config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as config_file:
        config_data = json.load(config_file)

    raw_group_paths = config_data.get("groups") if isinstance(config_data, dict) else config_data
    if not isinstance(raw_group_paths, list):
        raise ValueError(f"Default Keycloak groups config must contain a list of group paths: {config_path}")

    return normalize_organizational_group_identifiers(
        [group_path for group_path in raw_group_paths if isinstance(group_path, str)]
    )


def default_organizational_group_names() -> tuple[str, ...]:
    """Return the canonical top-level organization group names for workflow membership."""
    group_names: list[str] = []
    seen: set[str] = set()

    for group_path in load_default_organizational_group_paths():
        normalized_path = normalize_organizational_group_identifier(group_path)
        group_name = normalized_path.strip("/").split("/")[-1].strip() if normalized_path else ""
        if not group_name or group_name in seen:
            continue
        seen.add(group_name)
        group_names.append(group_name)

    return tuple(group_names)


def _load_default_organization_role_group_names() -> tuple[str, ...]:
    """Return a stable exported tuple for modules that import role-group names at import time."""
    try:
        group_names = default_organizational_group_names()
        if group_names:
            return group_names
    except Exception as exc:  # pragma: no cover - defensive startup fallback
        logger.warning("Falling back to built-in organization role groups: %s", exc)
    return ("Approvers", "Designers", "Administrators", "Support", "Submitters", "Viewers")


# Backward-compatible export consumed by route/service patches at import time.
DEFAULT_ORGANIZATION_ROLE_GROUP_NAMES = _load_default_organization_role_group_names()


def _normalized_keycloak_group_path(group: dict[str, Any], parent_path: str = "") -> str:
    path = group.get("path")
    if isinstance(path, str) and path.strip():
        return normalize_organizational_group_identifier(path)

    name = group.get("name")
    if not isinstance(name, str) or not name.strip():
        return ""

    group_path = f"{parent_path}/{name.strip()}" if parent_path else name.strip()
    return normalize_organizational_group_identifier(group_path)


def _merge_group_path_into_keycloak_groups(groups: list[dict[str, Any]], group_path: str) -> None:
    normalized_path = normalize_organizational_group_identifier(group_path)
    if not normalized_path:
        return

    current_groups = groups
    parent_path = ""
    for segment in normalized_path.strip("/").split("/"):
        candidate_path = normalize_organizational_group_identifier(
            f"{parent_path}/{segment}" if parent_path else segment
        )
        match = next(
            (
                group
                for group in current_groups
                if isinstance(group, dict)
                and _normalized_keycloak_group_path(group, parent_path) == candidate_path
            ),
            None,
        )
        if match is None:
            match = {"name": segment, "path": candidate_path, "subGroups": []}
            current_groups.append(match)
        else:
            match.setdefault("name", segment)
            match.setdefault("path", candidate_path)
            if not isinstance(match.get("subGroups"), list):
                match["subGroups"] = []

        parent_path = candidate_path
        current_groups = match["subGroups"]


def _merge_default_organizational_groups(
    groups: list[dict[str, Any]],
    default_group_paths: list[str],
) -> list[dict[str, Any]]:
    """Merge canonical organizational group paths into the Keycloak group tree."""
    merged_groups = copy.deepcopy(groups)
    for group_path in default_group_paths:
        _merge_group_path_into_keycloak_groups(merged_groups, group_path)
    return merged_groups


def _env_public_url(*keys: str) -> str | None:
    """Return the first non-empty public URL from environment."""
    for key in keys:
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _origin_from_url(url: str | None) -> str | None:
    """Normalize an absolute URL to scheme://host[:port]."""
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    origin = f"{parsed.scheme.lower()}://{parsed.hostname.lower()}"
    if parsed.port is not None:
        origin += f":{parsed.port}"
    return origin


def _wildcard_from_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    return f"{origin}/*"


def _replace_runtime_url_placeholders(
    value: str,
    *,
    backend_wildcard: str | None,
    frontend_wildcard: str | None,
) -> str:
    """Replace template placeholders with runtime backend/frontend wildcards."""
    if backend_wildcard:
        value = value.replace(BACKEND_URL_PLACEHOLDER, backend_wildcard)
    if frontend_wildcard:
        value = value.replace(FRONTEND_URL_PLACEHOLDER, frontend_wildcard)
    return value


def _unique_strings(values: list[Any]) -> list[str]:
    """Return unique, non-empty strings while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _split_keycloak_uri_list(value: str | None) -> list[str]:
    """Split Keycloak's ##-separated URI list attribute."""
    if not isinstance(value, str) or not value.strip():
        return []
    return [item.strip() for item in value.split("##") if item.strip()]


def _runtime_client_values(
    client_id: Any,
    *,
    backend_value: str | None,
    frontend_value: str | None,
) -> tuple[str | None, ...]:
    """Return runtime URL values relevant for the given client."""
    if client_id == spoke_client_id():
        return (backend_value, frontend_value)
    if client_id == FRONTEND_CLIENT_ID:
        return (frontend_value,)
    return ()


def _replace_runtime_placeholders_in_list(
    values: Any,
    *,
    backend_wildcard: str | None,
    frontend_wildcard: str | None,
) -> list[Any]:
    """Replace runtime URL placeholders in a list of client values."""
    if not isinstance(values, list):
        return []
    return [
        _replace_runtime_url_placeholders(
            value,
            backend_wildcard=backend_wildcard,
            frontend_wildcard=frontend_wildcard,
        )
        if isinstance(value, str)
        else value
        for value in values
    ]


def _update_runtime_client_attributes(
    attrs: dict[str, Any],
    *,
    backend_wildcard: str | None,
    frontend_wildcard: str | None,
) -> None:
    """Replace runtime placeholders in string-valued client attributes."""
    for key, value in attrs.items():
        if isinstance(value, str):
            attrs[key] = _replace_runtime_url_placeholders(
                value,
                backend_wildcard=backend_wildcard,
                frontend_wildcard=frontend_wildcard,
            )


def _set_post_logout_redirect_uris(
    attrs: dict[str, Any],
    client_id: Any,
    *,
    backend_wildcard: str | None,
    frontend_wildcard: str | None,
) -> None:
    """Add runtime post-logout redirect URIs for supported clients."""
    runtime_values = _runtime_client_values(
        client_id,
        backend_value=backend_wildcard,
        frontend_value=frontend_wildcard,
    )
    if not runtime_values:
        return

    post_logout_uris = _split_keycloak_uri_list(attrs.get(POST_LOGOUT_REDIRECT_URIS_ATTR))
    post_logout_uris.extend(candidate for candidate in runtime_values if candidate)
    attrs[POST_LOGOUT_REDIRECT_URIS_ATTR] = "##".join(_unique_strings(post_logout_uris))


def _apply_runtime_client_urls(
    client: dict[str, Any],
    *,
    backend_origin: str | None,
    backend_wildcard: str | None,
    frontend_origin: str | None,
    frontend_wildcard: str | None,
) -> None:
    """Inject runtime backend/frontend URLs into tenant realm client config."""
    client_id = client.get("clientId")
    redirect_uri_values = _runtime_client_values(
        client_id,
        backend_value=backend_wildcard,
        frontend_value=frontend_wildcard,
    )
    web_origin_values = _runtime_client_values(
        client_id,
        backend_value=backend_origin,
        frontend_value=frontend_origin,
    )

    updated_redirect_uris = _replace_runtime_placeholders_in_list(
        client.get("redirectUris"),
        backend_wildcard=backend_wildcard,
        frontend_wildcard=frontend_wildcard,
    )
    updated_redirect_uris.extend(candidate for candidate in redirect_uri_values if candidate)
    if updated_redirect_uris:
        client["redirectUris"] = _unique_strings(updated_redirect_uris)

    web_origins = client.get("webOrigins")
    updated_web_origins: list[str] = list(web_origins) if isinstance(web_origins, list) else []
    updated_web_origins.extend(candidate for candidate in web_origin_values if candidate)
    if updated_web_origins:
        client["webOrigins"] = _unique_strings(updated_web_origins)

    attrs = client.get("attributes") or {}
    if not isinstance(attrs, dict):
        return

    _update_runtime_client_attributes(
        attrs,
        backend_wildcard=backend_wildcard,
        frontend_wildcard=frontend_wildcard,
    )
    _set_post_logout_redirect_uris(
        attrs,
        client_id,
        backend_wildcard=backend_wildcard,
        frontend_wildcard=frontend_wildcard,
    )
    client["attributes"] = attrs


def _regenerate_all_ids(obj: Any, id_map: dict[str, str] | None = None) -> dict[str, str]:
    """
    Recursively replace all 'id' values with new UUIDs, maintaining internal consistency.
    Returns a mapping of old_id -> new_id so references can be updated.
    """
    if id_map is None:
        id_map = {}
    if isinstance(obj, dict):
        if "id" in obj and isinstance(obj["id"], str):
            old_id = obj["id"]
            if old_id not in id_map:
                id_map[old_id] = str(uuid.uuid4())
            obj["id"] = id_map[old_id]
        for v in obj.values():
            _regenerate_all_ids(v, id_map)
    elif isinstance(obj, list):
        for item in obj:
            _regenerate_all_ids(item, id_map)
    return id_map


def _get_private_key_from_p12():
    """Load private key from configured PKCS#12 keystore."""
    path = spoke_keystore_p12_path()
    if not path or not Path(path).exists():
        raise ValueError(
            "M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 path not set or file not found. "
            "Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 to m8flow-backend/keystore.p12 (or absolute path) for spoke tenant auth."
        )
    password = spoke_keystore_password()
    if not password:
        raise ValueError("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD must be set for JWT client assertion.")
    from cryptography.hazmat.primitives.serialization import pkcs12

    with open(path, "rb") as f:
        data = f.read()
    pw_bytes = password.encode("utf-8") if isinstance(password, str) else password
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="PKCS#12 bundle could not be parsed as DER")
        private_key, certificate, _ = pkcs12.load_key_and_certificates(data, pw_bytes)
    if private_key is None:
        raise ValueError("keystore.p12 has no private key")
    return private_key, certificate


def _get_certificate_pem_from_p12() -> str:
    """Get public certificate PEM from PKCS#12 keystore for JWT client authentication."""
    _, certificate = _get_private_key_from_p12()
    if certificate is None:
        raise ValueError("keystore.p12 has no certificate")
    from cryptography.hazmat.primitives.serialization import Encoding
    
    return certificate.public_bytes(Encoding.PEM).decode("utf-8")


def _build_client_assertion_jwt(token_url: str, realm: str) -> str:
    """Build JWT for client_assertion (RFC 7523). Signed with spoke keystore private key."""
    import jwt

    base_url = keycloak_url()
    realm_issuer = f"{base_url}/realms/{realm}"
    client_id = spoke_client_id()
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": realm_issuer,
        "exp": now + 60,
        "iat": now,
        "jti": f"{uuid.uuid4().hex}-{now}-{uuid.uuid4().hex[:8]}",
    }
    private_key, _ = _get_private_key_from_p12()
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_master_admin_token() -> str:
    """Get access token via master realm admin username/password (for Admin API)."""
    url = f"{keycloak_url()}/realms/master/protocol/openid-connect/token"
    password = keycloak_admin_password()
    if not password:
        raise ValueError("KEYCLOAK_ADMIN_PASSWORD or M8FLOW_KEYCLOAK_ADMIN_PASSWORD must be set for realm creation.")
    # Testing only: log credentials used for tenant creation. Logging password is a security risk; remove or disable in production.
    username = keycloak_admin_user()
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": username,
        "password": password,
    }
    r = requests.post(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _log_admin_token_claims(token: str) -> None:
    """Decode admin JWT and log exp, iat, and realm_access (roles) at DEBUG. Never raises."""
    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        iat = payload.get("iat")
        now = int(time.time())
        expired = exp is not None and exp < now
        realm_access = payload.get("realm_access") or {}
        roles = realm_access.get("roles") if isinstance(realm_access, dict) else None
        logger.debug(
            "create_realm_from_template admin token: exp=%s iat=%s expired=%s realm_access.roles=%s",
            exp,
            iat,
            expired,
            roles,
        )
    except Exception:
        logger.debug("Could not decode admin token for logging")


def realm_exists(realm: str) -> bool:
    """Return True if the realm exists in Keycloak, False otherwise (e.g. 404).
    Uses the public OpenID discovery endpoint so no admin credentials are required.
    Treats 200 (OK) and 403 (Forbidden) as realm exists: some Keycloak configs restrict
    discovery while the realm and auth endpoint still work."""
    if not realm or not str(realm).strip():
        return False
    realm = str(realm).strip()
    try:
        base_url = keycloak_url()
        # Public endpoint: no admin token required
        discovery_url = f"{base_url}/realms/{realm}/.well-known/openid-configuration"
        r = requests.get(discovery_url, timeout=30)
        logger.debug(
            "realm_exists: realm=%r url=%s status=%s",
            realm,
            discovery_url,
            r.status_code,
        )
        if r.status_code not in (200, 403):
            logger.warning(
                "realm_exists: realm=%s url=%s status=%s (check KEYCLOAK_URL if realm exists in browser)",
                realm,
                discovery_url,
                r.status_code,
            )
            if r.text:
                logger.debug("realm_exists: response body (first 200 chars): %s", r.text[:200])
        # 200 = discovery public; 403 = discovery restricted but realm often still exists and auth works
        return r.status_code in (200, 403)
    except Exception as e:
        try:
            _url = f"{keycloak_url()}/realms/{realm}/.well-known/openid-configuration"
        except Exception:
            _url = "(could not build URL)"
        logger.debug("realm_exists: realm=%r url=%s error=%r", realm, _url, e)
        logger.warning(
            "realm_exists: realm=%s discovery_url=%s error=%s",
            realm,
            _url,
            e,
        )
        return False


def tenant_login_authorization_url(realm: str) -> str:
    """Return the Keycloak authorization (login) base URL for the given realm (no query params)."""
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")
    realm = str(realm).strip()
    return f"{keycloak_url()}/realms/{realm}/protocol/openid-connect/auth"


def _shared_realm_organizations_url(*segments: str) -> str:
    """Return the Organizations Admin API URL inside the configured shared realm."""
    base_url = keycloak_url()
    realm = shared_realm_name()
    base = f"{base_url}/admin/realms/{realm}/organizations"
    normalized_segments = [segment.strip("/") for segment in segments if segment and segment.strip("/")]
    if not normalized_segments:
        return base
    return f"{base}/{'/'.join(normalized_segments)}"


def _shared_realm_organization_groups_url(
    organization_id: str,
    *segments: str,
) -> str:
    """Return the organization-groups Admin API URL inside the configured shared realm."""
    base = _shared_realm_organizations_url(str(organization_id).strip(), "groups")
    normalized_segments = [segment.strip("/") for segment in segments if segment and segment.strip("/")]
    if not normalized_segments:
        return base
    return f"{base}/{'/'.join(normalized_segments)}"


def _shared_realm_organization_group_role_mappings_url(
    organization_id: str,
    group_id: str,
    *segments: str,
) -> str:
    """Return the organization-group role-mappings Admin API URL inside the shared realm."""
    base = _shared_realm_organization_groups_url(
        str(organization_id).strip(),
        quote(str(group_id).strip(), safe=""),
        "role-mappings",
        "realm",
    )
    normalized_segments = [segment.strip("/") for segment in segments if segment and segment.strip("/")]
    if not normalized_segments:
        return base
    return f"{base}/{'/'.join(normalized_segments)}"


def get_organization_by_id(
    organization_id: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the organization representation by id from the shared realm, or None when missing."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    organization_id = str(organization_id).strip()
    token = admin_token or get_master_admin_token()

    r = requests.get(
        _shared_realm_organizations_url(organization_id),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    organization = r.json()
    return organization if isinstance(organization, dict) else None


def get_organization_by_alias(
    alias: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the organization representation by exact alias from the shared realm, or None when missing."""
    if not alias or not str(alias).strip():
        raise ValueError("alias is required")

    alias = str(alias).strip()
    token = admin_token or get_master_admin_token()

    def _load_organizations(**params: str) -> list[dict[str, Any]]:
        r = requests.get(
            _shared_realm_organizations_url(),
            params=params,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()

        organizations = r.json()
        if not isinstance(organizations, list):
            return []
        return [organization for organization in organizations if isinstance(organization, dict)]

    def _search_organizations(*, exact: bool) -> list[dict[str, Any]]:
        return _load_organizations(
            search=alias,
            exact="true" if exact else "false",
            briefRepresentation="false",
            max="100",
        )

    organizations = _search_organizations(exact=True)
    if not organizations:
        # Some Keycloak organization endpoints ignore or mishandle exact=true.
        # Fall back to a broader search and filter locally.
        organizations = _search_organizations(exact=False)
    if not organizations:
        # Some Keycloak builds also fail alias searches entirely for later-created
        # organizations. Fall back to a bounded list and filter locally.
        organizations = _load_organizations(
            briefRepresentation="false",
            max="100",
        )

    for organization in organizations:
        if organization.get("alias") == alias:
            return organization
    return None


def get_organization_member_by_username(
    organization_id: str,
    username: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the exact-match member representation for one organization username."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not username or not str(username).strip():
        raise ValueError("username is required")

    organization_id = str(organization_id).strip()
    normalized_username = str(username).strip()
    token = admin_token or get_master_admin_token()

    def _search_members(*, exact: bool) -> list[dict[str, Any]]:
        r = requests.get(
            _shared_realm_organizations_url(organization_id, "members"),
            params={
                "search": normalized_username,
                "exact": "true" if exact else "false",
                "max": 100,
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()

        members = r.json()
        if not isinstance(members, list):
            return []
        return [member for member in members if isinstance(member, dict)]

    members = _search_members(exact=True)
    if not members:
        # Some Keycloak organization member searches return no rows when exact=true.
        members = _search_members(exact=False)

    exact_matches = [member for member in members if member.get("username") == normalized_username]
    if len(exact_matches) != 1:
        return None
    return exact_matches[0]


def get_realm_user_by_username(
    realm: str,
    username: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the exact-match Keycloak user representation for one realm username."""
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")
    if not username or not str(username).strip():
        raise ValueError("username is required")

    normalized_realm = str(realm).strip()
    normalized_username = str(username).strip()
    token = admin_token or get_master_admin_token()

    response = requests.get(
        f"{keycloak_url()}/admin/realms/{normalized_realm}/users",
        params={
            "username": normalized_username,
            "exact": "true",
            "max": 100,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    users = response.json()
    if not isinstance(users, list):
        return None

    exact_matches = [
        user
        for user in users
        if isinstance(user, dict) and user.get("username") == normalized_username
    ]
    if len(exact_matches) != 1:
        return None
    return exact_matches[0]


def search_realm_users(
    realm: str,
    search: str,
    *,
    exact: bool = False,
    admin_token: str | None = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """Search users in one Keycloak realm and return normalized user representations."""
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")

    normalized_realm = str(realm).strip()
    normalized_search = str(search).strip() if isinstance(search, str) else ""
    token = admin_token or get_master_admin_token()
    params: dict[str, Any] = {"max": max_results}
    if normalized_search:
        params["search"] = normalized_search
        params["exact"] = "true" if exact else "false"

    response = requests.get(
        f"{keycloak_url()}/admin/realms/{normalized_realm}/users",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    users = response.json()
    if not isinstance(users, list):
        return []

    return [user for user in users if isinstance(user, dict)]


def search_organization_members(
    organization_id: str,
    search: str,
    *,
    exact: bool = False,
    admin_token: str | None = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """Search organization members in the shared realm and return normalized member representations."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    organization_id = str(organization_id).strip()
    normalized_search = str(search).strip() if isinstance(search, str) else ""
    token = admin_token or get_master_admin_token()
    params: dict[str, Any] = {"max": max_results}
    if normalized_search:
        params["search"] = normalized_search
        params["exact"] = "true" if exact else "false"

    r = requests.get(
        _shared_realm_organizations_url(organization_id, "members"),
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()

    members = r.json()
    if not isinstance(members, list):
        return []

    return [member for member in members if isinstance(member, dict)]


def add_organization_member(
    organization_id: str,
    user_id: str,
    admin_token: str | None = None,
) -> None:
    """Ensure one shared-realm user is a member of one organization."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is required")

    organization_id = str(organization_id).strip()
    user_id = str(user_id).strip()
    token = admin_token or get_master_admin_token()

    response = requests.post(
        _shared_realm_organizations_url(organization_id, "members"),
        json=user_id,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code == 409:
        logger.info(
            "User %s is already a member of organization %s; ignoring conflict.",
            user_id,
            organization_id,
        )
        return
    response.raise_for_status()


def list_organization_groups(
    organization_id: str,
    admin_token: str | None = None,
) -> list[dict[str, Any]]:
    """Return the top-level organization groups for one shared-realm organization."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    organization_id = str(organization_id).strip()
    token = admin_token or get_master_admin_token()

    response = requests.get(
        _shared_realm_organization_groups_url(organization_id),
        params={
            "briefRepresentation": "true",
            "populateHierarchy": "false",
            "subGroupsCount": "false",
            "max": 100,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    groups = response.json()
    if not isinstance(groups, list):
        return []

    return [group for group in groups if isinstance(group, dict)]


def get_organization_member_groups(
    organization_id: str,
    member_id: str,
    admin_token: str | None = None,
) -> list[dict[str, Any]]:
    """Return the organization-group memberships for one member."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not member_id or not str(member_id).strip():
        raise ValueError("member_id is required")

    organization_id = str(organization_id).strip()
    member_id = str(member_id).strip()
    token = admin_token or get_master_admin_token()

    r = requests.get(
        _shared_realm_organizations_url(organization_id, "members", quote(member_id, safe=""), "groups"),
        params={
            "briefRepresentation": "true",
            "max": 100,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()

    groups = r.json()
    if not isinstance(groups, list):
        return []

    return [group for group in groups if isinstance(group, dict)]


def list_organization_group_members(
    organization_id: str,
    group_id: str,
    admin_token: str | None = None,
) -> list[dict[str, Any]]:
    """Return the members assigned to one top-level organization group."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")

    organization_id = str(organization_id).strip()
    group_id = str(group_id).strip()
    token = admin_token or get_master_admin_token()

    response = requests.get(
        _shared_realm_organization_groups_url(
            organization_id,
            quote(group_id, safe=""),
            "members",
        ),
        params={
            "briefRepresentation": "true",
            "max": 100,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    members = response.json()
    if not isinstance(members, list):
        return []

    return [member for member in members if isinstance(member, dict)]


def get_organization_group_by_name(
    organization_id: str,
    group_name: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the exact top-level organization group representation by name."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_name or not str(group_name).strip():
        raise ValueError("group_name is required")

    organization_id = str(organization_id).strip()
    normalized_group_name = str(group_name).strip()
    token = admin_token or get_master_admin_token()

    r = requests.get(
        _shared_realm_organization_groups_url(organization_id),
        params={
            "search": normalized_group_name,
            "exact": "true",
            "briefRepresentation": "true",
            "populateHierarchy": "false",
            "subGroupsCount": "false",
            "max": 100,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()

    groups = r.json()
    if not isinstance(groups, list):
        return None

    for group in groups:
        if not isinstance(group, dict):
            continue
        if group.get("name") != normalized_group_name:
            continue
        group_path = group.get("path")
        if group_path in {None, normalized_group_name, f"/{normalized_group_name}"}:
            return group
    return None


def get_organization_group_by_id(
    organization_id: str,
    group_id: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return one top-level organization group representation by id."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")

    organization_id = str(organization_id).strip()
    group_id = str(group_id).strip()
    token = admin_token or get_master_admin_token()

    response = requests.get(
        _shared_realm_organization_groups_url(organization_id, quote(group_id, safe="")),
        params={"subGroupsCount": "false"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    organization_group = response.json()
    return organization_group if isinstance(organization_group, dict) else None


def create_organization_group(
    organization_id: str,
    group_name: str,
    admin_token: str | None = None,
) -> dict[str, Any]:
    """Create a top-level organization group and return its representation."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_name or not str(group_name).strip():
        raise ValueError("group_name is required")

    organization_id = str(organization_id).strip()
    normalized_group_name = str(group_name).strip()
    token = admin_token or get_master_admin_token()

    r = requests.post(
        _shared_realm_organization_groups_url(organization_id),
        json={"name": normalized_group_name},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()

    location_headers = getattr(r, "headers", None) or {}
    location = location_headers.get("Location")
    organization_group: dict[str, Any] | None = None
    if location and isinstance(location, str):
        group_id = location.strip().rstrip("/").split("/")[-1]
        organization_group = get_organization_group_by_id(
            organization_id,
            group_id,
            admin_token=token,
        )
    if organization_group is None:
        organization_group = get_organization_group_by_name(
            organization_id,
            normalized_group_name,
            admin_token=token,
        )
    if organization_group is None:
        raise ValueError(
            f"Keycloak created organization group '{normalized_group_name}' in organization "
            f"'{organization_id}' but it could not be fetched afterward."
        )
    return organization_group


def _organization_group_attribute_values(
    attributes: Mapping[str, Any] | None,
    attribute_name: str,
) -> tuple[str, ...]:
    if not isinstance(attributes, Mapping):
        return ()

    raw_value = attributes.get(attribute_name)
    if isinstance(raw_value, str):
        raw_values = [raw_value]
    elif isinstance(raw_value, list):
        raw_values = [value for value in raw_value if isinstance(value, str)]
    else:
        return ()

    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for raw_item in raw_values:
        for candidate_value in raw_item.split(","):
            normalized_value = candidate_value.strip()
            if not normalized_value or normalized_value in seen_values:
                continue
            seen_values.add(normalized_value)
            normalized_values.append(normalized_value)
    return tuple(normalized_values)


def _organization_group_attribute_enabled(
    attributes: Mapping[str, Any] | None,
    attribute_name: str,
) -> bool:
    normalized_values = {
        value.casefold() for value in _organization_group_attribute_values(attributes, attribute_name)
    }
    return any(value in {"1", "true", "yes", "on"} for value in normalized_values)


def organization_group_role_names(group: Mapping[str, Any] | None) -> list[str]:
    """Return M8Flow tenant roles configured for one organization group."""
    if not isinstance(group, Mapping):
        return []

    group_name = group.get("name")
    normalized_group_name = str(group_name or "").strip()
    attributes = group.get("attributes")
    if _organization_group_attribute_enabled(
        attributes if isinstance(attributes, Mapping) else None,
        ORGANIZATION_GROUP_ROLE_MAPPING_CONFIGURED_ATTRIBUTE,
    ):
        return list(
            normalize_tenant_role_names(
                _organization_group_attribute_values(
                    attributes if isinstance(attributes, Mapping) else None,
                    ORGANIZATION_GROUP_ROLE_NAMES_ATTRIBUTE,
                )
            )
        )

    return list(tenant_roles_for_organization_group(normalized_group_name))


def set_organization_group_role_names(
    organization_id: str,
    group_id: str,
    role_names: list[str] | tuple[str, ...],
    admin_token: str | None = None,
) -> dict[str, Any]:
    """Persist M8Flow tenant roles on one organization group via supported group attributes."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")

    organization_id = str(organization_id).strip()
    group_id = str(group_id).strip()
    normalized_role_names = list(normalize_tenant_role_names(role_names))
    token = admin_token or get_master_admin_token()

    organization_group = get_organization_group_by_id(
        organization_id,
        group_id,
        admin_token=token,
    )
    if not isinstance(organization_group, dict):
        raise ValueError(
            f"Organization group '{group_id}' could not be found in organization '{organization_id}'."
        )

    group_name = organization_group.get("name")
    if not isinstance(group_name, str) or not group_name.strip():
        raise ValueError(
            f"Organization group '{group_id}' in organization '{organization_id}' does not have a valid name."
        )

    existing_attributes = organization_group.get("attributes")
    updated_attributes = copy.deepcopy(existing_attributes) if isinstance(existing_attributes, dict) else {}
    updated_attributes[ORGANIZATION_GROUP_ROLE_MAPPING_CONFIGURED_ATTRIBUTE] = ["true"]
    if normalized_role_names:
        updated_attributes[ORGANIZATION_GROUP_ROLE_NAMES_ATTRIBUTE] = normalized_role_names
    else:
        updated_attributes.pop(ORGANIZATION_GROUP_ROLE_NAMES_ATTRIBUTE, None)

    payload: dict[str, Any] = {
        "name": group_name.strip(),
        "attributes": updated_attributes,
    }
    description = organization_group.get("description")
    if isinstance(description, str):
        payload["description"] = description

    response = requests.put(
        _shared_realm_organization_groups_url(organization_id, quote(group_id, safe="")),
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    refreshed_group = get_organization_group_by_id(
        organization_id,
        group_id,
        admin_token=token,
    )
    if isinstance(refreshed_group, dict):
        return refreshed_group
    payload["id"] = group_id
    return payload


def get_group_realm_role_mappings(
    group_id: str,
    admin_token: str | None = None,
    *,
    organization_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return the realm roles granted by one shared-realm group."""
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")

    group_id = str(group_id).strip()
    token = admin_token or get_master_admin_token()
    role_mappings_url = (
        _shared_realm_organization_group_role_mappings_url(str(organization_id).strip(), group_id, "composite")
        if organization_id and str(organization_id).strip()
        else f"{keycloak_url()}/admin/realms/{shared_realm_name()}/groups/{quote(group_id, safe='')}/role-mappings/realm/composite"
    )

    response = requests.get(
        role_mappings_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    role_mappings = response.json()
    if not isinstance(role_mappings, list):
        return []

    return [role_mapping for role_mapping in role_mappings if isinstance(role_mapping, dict)]


def get_realm_role_by_name(
    realm_name: str,
    role_name: str,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return one realm-role representation by exact name."""
    if not realm_name or not str(realm_name).strip():
        raise ValueError("realm_name is required")
    if not role_name or not str(role_name).strip():
        raise ValueError("role_name is required")

    normalized_realm_name = str(realm_name).strip()
    normalized_role_name = str(role_name).strip()
    token = admin_token or get_master_admin_token()

    response = requests.get(
        f"{keycloak_url()}/admin/realms/{quote(normalized_realm_name, safe='')}/roles/{quote(normalized_role_name, safe='')}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    role = response.json()
    return role if isinstance(role, dict) else None


def add_group_realm_role_mapping(
    group_id: str,
    role_name: str,
    admin_token: str | None = None,
    *,
    organization_id: str | None = None,
) -> None:
    """Grant one shared-realm role to one shared-realm group."""
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")
    if not role_name or not str(role_name).strip():
        raise ValueError("role_name is required")

    normalized_group_id = str(group_id).strip()
    normalized_role_name = str(role_name).strip()
    token = admin_token or get_master_admin_token()

    existing_role_names = {
        str(role_mapping.get("name")).strip()
        for role_mapping in get_group_realm_role_mappings(
            normalized_group_id,
            admin_token=token,
            organization_id=organization_id,
        )
        if isinstance(role_mapping.get("name"), str) and str(role_mapping.get("name")).strip()
    }
    if normalized_role_name in existing_role_names:
        return

    role = get_realm_role_by_name(shared_realm_name(), normalized_role_name, admin_token=token)
    if not isinstance(role, dict):
        raise ValueError(
            f"Realm role '{normalized_role_name}' does not exist in shared realm '{shared_realm_name()}'."
        )

    role_mappings_url = (
        _shared_realm_organization_group_role_mappings_url(
            str(organization_id).strip(),
            normalized_group_id,
        )
        if organization_id and str(organization_id).strip()
        else f"{keycloak_url()}/admin/realms/{shared_realm_name()}/groups/{quote(normalized_group_id, safe='')}/role-mappings/realm"
    )

    response = requests.post(
        role_mappings_url,
        json=[role],
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()


def remove_group_realm_role_mapping(
    group_id: str,
    role_name: str,
    admin_token: str | None = None,
    *,
    organization_id: str | None = None,
) -> None:
    """Remove one shared-realm role from one shared-realm group when present."""
    if not group_id or not str(group_id).strip():
        raise ValueError("group_id is required")
    if not role_name or not str(role_name).strip():
        raise ValueError("role_name is required")

    normalized_group_id = str(group_id).strip()
    normalized_role_name = str(role_name).strip()
    token = admin_token or get_master_admin_token()

    existing_role = next(
        (
            role_mapping
            for role_mapping in get_group_realm_role_mappings(
                normalized_group_id,
                admin_token=token,
                organization_id=organization_id,
            )
            if isinstance(role_mapping, dict)
            and isinstance(role_mapping.get("name"), str)
            and str(role_mapping.get("name")).strip() == normalized_role_name
        ),
        None,
    )
    if not isinstance(existing_role, dict):
        return

    role_mappings_url = (
        _shared_realm_organization_group_role_mappings_url(
            str(organization_id).strip(),
            normalized_group_id,
        )
        if organization_id and str(organization_id).strip()
        else f"{keycloak_url()}/admin/realms/{shared_realm_name()}/groups/{quote(normalized_group_id, safe='')}/role-mappings/realm"
    )

    response = requests.delete(
        role_mappings_url,
        json=[existing_role],
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 404:
        response.raise_for_status()


def ensure_organization_group_role_mappings(
    organization_id: str,
    *,
    admin_token: str | None = None,
) -> None:
    """Seed default M8Flow tenant-role mappings onto organization groups when unset."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    token = admin_token or get_master_admin_token()
    for group in list_organization_groups(str(organization_id).strip()):
        group_id = group.get("id")
        group_name = group.get("name")
        if not isinstance(group_id, str) or not group_id.strip():
            continue
        if not isinstance(group_name, str) or not group_name.strip():
            continue

        existing_group = get_organization_group_by_id(
            str(organization_id).strip(),
            group_id.strip(),
            admin_token=token,
        ) or group

        if _organization_group_attribute_enabled(
            existing_group.get("attributes") if isinstance(existing_group, Mapping) else None,
            ORGANIZATION_GROUP_ROLE_MAPPING_CONFIGURED_ATTRIBUTE,
        ):
            continue

        default_role_names = normalize_tenant_role_names(
            tenant_roles_for_organization_group(group_name.strip())
        )
        if not default_role_names:
            continue

        set_organization_group_role_names(
            str(organization_id).strip(),
            group_id.strip(),
            list(default_role_names),
            admin_token=token,
        )


def ensure_organization_role_groups(
    organization_id: str,
    *,
    group_names: tuple[str, ...] | None = None,
    admin_token: str | None = None,
) -> list[dict[str, Any]]:
    """Ensure the baseline organization workflow groups exist."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    organization_id = str(organization_id).strip()
    token = admin_token or get_master_admin_token()
    ensured_groups: list[dict[str, Any]] = []
    effective_group_names = group_names or default_organizational_group_names()
    for group_name in effective_group_names:
        if not group_name or not str(group_name).strip():
            continue
        normalized_group_name = str(group_name).strip()
        organization_group = get_organization_group_by_name(
            organization_id,
            normalized_group_name,
            admin_token=token,
        )
        if organization_group is None:
            logger.info(
                "Creating organization group '%s' in organization %s within shared realm %s",
                normalized_group_name,
                organization_id,
                shared_realm_name(),
            )
            organization_group = create_organization_group(
                organization_id,
                normalized_group_name,
                admin_token=token,
            )
        ensured_groups.append(organization_group)
    ensure_organization_group_role_mappings(organization_id, admin_token=token)
    return ensured_groups


def add_organization_group_member(
    organization_id: str,
    group_name: str,
    member_id: str,
    admin_token: str | None = None,
) -> None:
    """Ensure one organization member belongs to one top-level organization group."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_name or not str(group_name).strip():
        raise ValueError("group_name is required")
    if not member_id or not str(member_id).strip():
        raise ValueError("member_id is required")

    organization_id = str(organization_id).strip()
    normalized_group_name = str(group_name).strip()
    member_id = str(member_id).strip()
    token = admin_token or get_master_admin_token()

    organization_group = get_organization_group_by_name(
        organization_id,
        normalized_group_name,
        admin_token=token,
    )
    if organization_group is None:
        organization_group = create_organization_group(
            organization_id,
            normalized_group_name,
            admin_token=token,
        )

    group_id = organization_group.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ValueError(
            f"Organization group '{normalized_group_name}' in organization '{organization_id}' has no id."
        )

    response = requests.put(
        _shared_realm_organization_groups_url(
            organization_id,
            quote(group_id.strip(), safe=""),
            "members",
            quote(member_id, safe=""),
        ),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code == 409:
        logger.info(
            "Organization member %s is already assigned to organization group %s in organization %s; ignoring conflict.",
            member_id,
            normalized_group_name,
            organization_id,
        )
        return
    response.raise_for_status()


def remove_organization_group_member(
    organization_id: str,
    group_name: str,
    member_id: str,
    admin_token: str | None = None,
) -> None:
    """Remove one organization member from one top-level organization group when present."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not group_name or not str(group_name).strip():
        raise ValueError("group_name is required")
    if not member_id or not str(member_id).strip():
        raise ValueError("member_id is required")

    organization_id = str(organization_id).strip()
    normalized_group_name = str(group_name).strip()
    member_id = str(member_id).strip()
    token = admin_token or get_master_admin_token()

    organization_group = get_organization_group_by_name(
        organization_id,
        normalized_group_name,
        admin_token=token,
    )
    if organization_group is None:
        return

    group_id = organization_group.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        return

    response = requests.delete(
        _shared_realm_organization_groups_url(
            organization_id,
            quote(group_id.strip(), safe=""),
            "members",
            quote(member_id, safe=""),
        ),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 404:
        response.raise_for_status()


def create_organization(
    alias: str,
    name: str | None = None,
    *,
    enabled: bool = True,
    admin_token: str | None = None,
) -> dict[str, Any]:
    """Create an organization in the shared realm and return its representation."""
    if not alias or not str(alias).strip():
        raise ValueError("alias is required")

    alias = str(alias).strip()
    organization_name = str(name).strip() if name and str(name).strip() else alias
    token = admin_token or get_master_admin_token()

    r = requests.post(
        _shared_realm_organizations_url(),
        json={"alias": alias, "name": organization_name, "enabled": enabled},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()

    location_headers = getattr(r, "headers", None) or {}
    location = location_headers.get("Location")
    organization: dict[str, Any] | None = None
    if location and isinstance(location, str):
        organization_id = location.strip().rstrip("/").split("/")[-1]
        organization = get_organization_by_id(organization_id, admin_token=token)
    if organization is None:
        organization = get_organization_by_alias(alias, admin_token=token)
    if organization is None:
        raise ValueError(
            f"Keycloak created organization '{alias}' but it could not be fetched afterward."
        )
    ensure_organization_role_groups(organization["id"], admin_token=token)
    return organization


def update_organization(
    organization_id: str,
    *,
    alias: str,
    name: str,
    enabled: bool = True,
    admin_token: str | None = None,
) -> None:
    """Update an organization in the shared realm."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not alias or not str(alias).strip():
        raise ValueError("alias is required")
    if not name or not str(name).strip():
        raise ValueError("name is required")

    organization_id = str(organization_id).strip()
    alias = str(alias).strip()
    name = str(name).strip()
    token = admin_token or get_master_admin_token()

    r = requests.put(
        _shared_realm_organizations_url(organization_id),
        json={
            "id": organization_id,
            "alias": alias,
            "name": name,
            "enabled": enabled,
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    logger.info(
        "Updated Keycloak organization %s in shared realm %s: alias=%s name=%s",
        organization_id,
        shared_realm_name(),
        alias,
        name,
    )


def delete_organization(
    organization_id: str,
    admin_token: str | None = None,
) -> None:
    """Delete an organization in the shared realm using the provided admin token or the master admin token."""
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")

    organization_id = str(organization_id).strip()
    token = admin_token or get_master_admin_token()

    r = requests.delete(
        _shared_realm_organizations_url(organization_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code == 404:
        logger.info("Keycloak organization %s already deleted or not found.", organization_id)
        return
    r.raise_for_status()
    logger.info(
        "Deleted Keycloak organization %s from shared realm %s",
        organization_id,
        shared_realm_name(),
    )


def _list_client_protocol_mappers(
    *,
    base_url: str,
    realm_id: str,
    client_internal_id: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    mappers_url = f"{base_url}/admin/realms/{realm_id}/clients/{client_internal_id}/protocol-mappers/models"
    response = requests.get(mappers_url, headers=headers, timeout=30)
    response.raise_for_status()
    mappers = response.json()
    return mappers if isinstance(mappers, list) else []


def _list_resource_protocol_mappers(
    *,
    base_url: str,
    realm_id: str,
    resource_path: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    mappers_url = f"{base_url}/admin/realms/{realm_id}/{resource_path}/protocol-mappers/models"
    response = requests.get(mappers_url, headers=headers, timeout=30)
    response.raise_for_status()
    mappers = response.json()
    return mappers if isinstance(mappers, list) else []


def _list_client_scopes(
    *,
    base_url: str,
    realm_id: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    scopes_url = f"{base_url}/admin/realms/{realm_id}/client-scopes"
    response = requests.get(scopes_url, headers=headers, timeout=30)
    response.raise_for_status()
    scopes = response.json()
    return scopes if isinstance(scopes, list) else []


def _is_legacy_roles_as_groups_mapper(mapper: dict[str, Any]) -> bool:
    config = mapper.get("config") or {}
    return (
        mapper.get("name") == GROUPS_CLAIM_NAME
        and mapper.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        and isinstance(config, dict)
        and config.get("claim.name") == GROUPS_CLAIM_NAME
    )


def _is_roles_claim_mapper(mapper: dict[str, Any]) -> bool:
    config = mapper.get("config") or {}
    return (
        mapper.get("name") == ROLES_CLAIM_NAME
        and mapper.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        and isinstance(config, dict)
        and config.get("claim.name") == ROLES_CLAIM_NAME
    )


def _is_groups_claim_mapper(mapper: dict[str, Any]) -> bool:
    config = mapper.get("config") or {}
    if mapper.get("name") == GROUPS_CLAIM_NAME:
        return True
    return isinstance(config, dict) and config.get("claim.name") == GROUPS_CLAIM_NAME


def _is_normalized_groups_claim_mapper(mapper: dict[str, Any]) -> bool:
    config = mapper.get("config") or {}
    return (
        mapper.get("name") == GROUPS_CLAIM_NAME
        and mapper.get("protocolMapper") == NORMALIZED_GROUP_MAPPER_PROVIDER_ID
        and isinstance(config, dict)
        and config.get("claim.name") == GROUPS_CLAIM_NAME
    )


def _groups_claim_mapper_payload() -> dict[str, Any]:
    return {
        "name": GROUPS_CLAIM_NAME,
        "protocol": "openid-connect",
        "protocolMapper": NORMALIZED_GROUP_MAPPER_PROVIDER_ID,
        "consentRequired": False,
        "config": {
            "introspection.token.claim": "true",
            "multivalued": "true",
            "userinfo.token.claim": "true",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "claim.name": GROUPS_CLAIM_NAME,
            "jsonType.label": "String",
        },
    }


def _reconcile_backend_client_claim_mappers(
    *,
    base_url: str,
    realm_id: str,
    client_internal_id: str,
    headers: dict[str, str],
) -> None:
    """Remove legacy root-group mappers and ensure the separate roles claim mapper exists."""
    try:
        mappers = _list_client_protocol_mappers(
            base_url=base_url,
            realm_id=realm_id,
            client_internal_id=client_internal_id,
            headers=headers,
        )
    except Exception as exc:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: list protocol mappers realm=%s client=%s error=%s",
            realm_id,
            client_internal_id,
            exc,
        )
        return

    conflicting_group_mapper_ids = [
        mapper.get("id")
        for mapper in mappers
        if isinstance(mapper, dict) and (_is_legacy_roles_as_groups_mapper(mapper) or _is_groups_claim_mapper(mapper))
    ]
    for mapper_id in conflicting_group_mapper_ids:
        if not isinstance(mapper_id, str) or not mapper_id.strip():
            continue
        delete_url = (
            f"{base_url}/admin/realms/{realm_id}/clients/{client_internal_id}/protocol-mappers/models/{mapper_id}"
        )
        try:
            delete_response = requests.delete(delete_url, headers=headers, timeout=30)
            delete_response.raise_for_status()
            logger.info(
                "ensure_backend_redirect_uri_in_keycloak_client: removed client groups mapper realm=%s client=%s mapper_id=%s",
                realm_id,
                client_internal_id,
                mapper_id,
            )
        except Exception as exc:
            logger.warning(
                "ensure_backend_redirect_uri_in_keycloak_client: delete client groups mapper realm=%s client=%s mapper_id=%s error=%s",
                realm_id,
                client_internal_id,
                mapper_id,
                exc,
            )

    if any(isinstance(mapper, dict) and _is_roles_claim_mapper(mapper) for mapper in mappers):
        return

    create_url = f"{base_url}/admin/realms/{realm_id}/clients/{client_internal_id}/protocol-mappers/models"
    payload = {
        "name": ROLES_CLAIM_NAME,
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-realm-role-mapper",
        "consentRequired": False,
        "config": {
            "introspection.token.claim": "true",
            "multivalued": "true",
            "userinfo.token.claim": "true",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "claim.name": ROLES_CLAIM_NAME,
            "jsonType.label": "String",
        },
    }
    try:
        create_response = requests.post(create_url, json=payload, headers=headers, timeout=30)
        create_response.raise_for_status()
        logger.info(
            "ensure_backend_redirect_uri_in_keycloak_client: created roles claim mapper realm=%s client=%s",
            realm_id,
            client_internal_id,
        )
    except Exception as exc:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: create roles mapper realm=%s client=%s error=%s",
            realm_id,
            client_internal_id,
            exc,
        )


def _reconcile_groups_claim_mapper_on_resource(
    *,
    base_url: str,
    realm_id: str,
    resource_path: str,
    headers: dict[str, str],
) -> None:
    try:
        mappers = _list_resource_protocol_mappers(
            base_url=base_url,
            realm_id=realm_id,
            resource_path=resource_path,
            headers=headers,
        )
    except Exception as exc:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: list groups mappers realm=%s resource=%s error=%s",
            realm_id,
            resource_path,
            exc,
        )
        return

    conflicting_mapper_ids = [
        mapper.get("id")
        for mapper in mappers
        if isinstance(mapper, dict) and _is_groups_claim_mapper(mapper)
    ]
    for mapper_id in conflicting_mapper_ids:
        if not isinstance(mapper_id, str) or not mapper_id.strip():
            continue
        delete_url = f"{base_url}/admin/realms/{realm_id}/{resource_path}/protocol-mappers/models/{mapper_id}"
        try:
            delete_response = requests.delete(delete_url, headers=headers, timeout=30)
            delete_response.raise_for_status()
            logger.info(
                "ensure_backend_redirect_uri_in_keycloak_client: removed conflicting groups mapper realm=%s resource=%s mapper_id=%s",
                realm_id,
                resource_path,
                mapper_id,
            )
        except Exception as exc:
            logger.warning(
                "ensure_backend_redirect_uri_in_keycloak_client: delete groups mapper realm=%s resource=%s mapper_id=%s error=%s",
                realm_id,
                resource_path,
                mapper_id,
                exc,
            )


def _reconcile_profile_scope_groups_claim_mapper(
    *,
    base_url: str,
    realm_id: str,
    headers: dict[str, str],
) -> None:
    try:
        scopes = _list_client_scopes(base_url=base_url, realm_id=realm_id, headers=headers)
    except Exception as exc:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: list client scopes realm=%s error=%s",
            realm_id,
            exc,
        )
        return

    profile_scope = next(
        (
            scope
            for scope in scopes
            if isinstance(scope, dict) and scope.get("name") == "profile" and isinstance(scope.get("id"), str)
        ),
        None,
    )
    if profile_scope is None:
        return

    _reconcile_groups_claim_mapper_on_resource(
        base_url=base_url,
        realm_id=realm_id,
        resource_path=f"client-scopes/{profile_scope['id']}",
        headers=headers,
    )


def ensure_backend_redirect_uri_in_keycloak_client(realm_id: str) -> None:
    """Ensure the m8flow-backend client in the given realm has the current backend and frontend
    redirect URIs / web origins and reconcile its claim mappers. Idempotent; safe to call on every ensure_tenant_auth_config.
    Uses Keycloak Admin API; logs and skips on failure (e.g. missing admin credentials)."""
    if not realm_id or not str(realm_id).strip():
        return
    realm_id = str(realm_id).strip()
    backend_origin = _origin_from_url(
        _env_public_url("SPIFFWORKFLOW_BACKEND_URL", "M8FLOW_BACKEND_URL")
    )
    frontend_origin = _origin_from_url(
        _env_public_url("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "M8FLOW_BACKEND_URL_FOR_FRONTEND")
    )
    backend_wildcard = _wildcard_from_origin(backend_origin)
    frontend_wildcard = _wildcard_from_origin(frontend_origin)
    try:
        token = get_master_admin_token()
    except Exception as e:
        logger.debug(
            "ensure_backend_redirect_uri_in_keycloak_client: cannot get admin token for realm %s: %s",
            realm_id,
            e,
        )
        return
    base_url = keycloak_url()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    list_url = f"{base_url}/admin/realms/{realm_id}/clients?clientId={spoke_client_id()}"
    try:
        r = requests.get(list_url, headers=headers, timeout=30)
        r.raise_for_status()
        clients = r.json()
    except Exception as e:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: list clients realm=%s error=%s",
            realm_id,
            e,
        )
        return
    if not isinstance(clients, list) or len(clients) == 0:
        return
    client_internal_id = clients[0].get("id")
    if not client_internal_id:
        return

    _reconcile_backend_client_claim_mappers(
        base_url=base_url,
        realm_id=realm_id,
        client_internal_id=client_internal_id,
        headers=headers,
    )
    _reconcile_profile_scope_groups_claim_mapper(
        base_url=base_url,
        realm_id=realm_id,
        headers=headers,
    )

    if not backend_wildcard:
        return

    get_url = f"{base_url}/admin/realms/{realm_id}/clients/{client_internal_id}"
    try:
        r2 = requests.get(get_url, headers=headers, timeout=30)
        r2.raise_for_status()
        client = r2.json()
    except Exception as e:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: get client realm=%s id=%s error=%s",
            realm_id,
            client_internal_id,
            e,
        )
        return
    redirect_uris = list(client.get("redirectUris") or [])
    updated = False
    if backend_wildcard and backend_wildcard not in redirect_uris:
        redirect_uris.append(backend_wildcard)
        updated = True
    if frontend_wildcard and frontend_wildcard not in redirect_uris:
        redirect_uris.append(frontend_wildcard)
        updated = True
    if updated:
        client["redirectUris"] = _unique_strings(redirect_uris)
    web_origins = list(client.get("webOrigins") or [])
    if backend_origin and backend_origin not in web_origins:
        web_origins.append(backend_origin)
        updated = True
    if frontend_origin and frontend_origin not in web_origins:
        web_origins.append(frontend_origin)
        updated = True
    if updated:
        client["webOrigins"] = _unique_strings(web_origins)
    if not updated:
        return
    put_url = f"{base_url}/admin/realms/{realm_id}/clients/{client_internal_id}"
    try:
        r3 = requests.put(put_url, json=client, headers=headers, timeout=30)
        r3.raise_for_status()
        logger.info(
            "ensure_backend_redirect_uri_in_keycloak_client: updated redirectUris/webOrigins for client %s in realm %s",
            spoke_client_id(),
            realm_id,
        )
    except Exception as e:
        logger.warning(
            "ensure_backend_redirect_uri_in_keycloak_client: PUT client realm=%s error=%s",
            realm_id,
            e,
        )


def _fill_realm_template(
    template: dict[str, Any], realm_id: str, display_name: str | None, template_name: str
) -> dict[str, Any]:
    """
    Return a deep copy of the realm template with only the necessary values updated for the new tenant.
    Preserves users, roles, groups, clients, and all other structure from the realm template JSON.
    """
    payload = copy.deepcopy(template)

    # Top-level realm identifiers. Omit "id" on create so Keycloak auto-generates it (avoids 409 Conflict).
    payload["realm"] = realm_id
    payload["displayName"] = display_name if display_name else realm_id
    payload.pop("id", None)
    payload["groups"] = _merge_default_organizational_groups(
        payload.get("groups") or [],
        load_default_organizational_group_paths(),
    )

    backend_origin = _origin_from_url(
        _env_public_url("SPIFFWORKFLOW_BACKEND_URL", "M8FLOW_BACKEND_URL")
    )
    frontend_origin = _origin_from_url(
        _env_public_url("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "M8FLOW_BACKEND_URL_FOR_FRONTEND")
    )
    backend_wildcard = _wildcard_from_origin(backend_origin)
    frontend_wildcard = _wildcard_from_origin(frontend_origin)

    default_role_name_old = f"{DEFAULT_ROLES_PREFIX}{template_name}"
    default_role_name_new = f"{DEFAULT_ROLES_PREFIX}{realm_id}"
    realm_url_old = f"{REALM_URL_PREFIX}{template_name}/"
    realm_url_new = f"{REALM_URL_PREFIX}{realm_id}/"
    admin_console_url_old = f"{ADMIN_CONSOLE_URL_PREFIX}{template_name}/"
    admin_console_url_new = f"{ADMIN_CONSOLE_URL_PREFIX}{realm_id}/"

    # Realm roles: containerId (realm id) and default role name
    roles = payload.get("roles") or {}
    for role in roles.get("realm") or []:
        if role.get("containerId") == template_name:
            role["containerId"] = realm_id
        if role.get("name") == default_role_name_old:
            role["name"] = default_role_name_new

    # defaultRole (top-level default role reference)
    default_role = payload.get("defaultRole")
    if isinstance(default_role, dict):
        if default_role.get("containerId") == template_name:
            default_role["containerId"] = realm_id
        if default_role.get("name") == default_role_name_old:
            default_role["name"] = default_role_name_new

    # Users: realmRoles array (reference to default-roles-{realm})
    for user in payload.get("users") or []:
        realm_roles = user.get("realmRoles")
        if isinstance(realm_roles, list):
            user["realmRoles"] = [
                default_role_name_new if r == default_role_name_old else r for r in realm_roles
            ]

    # Clients: URLs containing /realms/{realm}/ or /admin/{realm}/
    def _replace_realm_urls(s: str) -> str:
        if realm_url_old in s:
            s = s.replace(realm_url_old, realm_url_new)
        if admin_console_url_old in s:
            s = s.replace(admin_console_url_old, admin_console_url_new)
        return s

    for client in payload.get("clients") or []:
        for key in ("baseUrl", "adminUrl", "rootUrl"):
            if isinstance(client.get(key), str):
                client[key] = _replace_realm_urls(client[key])
        for key in ("redirectUris", "webOrigins"):
            uris = client.get(key)
            if isinstance(uris, list):
                client[key] = [
                    _replace_realm_urls(u) if isinstance(u, str) else u for u in uris
                ]
        attrs = client.get("attributes") or {}
        if isinstance(attrs, dict):
            for k, v in list(attrs.items()):
                if isinstance(v, str):
                    attrs[k] = _replace_runtime_url_placeholders(
                        _replace_realm_urls(v),
                        backend_wildcard=backend_wildcard,
                        frontend_wildcard=frontend_wildcard,
                    )
            client["attributes"] = attrs
        _apply_runtime_client_urls(
            client,
            backend_origin=backend_origin,
            backend_wildcard=backend_wildcard,
            frontend_origin=frontend_origin,
            frontend_wildcard=frontend_wildcard,
        )

    backend_val = redirect_uri_backend_host_and_path()
    frontend_val = redirect_uri_frontend_host()
    _replace_redirect_placeholders_in_place(payload, backend_val, frontend_val)

    return payload


def _sanitize_roles_for_partial_import(roles: dict[str, Any]) -> dict[str, Any]:
    """Strip id and containerId from realm and client roles so Keycloak can assign new ones."""
    out = copy.deepcopy(roles)
    if "realm" in out:
        out["realm"] = _sanitize_realm_roles_for_partial_import(out.get("realm") or [])
    _sanitize_client_roles_for_partial_import(out.get("client"))
    return out


def _sanitize_role_identifiers(role: Any) -> None:
    if isinstance(role, dict):
        role.pop("id", None)
        role.pop("containerId", None)


def _sanitize_realm_roles_for_partial_import(realm_roles: list[Any]) -> list[Any]:
    sanitized_roles = []
    for role in realm_roles:
        if isinstance(role, dict) and role.get("name") in GLOBAL_ONLY_REALM_ROLE_NAMES:
            continue
        _sanitize_role_identifiers(role)
        sanitized_roles.append(role)
    return sanitized_roles


def _sanitize_client_roles_for_partial_import(client_roles: Any) -> None:
    if not isinstance(client_roles, dict):
        return
    for role_list in client_roles.values():
        if not isinstance(role_list, list):
            continue
        for role in role_list:
            _sanitize_role_identifiers(role)


def _sanitize_groups_for_partial_import(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively strip id from groups and subGroups for partial import."""
    out = copy.deepcopy(groups)

    def _strip_group_ids(g: dict[str, Any]) -> None:
        g.pop("id", None)
        for sub in g.get("subGroups") or []:
            if isinstance(sub, dict):
                _strip_group_ids(sub)

    for group in out:
        if isinstance(group, dict):
            _strip_group_ids(group)
    return out


def _sanitize_user_realm_roles(user: dict[str, Any]) -> None:
    realm_roles = user.get("realmRoles")
    if not isinstance(realm_roles, list):
        return
    user["realmRoles"] = [role for role in realm_roles if role not in GLOBAL_ONLY_REALM_ROLE_NAMES]


def _sanitize_user_credential(credential: Any) -> None:
    if isinstance(credential, dict):
        credential.pop("id", None)


def _sanitize_user_for_partial_import(user: Any) -> dict[str, Any] | Any | None:
    if not isinstance(user, dict):
        return user
    if user.get("username") in GLOBAL_ONLY_USERNAMES:
        return None

    user.pop("id", None)
    _sanitize_user_realm_roles(user)
    for credential in user.get("credentials") or []:
        _sanitize_user_credential(credential)
    return user


def _sanitize_users_for_partial_import(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip id from users and their credentials for partial import."""
    out = copy.deepcopy(users)
    sanitized_users = []
    for user in out:
        sanitized_user = _sanitize_user_for_partial_import(user)
        if sanitized_user is not None:
            sanitized_users.append(sanitized_user)
    return sanitized_users


def _sanitize_client_scopes_for_partial_import(scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip id from client scopes and their protocol mappers for partial import."""
    out = copy.deepcopy(scopes)
    for scope in out:
        if isinstance(scope, dict):
            scope.pop("id", None)
            for mapper in scope.get("protocolMappers") or []:
                if isinstance(mapper, dict):
                    mapper.pop("id", None)
    return out


def _sanitize_idps_for_partial_import(idps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip internal id from identity providers for partial import."""
    out = copy.deepcopy(idps)
    for idp in out:
        if isinstance(idp, dict):
            idp.pop("internalId", None)
    return out


def _minimal_realm_creation_payload(full_payload: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "realm": full_payload.get("realm"),
        "displayName": full_payload.get("displayName"),
        "enabled": full_payload.get("enabled", True),
        "sslRequired": full_payload.get("sslRequired", "none"),
        # Carry the realm-level registration flag from the template so new tenant
        # realms expose the "Register" link on the login screen. partialImport does
        # not apply realm-level settings, so this must be set on initial creation.
        "registrationAllowed": full_payload.get("registrationAllowed", False),
    }

    login_theme = full_payload.get("loginTheme")
    if login_theme:
        payload["loginTheme"] = login_theme

    return payload


def _certificate_pem_or_none(client_id_to_find: str) -> str | None:
    try:
        return _get_certificate_pem_from_p12()
    except Exception as e:
        logger.warning(f"Could not configure JWT certificate for client {client_id_to_find}: {e}")
        return None


def _configure_spoke_client_authentication(client: dict[str, Any], client_id_to_find: str) -> None:
    if client.get("clientId") != client_id_to_find:
        return

    cert_pem = _certificate_pem_or_none(client_id_to_find)
    if not cert_pem:
        return

    client["clientAuthenticatorType"] = "client-jwt"
    client.pop("secret", None)
    if "attributes" not in client:
        client["attributes"] = {}
    client["attributes"]["jwt.credential.certificate"] = cert_pem


def _sanitize_client_for_partial_import(client: dict[str, Any], *, client_id_to_find: str) -> None:
    client.pop("id", None)

    for mapper in client.get("protocolMappers", []):
        if isinstance(mapper, dict):
            mapper.pop("id", None)

    # Strip authorization (UMA) settings to avoid Keycloak FK violation during sync:
    # RESOURCE_SCOPE.SCOPE_ID -> RESOURCE_SERVER_SCOPE.ID delete order can trigger
    # ModelDuplicateException / JdbcBatchUpdateException in ClientApplicationSynchronizer.
    client.pop("authorizationSettings", None)
    if client.get("authorizationServicesEnabled") is True:
        client["authorizationServicesEnabled"] = False

    _configure_spoke_client_authentication(client, client_id_to_find)


def _partial_import_payload(full_payload: dict[str, Any]) -> dict[str, Any]:
    clients = copy.deepcopy(full_payload.get("clients", []))
    client_id_to_find = spoke_client_id()
    for client in clients:
        _sanitize_client_for_partial_import(client, client_id_to_find=client_id_to_find)
    # Prepare tenant-safe partial import payload: ids stripped, global-only roles/users removed.
    return {
        "ifResourceExists": "SKIP",
        "clients": clients,
        "roles": _sanitize_roles_for_partial_import(full_payload.get("roles") or {}),
        "groups": _sanitize_groups_for_partial_import(full_payload.get("groups") or []),
        "users": _sanitize_users_for_partial_import(full_payload.get("users") or []),
        "clientScopes": _sanitize_client_scopes_for_partial_import(full_payload.get("clientScopes") or []),
        "identityProviders": _sanitize_idps_for_partial_import(full_payload.get("identityProviders") or []),
        "defaultDefaultClientScopes": full_payload.get("defaultDefaultClientScopes", []),
        "defaultOptionalClientScopes": full_payload.get("defaultOptionalClientScopes", []),
    }


def load_realm_template() -> dict[str, Any]:
    """Load the realm template JSON (m8flow-tenant-template.json). Placeholder __M8FLOW_SPOKE_CLIENT_ID__ is replaced with spoke_client_id() from env."""
    template_path = realm_template_path()
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Realm template not found: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)
    return _substitute_spoke_client_id(template, spoke_client_id())


def create_realm_from_template(realm_id: str, display_name: str | None = None) -> dict:
    """
    Create a new tenant realm from the template in two steps:
    1. Create minimal realm (realm name, displayName, enabled)
    2. Use Keycloak partial import to add clients, roles, groups, and users from template
    """
    if not realm_id or not realm_id.strip():
        raise ValueError("realm_id is required")
    realm_id = realm_id.strip()
    logger.debug(
        "create_realm_from_template: realm_id=%r keycloak_url=%s",
        realm_id,
        keycloak_url(),
    )
    template = load_realm_template()
    # Detect template realm name from JSON if present, else fallback to config
    template_name = template.get("realm") or template_realm_name()
    full_payload = _fill_realm_template(template, realm_id, display_name, template_name)

    # Step 1: Create minimal realm first (avoids 500 error from full template)
    minimal_payload = _minimal_realm_creation_payload(full_payload)

    token = get_master_admin_token()
    _log_admin_token_claims(token)
    base_url = keycloak_url()

    r = requests.post(
        f"{base_url}/admin/realms",
        json=minimal_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    logger.debug(
        "create_realm_from_template step 1 OK: POST /admin/realms -> %s",
        r.status_code,
    )

    # Step 2: Partial import of clients, roles, groups, and users from template.
    # Sanitize ids/containerIds so Keycloak can assign new ones and avoid conflicts.
    partial_import_payload = _partial_import_payload(full_payload)

    partial_import_url = f"{base_url}/admin/realms/{realm_id}/partialImport"
    clients_count = len(partial_import_payload.get("clients", []))
    roles_obj = partial_import_payload.get("roles", {}) or {}
    roles_count = len(roles_obj.get("realm", [])) + len(roles_obj.get("client", {}))
    users_count = len(partial_import_payload.get("users", []))
    logger.debug(
        "create_realm_from_template step 2: POST %s (clients=%s roles=%s users=%s)",
        partial_import_url,
        clients_count,
        roles_count,
        users_count,
    )
    r2 = requests.post(
        partial_import_url,
        json=partial_import_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=120,
    )
    if not r2.ok:
        logger.warning(
            "create_realm_from_template step 2 FAILED: partialImport %s %s url=%s body=%s",
            r2.status_code,
            r2.reason,
            r2.url,
            (r2.text[:500] if r2.text else None),
        )
    r2.raise_for_status()

    # Ensure realm-level settings that partialImport doesn't cover are applied.
    login_theme = full_payload.get("loginTheme")
    if login_theme:
        r_theme = requests.put(
            f"{base_url}/admin/realms/{realm_id}",
            json={"loginTheme": login_theme},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        r_theme.raise_for_status()

    # Partial import skips built-in scopes like "profile" when they already exist in the
    # new realm, so reconcile the client/group claim mappers explicitly before first login.
    ensure_backend_redirect_uri_in_keycloak_client(realm_id)

    # Step 3: Fetch realm to obtain Keycloak's internal UUID (used as M8flowTenantModel.id)
    r3 = requests.get(
        f"{base_url}/admin/realms/{realm_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r3.raise_for_status()
    realm_json = r3.json()
    keycloak_realm_id = realm_json.get("id")
    if not keycloak_realm_id:
        raise ValueError(
            f"Keycloak did not return realm id for realm {realm_id!r}. Cannot persist tenant."
        )

    return {
        "realm": realm_id,
        "displayName": full_payload.get("displayName", ""),
        "keycloak_realm_id": keycloak_realm_id,
    }


def tenant_login(realm: str, username: str, password: str) -> dict:
    """
    Login as a user in a spoke realm (resource owner password grant).
    Uses JWT client assertion from the configured PKCS#12 keystore (keystore.p12). Returns token response.
    """
    if not realm or not username:
        raise ValueError("realm and username are required")
    url = f"{keycloak_url()}/realms/{realm}/protocol/openid-connect/token"
    client_id = spoke_client_id()
    data = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": _build_client_assertion_jwt(url, realm),
    }
    r = requests.post(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
        allow_redirects=False,
    )
    r.raise_for_status()
    return r.json()


def create_user_in_realm(
    realm: str,
    username: str,
    password: str,
    email: str | None = None,
    enabled: bool = True,
) -> str:
    """Create user in spoke realm via Admin API. Returns user id (UUID)."""
    if not realm or not username:
        raise ValueError("realm and username are required")
    token = get_master_admin_token()
    base_url = keycloak_url()
    
    # Step 1: Create user
    url = f"{base_url}/admin/realms/{realm}/users"
    payload = {
        "username": username,
        "enabled": enabled,
        "emailVerified": True,  # Mark email as verified
        "firstName": username,  # Keycloak 24.0+ may require firstName/lastName
        "lastName": "User",  # Set a default lastName
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    if email:
        payload["email"] = email
    r = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    location = r.headers.get("Location")
    if not (location and location.strip()):
        raise ValueError(
            "Keycloak did not return a Location header when creating user; "
            "check Keycloak version and configuration"
        )
    user_id = location.strip().rstrip("/").split("/")[-1]

    # Step 2: Fetch user and update to clear required actions
    # Keycloak may add default required actions, so we need to explicitly clear them
    get_url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
    r_get = requests.get(
        get_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r_get.raise_for_status()
    user_data = r_get.json()
    
    # Clear required actions and ensure emailVerified is True
    # Also ensure firstName/lastName are set (Keycloak 24.0+ requirement)
    user_data["requiredActions"] = []
    user_data["emailVerified"] = True
    if not user_data.get("firstName"):
        user_data["firstName"] = username
    if not user_data.get("lastName"):
        user_data["lastName"] = "User"

    r2 = requests.put(
        get_url,
        json=user_data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r2.raise_for_status()

    return user_id


def delete_realm(realm_id: str, admin_token: str | None = None) -> None:
    """Delete a realm in Keycloak using the provided admin token or the master admin token."""
    if not realm_id or not str(realm_id).strip():
        raise ValueError("realm_id is required")
    realm_id = str(realm_id).strip()
    
    token = admin_token or get_master_admin_token()
    base_url = keycloak_url()

    r = requests.delete(
        f"{base_url}/admin/realms/{realm_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code == 404:
        logger.info("Keycloak realm %s already deleted or not found.", realm_id)
        return
    r.raise_for_status()
    logger.info("Deleted Keycloak realm: %s", realm_id)


def update_realm(realm_id: str, display_name: str, admin_token: str | None = None) -> None:
    """Update a realm in Keycloak (specifically displayName)."""
    if not realm_id or not str(realm_id).strip():
        raise ValueError("realm_id is required")

    if not display_name or not str(display_name).strip():
        raise ValueError("display_name is required")
    
    if not admin_token or not str(admin_token).strip():
        raise ValueError("admin_token is required")

    realm_id = str(realm_id).strip()
    display_name = str(display_name).strip()
    admin_token = str(admin_token).strip()

    base_url = keycloak_url()

    payload = {
        "realm": realm_id,
        "displayName": display_name
    }

    r = requests.put(
        f"{base_url}/admin/realms/{realm_id}",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    logger.info("Updated Keycloak realm %s: displayName=%s", realm_id, display_name)


def verify_admin_token(token: str) -> bool:
    """
    Verify that the provided token is a valid admin token.
    We check this by calling the master realm info endpoint.
    """
    if not token:
        return False
    base_url = keycloak_url()
    try:
        r = requests.get(
            f"{base_url}/admin/realms/master",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False
