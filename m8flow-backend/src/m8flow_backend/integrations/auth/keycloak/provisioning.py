"""Keycloak realm provisioning: template import, mappers, client redirect URIs.

Spoke-realm create/delete/update plus protocol-mapper reconciliation live
here. The provider exposes them through ``SupportsProvisioning``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
from m8flow_backend.integrations.auth.keycloak.admin_client import KeycloakAdminClient
from m8flow_backend.integrations.auth.keycloak.client_auth import fetch_master_admin_token
from m8flow_backend.integrations.auth.keycloak.settings import keycloak_url, spoke_client_id, template_realm_name
from m8flow_backend.integrations.auth.keycloak.realm_template import (
    GROUPS_CLAIM_NAME,
    NORMALIZED_GROUP_MAPPER_PROVIDER_ID,
    ROLES_CLAIM_NAME,
    _fill_realm_template,
    _minimal_realm_creation_payload,
    _origin_from_url,
    _partial_import_payload,
    _unique_strings,
    _wildcard_from_origin,
    load_realm_template,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 30


def _env_public_url(*keys: str) -> str | None:
    import os

    for key in keys:
        value = os.environ.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return None


def _realm_name(tenant_ref: TenantRef) -> str:
    name = tenant_ref.alias or tenant_ref.id
    if not name or not str(name).strip():
        raise ValueError("tenant_ref.alias or tenant_ref.id is required")
    return str(name).strip()


def _unavailable(action: str, exc: Exception) -> ProviderUnavailable:
    error = ProviderUnavailable(f"Could not {action}")
    error.__cause__ = exc
    return error


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
        token = fetch_master_admin_token()
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

    try:
        token = fetch_master_admin_token()
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

    except requests.RequestException as exc:
        raise ProviderUnavailable(f"Could not create tenant realm {realm_id!r}") from exc

    return {
        "realm": realm_id,
        "displayName": full_payload.get("displayName", ""),
        "keycloak_realm_id": keycloak_realm_id,
    }

def delete_realm(realm_id: str, admin_token: str | None = None) -> None:
    """Delete a realm in Keycloak using the provided admin token or the master admin token."""
    if not realm_id or not str(realm_id).strip():
        raise ValueError("realm_id is required")
    realm_id = str(realm_id).strip()
    response = KeycloakAdminClient(admin_token=admin_token).delete(
        realm_id,
        tolerate=(404,),
        context=f"delete tenant realm {realm_id!r}",
    )
    if response.status_code == 404:
        logger.info("Keycloak realm %s already deleted or not found.", realm_id)
        return
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

    KeycloakAdminClient(admin_token=admin_token).put(
        realm_id,
        json={"realm": realm_id, "displayName": display_name},
        context=f"update tenant realm {realm_id!r}",
    )
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



class KeycloakProvisioning:
    """Keycloak realization of ``SupportsProvisioning``."""

    def create_tenant_realm(self, tenant_ref: TenantRef, *, display_name: str | None = None) -> Tenant:
        realm_id = _realm_name(tenant_ref)
        result = create_realm_from_template(realm_id, display_name)
        display = result.get("displayName") or display_name or realm_id
        return Tenant(
            ref=TenantRef(
                id=str(result.get("keycloak_realm_id") or "") or None,
                alias=result.get("realm") or realm_id,
                name=display,
            ),
            display_name=display,
        )

    def delete_tenant_realm(self, tenant_ref: TenantRef) -> None:
        delete_realm(_realm_name(tenant_ref))

    def update_tenant_realm(self, tenant_ref: TenantRef, *, display_name: str) -> Tenant:
        realm_id = _realm_name(tenant_ref)
        delete_token = fetch_master_admin_token()
        update_realm(realm_id, display_name, admin_token=delete_token)
        return Tenant(
            ref=TenantRef(id=tenant_ref.id, alias=realm_id, name=display_name),
            display_name=display_name,
        )

    def ensure_client_redirect_uri(self, tenant_ref: TenantRef, *, redirect_uri: str) -> None:
        realm_id = _realm_name(tenant_ref)
        ensure_backend_redirect_uri_in_keycloak_client(realm_id)
        extra = (redirect_uri or "").strip()
        if extra:
            _ensure_extra_redirect_uri(realm_id, extra)


def _ensure_extra_redirect_uri(realm_id: str, redirect_uri: str) -> None:
    """Append one explicit redirect URI onto the spoke client if missing."""
    try:
        token = fetch_master_admin_token()
    except Exception:
        return
    base_url = keycloak_url()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    list_url = f"{base_url}/admin/realms/{realm_id}/clients?clientId={spoke_client_id()}"
    try:
        response = requests.get(list_url, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        clients = response.json()
    except Exception as exc:
        logger.warning("ensure_client_redirect_uri: list clients realm=%s error=%s", realm_id, exc)
        return
    if not isinstance(clients, list) or not clients:
        return
    client_id = clients[0].get("id")
    if not client_id:
        return
    get_url = f"{base_url}/admin/realms/{realm_id}/clients/{client_id}"
    try:
        response = requests.get(get_url, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        client = response.json()
    except Exception as exc:
        logger.warning("ensure_client_redirect_uri: get client realm=%s error=%s", realm_id, exc)
        return
    redirect_uris = list(client.get("redirectUris") or [])
    if redirect_uri in redirect_uris:
        return
    redirect_uris.append(redirect_uri)
    client["redirectUris"] = _unique_strings(redirect_uris)
    try:
        response = requests.put(get_url, json=client, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("ensure_client_redirect_uri: PUT client realm=%s error=%s", realm_id, exc)

