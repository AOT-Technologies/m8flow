"""Keycloak Admin API directory: realm users.

Tenant/membership HTTP lives in ``tenants.py``. HTTP plumbing (URLs, headers,
admin token, error mapping) lives in ``admin_client.py``. This module owns only
the user endpoints and the Keycloak-representation ↔ neutral-``User`` mapping.
"""
from __future__ import annotations

import logging
from typing import Any

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, UserNotFound
from m8flow_backend.integrations.auth.base.models import User
from m8flow_backend.integrations.auth.keycloak.admin_client import KeycloakAdminClient

logger = logging.getLogger(__name__)


def user_from_representation(payload: dict[str, Any]) -> User:
    user_id = payload.get("id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ProviderUnavailable("Directory user is missing a subject")
    username = payload.get("username")
    email = payload.get("email")
    first = payload.get("firstName") if isinstance(payload.get("firstName"), str) else ""
    last = payload.get("lastName") if isinstance(payload.get("lastName"), str) else ""
    display = f"{first} {last}".strip() or None
    return User(
        subject=user_id.strip(),
        username=username.strip() if isinstance(username, str) and username.strip() else None,
        email=email.strip() if isinstance(email, str) and email.strip() else None,
        display_name=display,
    )


def fetch_user_representation(
    realm: str,
    username: str,
    *,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    """Return the exact-match user representation, or None if missing/ambiguous."""
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")
    if not username or not str(username).strip():
        raise ValueError("username is required")
    normalized_realm = str(realm).strip()
    normalized_username = str(username).strip()
    response = KeycloakAdminClient(admin_token=admin_token).get(
        normalized_realm,
        "users",
        params={"username": normalized_username, "exact": "true", "max": 100},
        context=f"look up directory user {normalized_username!r}",
    )
    users = response.json()
    if not isinstance(users, list):
        return None
    exact = [
        user
        for user in users
        if isinstance(user, dict) and user.get("username") == normalized_username
    ]
    if len(exact) != 1:
        return None
    return exact[0]


def set_user_attribute(
    realm: str,
    username: str,
    *,
    name: str,
    value: str | None,
    admin_token: str | None = None,
) -> None:
    """Set (or clear, when ``value`` is None/blank) a single user attribute.

    Fetches the user representation, merges just the one attribute, and PUTs it
    back -- the shape Keycloak's Admin API expects. Used by the tenant switch to
    write ``m8flow_active_tenant`` so a subsequent refresh_token grant re-mints a
    token carrying the target org's claims (RealmInfoMapper reads this attribute;
    active-tenant deep-module map, ticket 09/10).
    """
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")
    if not username or not str(username).strip():
        raise ValueError("username is required")
    if not name or not str(name).strip():
        raise ValueError("attribute name is required")
    normalized_realm = str(realm).strip()
    normalized_name = str(name).strip()
    representation = fetch_user_representation(normalized_realm, username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    user_id = representation.get("id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise UserNotFound(username)

    attributes = representation.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    normalized_value = str(value).strip() if value is not None else ""
    if normalized_value:
        attributes[normalized_name] = [normalized_value]
    else:
        attributes.pop(normalized_name, None)
    representation["attributes"] = attributes

    KeycloakAdminClient(admin_token=admin_token).put(
        normalized_realm,
        "users",
        user_id.strip(),
        json=representation,
        context=f"set attribute {normalized_name!r} on directory user {username!r}",
    )


def search_user_representations(
    realm: str,
    search: str,
    *,
    exact: bool = False,
    admin_token: str | None = None,
    max_results: int = 100,
    first_result: int = 0,
) -> list[dict[str, Any]]:
    if not realm or not str(realm).strip():
        raise ValueError("realm is required")
    normalized_realm = str(realm).strip()
    normalized_search = str(search).strip() if isinstance(search, str) else ""
    params: dict[str, Any] = {"max": max_results}
    if first_result > 0:
        params["first"] = first_result
    if normalized_search:
        params["search"] = normalized_search
        params["exact"] = "true" if exact else "false"
    response = KeycloakAdminClient(admin_token=admin_token).get(
        normalized_realm,
        "users",
        params=params,
        context=f"search directory users in realm {normalized_realm!r}",
    )
    users = response.json()
    if not isinstance(users, list):
        return []
    return [user for user in users if isinstance(user, dict)]


def create_user(
    realm: str,
    username: str,
    password: str,
    *,
    email: str | None = None,
    enabled: bool = True,
    admin_token: str | None = None,
) -> User:
    """Create a realm user, clear required actions, return the neutral User."""
    if not realm or not username:
        raise ValueError("realm and username are required")
    normalized_realm = str(realm).strip()
    normalized_username = str(username).strip()
    client = KeycloakAdminClient(admin_token=admin_token)
    context = f"create directory user {normalized_username!r}"
    payload: dict[str, Any] = {
        "username": normalized_username,
        "enabled": enabled,
        "emailVerified": True,
        "firstName": normalized_username,
        "lastName": "User",
        "credentials": [{"type": "password", "value": password, "temporary": False}],
        "requiredActions": [],
    }
    if email:
        payload["email"] = email
    create_response = client.post(
        normalized_realm, "users", json=payload, tolerate=(409,), context=context
    )
    if create_response.status_code == 409:
        raise ProviderUnavailable("User already exists")
    location = create_response.headers.get("Location")
    if not (location and location.strip()):
        raise ProviderUnavailable("Directory did not return a user location after create")
    user_id = location.strip().rstrip("/").split("/")[-1]
    user_data = client.get(normalized_realm, "users", user_id, context=context).json()
    if not isinstance(user_data, dict):
        raise ProviderUnavailable("Directory returned a malformed user after create")
    user_data["requiredActions"] = []
    user_data["emailVerified"] = True
    if not user_data.get("firstName"):
        user_data["firstName"] = normalized_username
    if not user_data.get("lastName"):
        user_data["lastName"] = "User"
    client.put(normalized_realm, "users", user_id, json=user_data, context=context)
    return user_from_representation(user_data)


def delete_user_by_id(
    realm: str,
    user_id: str,
    *,
    admin_token: str | None = None,
) -> None:
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is required")
    normalized_realm = str(realm).strip()
    normalized_user_id = str(user_id).strip()
    response = KeycloakAdminClient(admin_token=admin_token).delete(
        normalized_realm,
        "users",
        normalized_user_id,
        tolerate=(404,),
        context=f"delete directory user {normalized_user_id!r}",
    )
    if response.status_code == 404:
        logger.info(
            "Directory user %s already deleted or not found in realm %s.",
            normalized_user_id,
            normalized_realm,
        )
        return
    logger.info("Deleted directory user %s from realm %s.", normalized_user_id, normalized_realm)


def delete_user_by_username(
    realm: str,
    username: str,
    *,
    admin_token: str | None = None,
) -> None:
    representation = fetch_user_representation(realm, username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    user_id = representation.get("id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ProviderUnavailable("Directory user is missing a subject")
    delete_user_by_id(realm, user_id, admin_token=admin_token)
