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
    verify_admin_token,
)
from sqlalchemy.exc import IntegrityError

from m8flow_backend.tenancy import create_tenant_if_not_exists
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from spiffworkflow_backend.models.db import db
from flask import request

logger = logging.getLogger(__name__)


def create_realm(body: dict) -> tuple[dict, int]:
    """Create a spoke realm from the spiffworkflow template. Returns (response_dict, status_code)."""
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
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return {"detail": "Authorization header with Bearer token is required"}, 401

    admin_token = auth_header.split(" ")[1]
    if not verify_admin_token(admin_token):
        return {"detail": "Invalid or unauthorized admin token"}, 401

    try:
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
