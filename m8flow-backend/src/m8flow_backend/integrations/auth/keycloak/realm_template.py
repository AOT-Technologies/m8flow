"""Realm-template load/fill/sanitize for Keycloak spoke-realm provisioning.

The JSON export stays on disk (out of scope); this module is the reader and
the Keycloak-specific rewrite applied before create + partialImport.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from m8flow_backend.config import redirect_uri_backend_host_and_path, redirect_uri_frontend_host
from m8flow_backend.integrations.auth.keycloak.settings import (
    keycloak_default_groups_path,
    realm_template_path,
    spoke_client_id,
)
from m8flow_backend.auth.identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.auth.identity_helpers import normalize_organizational_group_identifiers

logger = logging.getLogger(__name__)

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


def _retarget_realm_roles(
    payload: dict[str, Any],
    *,
    template_name: str,
    realm_id: str,
    default_role_name_old: str,
    default_role_name_new: str,
) -> None:
    """Rewrite each realm role's containerId (realm id) and default role name."""
    roles = payload.get("roles") or {}
    for role in roles.get("realm") or []:
        if role.get("containerId") == template_name:
            role["containerId"] = realm_id
        if role.get("name") == default_role_name_old:
            role["name"] = default_role_name_new


def _rename_default_role(
    payload: dict[str, Any],
    *,
    template_name: str,
    realm_id: str,
    default_role_name_old: str,
    default_role_name_new: str,
) -> None:
    """Rewrite the top-level defaultRole reference's containerId and name."""
    default_role = payload.get("defaultRole")
    if isinstance(default_role, dict):
        if default_role.get("containerId") == template_name:
            default_role["containerId"] = realm_id
        if default_role.get("name") == default_role_name_old:
            default_role["name"] = default_role_name_new


def _rewrite_user_realm_roles(
    payload: dict[str, Any],
    *,
    default_role_name_old: str,
    default_role_name_new: str,
) -> None:
    """Rewrite each user's realmRoles array (reference to default-roles-{realm})."""
    for user in payload.get("users") or []:
        realm_roles = user.get("realmRoles")
        if isinstance(realm_roles, list):
            user["realmRoles"] = [
                default_role_name_new if r == default_role_name_old else r for r in realm_roles
            ]


def _rewrite_client_urls(
    payload: dict[str, Any],
    *,
    realm_url_old: str,
    realm_url_new: str,
    admin_console_url_old: str,
    admin_console_url_new: str,
    backend_origin: str | None,
    backend_wildcard: str | None,
    frontend_origin: str | None,
    frontend_wildcard: str | None,
) -> None:
    """Rewrite client URLs containing /realms/{realm}/ or /admin/{realm}/."""

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

    _retarget_realm_roles(
        payload,
        template_name=template_name,
        realm_id=realm_id,
        default_role_name_old=default_role_name_old,
        default_role_name_new=default_role_name_new,
    )

    _rename_default_role(
        payload,
        template_name=template_name,
        realm_id=realm_id,
        default_role_name_old=default_role_name_old,
        default_role_name_new=default_role_name_new,
    )

    _rewrite_user_realm_roles(
        payload,
        default_role_name_old=default_role_name_old,
        default_role_name_new=default_role_name_new,
    )

    _rewrite_client_urls(
        payload,
        realm_url_old=realm_url_old,
        realm_url_new=realm_url_new,
        admin_console_url_old=admin_console_url_old,
        admin_console_url_new=admin_console_url_new,
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
        # Carry the realm-level registration flag from the template onto the new
        # tenant realm. partialImport does not apply realm-level settings, so this
        # must be set explicitly at creation time to match the template's value.
        "registrationAllowed": full_payload.get("registrationAllowed", False),
    }

    login_theme = full_payload.get("loginTheme")
    if login_theme:
        payload["loginTheme"] = login_theme

    return payload


def _certificate_pem_or_none(client_id_to_find: str) -> str | None:
    try:
        from m8flow_backend.integrations.auth.keycloak.client_auth import spoke_certificate_pem

        return spoke_certificate_pem()
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


