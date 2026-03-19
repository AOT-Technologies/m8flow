"""Keycloak API controller: create realm, tenant login, create user in realm."""
from __future__ import annotations

import logging

import requests

from m8flow_backend.services.keycloak_service import (
    create_realm_from_template,
    create_user_in_realm as create_user_in_realm_svc,
    delete_realm,
    realm_exists,
    tenant_login as tenant_login_svc,
    tenant_login_authorization_url,
    update_realm,
    verify_admin_token,
    get_master_admin_token,
)
from sqlalchemy.exc import IntegrityError
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authorization_service import AuthorizationService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors

from m8flow_backend.tenancy import create_tenant_if_not_exists
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from spiffworkflow_backend.models.db import db
from flask import request, g

logger = logging.getLogger(__name__)


def create_realm(body: dict) -> tuple[dict, int]:
    """Create a spoke realm from the spiffworkflow template. Returns (response_dict, status_code)."""

    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    is_authorized = AuthorizationService.user_has_permission(user, "create", request.path)
        
    if not is_authorized:
        logger.warning(
            "User %s (groups: %s) attempted to create a tenant/realm without required permissions", 
            user.username, 
            [getattr(g, 'identifier', g.name) for g in getattr(user, 'groups', [])],
        )
        raise ApiError(error_code="forbidden", message="Not authorized to create a tenant.", status_code=403)


    realm_id = body.get("realm_id")
    if not realm_id or not str(realm_id).strip():
        return {"detail": "realm_id is required"}, 400
    display_name = body.get("display_name")
    try:
        result = create_realm_from_template(
            realm_id=str(realm_id).strip(),
            display_name=str(display_name).strip() if display_name else None,
        )
        keycloak_realm_id = result["keycloak_realm_id"]
        create_tenant_if_not_exists(
            keycloak_realm_id,
            name=result.get("displayName") or result["realm"],
            slug=result["realm"],
        )
        # Include id (Keycloak UUID) in response for clients that need it
        response = {**result, "id": keycloak_realm_id}
        return response, 201
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        # Debug: log which Keycloak URL failed (create realm vs partialImport vs get realm)
        failed_url = e.response.url if e.response is not None else None
        logger.warning(
            "Keycloak create realm HTTP error: %s %s (url=%s)",
            status,
            detail,
            failed_url,
        )
        logger.debug(
            "Keycloak create realm full response: status=%s url=%s body=%s",
            status,
            failed_url,
            (e.response.text[:1000] if e.response and e.response.text else None),
        )
        if status == 409:
            return {"detail": "Realm already exists or conflict"}, 409
        return {"detail": detail}, status
    except (ValueError, FileNotFoundError) as e:
        return {"detail": str(e)}, 400


def tenant_login(body: dict) -> tuple[dict, int]:
    """Login as a user in a spoke realm. Returns (token_response_dict, status_code)."""
    realm = body.get("realm")
    username = body.get("username")
    password = body.get("password")
    if not realm or not username:
        return {"detail": "realm and username are required"}, 400
    if password is None:
        password = ""
    try:
        result = tenant_login_svc(realm=str(realm).strip(), username=str(username), password=password)
        return result, 200
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        logger.warning("Keycloak tenant login HTTP error: %s %s", status, detail)
        if status == 401:
            return {"detail": "Invalid credentials"}, 401
        return {"detail": detail}, status
    except ValueError as e:
        return {"detail": str(e)}, 400


def create_user_in_realm(realm: str, body: dict) -> tuple[dict, int]:
    """Create a user in a spoke realm. Returns (response_dict, status_code)."""
    username = body.get("username")
    password = body.get("password")
    if not realm or not username:
        return {"detail": "realm and username are required"}, 400
    if password is None:
        password = ""
    email = body.get("email")
    try:
        user_id = create_user_in_realm_svc(
            realm=str(realm).strip(),
            username=str(username).strip(),
            password=password,
            email=str(email).strip() if email else None,
        )
        return {"user_id": user_id, "location": f"/admin/realms/{realm}/users/{user_id}"}, 201
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        logger.warning("Keycloak create user HTTP error: %s %s", status, detail)
        if status == 409:
            return {"detail": "User already exists or conflict"}, 409
        return {"detail": detail}, status
    except ValueError as e:
        return {"detail": str(e)}, 400


def get_tenant_login_url(tenant: str) -> tuple[dict, int]:
    """Check Keycloak for tenant realm and return its login URL. Returns (response_dict, status_code)."""
    if not tenant or not str(tenant).strip():
        return {"detail": "tenant is required"}, 400
    tenant = str(tenant).strip()
    if not realm_exists(tenant):
        return {"detail": "Tenant realm not found"}, 404
    try:
        login_url = tenant_login_authorization_url(tenant)
        return {"login_url": login_url, "realm": tenant}, 200
    except ValueError as e:
        return {"detail": str(e)}, 400


def delete_tenant_realm(realm_id: str) -> tuple[dict, int]:
    """Delete a tenant realm from Keycloak and Postgres. Requires a valid admin token.
    Keycloak is deleted first; Postgres is updated only after Keycloak succeeds to avoid
    inconsistent state if Keycloak fails (network, 5xx, timeout).

    The tenant row in Postgres has FK references from tenant-scoped tables (m8f_tenant_id)
    with ON DELETE RESTRICT. If any rows still reference this tenant, the delete returns
    409 and the caller must remove or reassign those references first (or use soft delete).
    """
    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    is_authorized = AuthorizationService.user_has_permission(user, "delete", request.path)
        
    if not is_authorized:
        logger.warning(
            "User %s (groups: %s) attempted to delete tenant %s without required permissions", 
            user.username, 
            [getattr(g, 'identifier', g.name) for g in getattr(user, 'groups', [])],
            realm_id
        )
        raise ApiError(error_code="forbidden", message="Not authorized to delete a tenant.", status_code=403)

    try:
        admin_token = get_master_admin_token()
        # Delete from Keycloak first. If this raises, we do not touch Postgres.
        delete_realm(realm_id, admin_token=admin_token)

        # Only after Keycloak succeeds: remove tenant from Postgres.
        tenant = (
            db.session.query(M8flowTenantModel)
            .filter(M8flowTenantModel.slug == realm_id)
            .one_or_none()
        )
        if tenant:
            try:
                db.session.delete(tenant)
                db.session.commit()
                logger.info("Deleted tenant record: id=%s slug=%s", tenant.id, realm_id)
            except IntegrityError as pg_exc:
                db.session.rollback()
                logger.warning(
                    "Cannot delete tenant %s: still referenced by other tables (m8f_tenant_id). %s",
                    realm_id,
                    pg_exc,
                )
                return {
                    "detail": "Tenant cannot be deleted: it still has data in tenant-scoped tables. Remove or reassign those records first, or use soft delete (tenant status DELETED).",
                }, 409
            except Exception as pg_exc:
                db.session.rollback()
                logger.exception(
                    "Keycloak realm %s was deleted but Postgres delete failed; tenant record may need manual cleanup: %s",
                    realm_id,
                    pg_exc,
                )
                return {
                    "message": f"Tenant realm {realm_id} was removed from Keycloak; local tenant record may need manual cleanup.",
                }, 200
        else:
            logger.info(
                "Tenant record with slug %s not found in Postgres after Keycloak delete (already consistent).",
                realm_id,
            )

        return {"message": f"Tenant {realm_id} deleted successfully"}, 200

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        logger.warning("Keycloak delete realm HTTP error: %s %s", status, detail)
        return {"detail": detail}, status
    except Exception as e:
        logger.exception("Error deleting tenant %s", realm_id)
        return {"detail": str(e)}, 500


@handle_api_errors
def update_tenant_name(tenant_id: str, body: dict) -> tuple[dict, int]:
    """Update a tenant's display name. Requires appropriate permissions."""
    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    is_authorized = AuthorizationService.user_has_permission(user, "update", request.path)
        
    if not is_authorized:
        logger.warning(
            "User %s (groups: %s) attempted to update tenant %s without required permissions", 
            user.username, 
            [getattr(g, 'identifier', g.name) for g in getattr(user, 'groups', [])],
            tenant_id
        )
        raise ApiError(error_code="forbidden", message="Not authorized to update the tenant name.", status_code=403)

    new_name = body.get("name")
    if not new_name or not str(new_name).strip():
        return {"detail": "name is required"}, 400
    new_name = str(new_name).strip()

    try:
        tenant = (
            db.session.query(M8flowTenantModel)
            .filter(M8flowTenantModel.id == tenant_id)
            .one_or_none()
        )
        if not tenant:
            return {"detail": "Tenant not found"}, 404

        admin_token = get_master_admin_token()

        update_realm(tenant.slug, display_name=new_name, admin_token=admin_token)
        tenant.name = new_name
        db.session.commit()
        logger.info("Updated tenant name: id=%s slug=%s to name=%s (updated by %s)", 
                    tenant_id, tenant.slug, new_name, user.username)

        return {"message": "Tenant name updated successfully", "name": new_name}, 200

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        logger.warning("Keycloak update realm HTTP error: %s %s", status, detail)
        return {"detail": detail}, status
    except Exception as e:
        db.session.rollback()
        logger.exception("Error updating tenant name %s", tenant_id)
        return {"detail": str(e)}, 500
