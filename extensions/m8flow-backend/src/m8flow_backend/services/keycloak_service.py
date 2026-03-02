"""Keycloak service: master token, create realm from template, tenant login, create user in realm."""
from __future__ import annotations

import copy
import json
import logging
import time
import uuid
import warnings
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

from m8flow_backend.config import (
    keycloak_admin_password,
    keycloak_admin_user,
    keycloak_url,
    realm_template_path,
    spoke_client_id,
    spoke_client_secret,
    spoke_keystore_password,
    spoke_keystore_p12_path,
    template_realm_name,
)

# Template source: extensions/m8flow-backend/keycloak/realm_exports/spiffworkflow-realm.json
# Only necessary values are changed for a new tenant; roles, groups, users, and clients are preserved.
# Placeholder in the JSON is replaced at load time with M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID (default: spiffworkflow-backend).
SPOKE_CLIENT_ID_PLACEHOLDER = "__M8FLOW_SPOKE_CLIENT_ID__"
DEFAULT_ROLES_PREFIX = "default-roles-"  # role name "default-roles-{realm}" must be updated
REALM_URL_PREFIX = "/realms/"  # client baseUrl/redirectUris contain /realms/{realm}/
ADMIN_CONSOLE_URL_PREFIX = "/admin/"  # security-admin-console has /admin/{realm}/console/


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
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": keycloak_admin_user(),
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
        logger.warning(
            "realm_exists: realm=%s url=%s status=%s (check KEYCLOAK_URL if realm exists in browser)",
            realm,
            discovery_url,
            r.status_code,
        )
        if r.status_code != 200 and r.text:
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
                    attrs[k] = _replace_realm_urls(v)
            client["attributes"] = attrs

    return payload


def _sanitize_roles_for_partial_import(roles: dict[str, Any]) -> dict[str, Any]:
    """Strip id and containerId from realm and client roles so Keycloak can assign new ones."""
    out = copy.deepcopy(roles)
    for role in out.get("realm") or []:
        if isinstance(role, dict):
            role.pop("id", None)
            role.pop("containerId", None)
    for client_id, role_list in (out.get("client") or {}).items():
        if isinstance(role_list, list):
            for role in role_list:
                if isinstance(role, dict):
                    role.pop("id", None)
                    role.pop("containerId", None)
    return out


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


def _sanitize_users_for_partial_import(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip id from users and their credentials for partial import."""
    out = copy.deepcopy(users)
    for user in out:
        if isinstance(user, dict):
            user.pop("id", None)
            for cred in user.get("credentials") or []:
                if isinstance(cred, dict):
                    cred.pop("id", None)
    return out


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


def load_realm_template() -> dict[str, Any]:
    """Load the realm template JSON (spiffworkflow-realm.json). Placeholder __M8FLOW_SPOKE_CLIENT_ID__ is replaced with spoke_client_id() from env."""
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
    template = load_realm_template()
    # Detect template realm name from JSON if present, else fallback to config
    template_name = template.get("realm") or template_realm_name()
    full_payload = _fill_realm_template(template, realm_id, display_name, template_name)
    
    # Step 1: Create minimal realm first (avoids 500 error from full template)
    minimal_payload = {
        "realm": full_payload.get("realm"),
        "displayName": full_payload.get("displayName"),
        "enabled": full_payload.get("enabled", True),
        "sslRequired": full_payload.get("sslRequired", "none"),
    }
    
    token = get_master_admin_token()
    base_url = keycloak_url()

    r = requests.post(
        f"{base_url}/admin/realms",
        json=minimal_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    
    # Step 2: Partial import of clients, roles, groups, and users from template.
    # Sanitize ids/containerIds so Keycloak can assign new ones and avoid conflicts.
    clients = copy.deepcopy(full_payload.get("clients", []))
    client_id_to_find = spoke_client_id()
    for client in clients:
        # Remove id and all nested ids
        client.pop("id", None)
        # Remove protocol mappers ids (they cause conflicts)
        for mapper in client.get("protocolMappers", []):
            if isinstance(mapper, dict):
                mapper.pop("id", None)
        # Strip authorization (UMA) settings to avoid Keycloak FK violation during sync:
        # RESOURCE_SCOPE.SCOPE_ID -> RESOURCE_SERVER_SCOPE.ID delete order can trigger
        # ModelDuplicateException / JdbcBatchUpdateException in ClientApplicationSynchronizer.
        client.pop("authorizationSettings", None)
        if client.get("authorizationServicesEnabled") is True:
            client["authorizationServicesEnabled"] = False

        # Configure spiffworkflow-backend client for JWT authentication (only when keystore is available)
        if client.get("clientId") == client_id_to_find:
            cert_pem = None
            try:
                cert_pem = _get_certificate_pem_from_p12()
            except Exception as e:
                logger.warning(f"Could not configure JWT certificate for client {client_id_to_find}: {e}")
            if cert_pem:
                client["clientAuthenticatorType"] = "client-jwt"
                client.pop("secret", None)
                if "attributes" not in client:
                    client["attributes"] = {}
                client["attributes"]["jwt.credential.certificate"] = cert_pem
            else:
                # Keystore missing: leave client as confidential with secret so upstream Basic auth token exchange works
                pass  # do not set client-jwt, do not remove secret
    
    roles = _sanitize_roles_for_partial_import(full_payload.get("roles") or {})
    groups = _sanitize_groups_for_partial_import(full_payload.get("groups") or [])
    users = _sanitize_users_for_partial_import(full_payload.get("users") or [])
    client_scopes = _sanitize_client_scopes_for_partial_import(full_payload.get("clientScopes") or [])
    idps = _sanitize_idps_for_partial_import(full_payload.get("identityProviders") or [])

    partial_import_payload = {
        "ifResourceExists": "SKIP",
        "clients": clients,
        "roles": roles,
        "groups": groups,
        "users": users,
        "clientScopes": client_scopes,
        "identityProviders": idps,
        "defaultDefaultClientScopes": full_payload.get("defaultDefaultClientScopes", []),
        "defaultOptionalClientScopes": full_payload.get("defaultOptionalClientScopes", []),
    }

    r2 = requests.post(
        f"{base_url}/admin/realms/{realm_id}/partialImport",
        json=partial_import_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=120,
    )
    r2.raise_for_status()

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
    user_id = r.headers["Location"].split("/")[-1]
    
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
