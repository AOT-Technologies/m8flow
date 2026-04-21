"""Keycloak service: master token, create realm from template, tenant login, create user in realm."""
from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

from m8flow_backend.config import (
    keycloak_admin_password,
    keycloak_admin_user,
    keycloak_url,
    realm_template_path,
    redirect_uri_backend_host_and_path,
    redirect_uri_frontend_host,
    spoke_client_id,
    spoke_keystore_password,
    spoke_keystore_p12_path,
    template_realm_name,
)

# Template source: extensions/m8flow-backend/keycloak/realm_exports/m8flow-tenant-template.json
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
            "Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 to extensions/m8flow-backend/keystore.p12 (or absolute path) for spoke tenant auth."
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


def ensure_backend_redirect_uri_in_keycloak_client(realm_id: str) -> None:
    """Ensure the m8flow-backend client in the given realm has the current backend and frontend
    redirect URIs / web origins. Idempotent; safe to call on every ensure_tenant_auth_config.
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
    if not backend_wildcard:
        return
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
