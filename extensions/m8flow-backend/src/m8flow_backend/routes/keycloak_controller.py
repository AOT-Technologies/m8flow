"""Keycloak API controller: create realm, tenant login, create user in realm."""
from __future__ import annotations

import logging

import requests

from m8flow_backend.services.keycloak_service import (
    create_realm_from_template,
    create_user_in_realm as create_user_in_realm_svc,
    tenant_login as tenant_login_svc,
)
from m8flow_backend.tenancy import create_tenant_if_not_exists

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
        create_tenant_if_not_exists(
            result["realm"],
            name=result.get("displayName") or result["realm"],
        )
        return result, 201
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 500
        detail = (e.response.text or str(e))[:500] if e.response is not None else str(e)
        logger.warning("Keycloak create realm HTTP error: %s %s", status, detail)
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
