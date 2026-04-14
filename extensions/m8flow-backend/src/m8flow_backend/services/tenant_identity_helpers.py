from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any

from m8flow_backend.tenancy import TENANT_CLAIM
from m8flow_backend.tenancy import get_tenant_id


def current_tenant_id_or_none() -> str | None:
    """Return the active tenant id, or ``None`` when no tenant context is set."""
    try:
        return get_tenant_id(warn_on_default=False)
    except RuntimeError:
        return None


def current_tenant_identifiers(tenant_id: str | None = None) -> set[str]:
    """Return the current tenant id plus any equivalent identifiers such as the slug."""
    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return set()

    identifiers = {effective_tenant_id}
    try:
        from sqlalchemy import or_

        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
        from spiffworkflow_backend.models.db import db

        tenant = (
            db.session.query(M8flowTenantModel)
            .filter(or_(M8flowTenantModel.id == effective_tenant_id, M8flowTenantModel.slug == effective_tenant_id))
            .one_or_none()
        )
    except Exception:
        tenant = None

    if tenant is not None:
        for value in (tenant.id, tenant.slug):
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    identifiers.add(normalized)

    return identifiers


def tenant_id_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Extract the configured tenant claim from a decoded token payload."""
    if payload is None:
        return None

    tenant_id = payload.get(TENANT_CLAIM)
    if isinstance(tenant_id, str):
        tenant_id = tenant_id.strip()
        if tenant_id:
            return tenant_id
    return None


def extract_realm_from_issuer(iss: str | None) -> str | None:
    """Extract the Keycloak realm name from an issuer URL."""
    if isinstance(iss, str) and "/realms/" in iss:
        return iss.split("/realms/")[-1].split("/")[0]
    return None


def realm_from_service(service: str | None) -> str:
    """Derive a stable tenant-like value from a service/issuer string."""
    realm = extract_realm_from_issuer(service)
    if realm:
        return realm
    if not service:
        return "unknown"
    normalized = service.rstrip("/")
    return normalized.replace("://", "_").replace("/", "_")[-32:] or "unknown"


def user_belongs_to_current_tenant(
    user: Any,
    tenant_id: str | None = None,
    tenant_identifiers: set[str] | None = None,
) -> bool:
    """Return ``True`` when the user can be matched to the active tenant context."""
    effective_identifiers = tenant_identifiers or current_tenant_identifiers(tenant_id)
    if not effective_identifiers:
        return True

    service_realm = realm_from_service(getattr(user, "service", None))
    if service_realm in effective_identifiers:
        return True

    username = getattr(user, "username", None)
    if isinstance(username, str) and "@" in username:
        _, _, suffix = username.rpartition("@")
        if suffix in effective_identifiers:
            return True

    return False


def filter_users_for_current_tenant(users: Iterable[Any], tenant_id: str | None = None) -> list[Any]:
    """Keep only users that belong to the current tenant context."""
    user_list = list(users)
    effective_identifiers = current_tenant_identifiers(tenant_id)
    if not effective_identifiers:
        return user_list
    return [
        user
        for user in user_list
        if user_belongs_to_current_tenant(user, tenant_identifiers=effective_identifiers)
    ]


def find_users_for_current_tenant_by_identifier(username_or_email: str, tenant_id: str | None = None) -> list[Any]:
    """Find users by username or email and narrow the result set to the active tenant."""
    from sqlalchemy import or_

    from spiffworkflow_backend.models.user import UserModel

    matches = UserModel.query.filter(
        or_(UserModel.username == username_or_email, UserModel.email == username_or_email)
    ).all()
    return filter_users_for_current_tenant(matches, tenant_id=tenant_id)


def find_users_for_current_tenant_by_username(username: str, tenant_id: str | None = None) -> list[Any]:
    """Find users by exact username within the current tenant."""
    from spiffworkflow_backend.models.user import UserModel

    matches = UserModel.query.filter(UserModel.username == username).all()
    return filter_users_for_current_tenant(matches, tenant_id=tenant_id)


def find_users_for_current_tenant_by_username_prefix(
    username_prefix: str,
    tenant_id: str | None = None,
) -> list[Any]:
    """Find users by username prefix within the current tenant."""
    from spiffworkflow_backend.models.user import UserModel

    matches = UserModel.query.filter(UserModel.username.like(f"{username_prefix}%")).all()  # type: ignore[arg-type]
    return filter_users_for_current_tenant(matches, tenant_id=tenant_id)


def resolve_user_for_current_tenant(username_or_email: str, tenant_id: str | None = None) -> Any | None:
    """Resolve a single tenant-local user from a username or email identifier."""
    matches = find_users_for_current_tenant_by_identifier(username_or_email, tenant_id=tenant_id)
    if not matches:
        return None

    exact_username_matches = [user for user in matches if getattr(user, "username", None) == username_or_email]
    if len(exact_username_matches) == 1:
        return exact_username_matches[0]

    exact_email_matches = [user for user in matches if getattr(user, "email", None) == username_or_email]
    if len(exact_email_matches) == 1:
        return exact_email_matches[0]

    if len(matches) == 1:
        return matches[0]

    return None


def qualify_group_identifier(group_identifier: str, tenant_id: str | None = None) -> str:
    """Return the canonical tenant-qualified group identifier."""
    identifier = group_identifier.strip()
    if not identifier:
        return identifier
    if ":" in identifier:
        prefix, _, remainder = identifier.partition(":")
        if prefix and remainder:
            return identifier

    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return identifier

    return f"{effective_tenant_id}:{identifier}"


def is_group_for_tenant(group_identifier: str, tenant_id: str | None = None) -> bool:
    """True when the group identifier is scoped to the given tenant."""
    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return False
    return group_identifier.startswith(f"{effective_tenant_id}:")


def normalize_group_identifiers(group_identifiers: list[str], tenant_id: str | None = None) -> list[str]:
    """Return tenant-qualified versions of the provided group identifiers."""
    return [qualify_group_identifier(group_identifier, tenant_id=tenant_id) for group_identifier in group_identifiers]


def normalize_group_permissions(group_permissions: list[dict[str, Any]], tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Return tenant-qualified group-permission payloads without mutating the input."""
    normalized_group_permissions: list[dict[str, Any]] = []
    for group in group_permissions:
        normalized_group_permissions.append(
            {
                "name": qualify_group_identifier(str(group["name"]), tenant_id=tenant_id),
                "users": list(group.get("users", [])),
                "permissions": [dict(permission) for permission in group.get("permissions", [])],
            }
        )
    return normalized_group_permissions


def qualified_config_group_identifier(config_key: str, tenant_id: str | None = None) -> str | None:
    """Read a config-backed group identifier and return its tenant-qualified form."""
    from flask import current_app

    value = current_app.config.get(config_key)
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return value
    return qualify_group_identifier(value, tenant_id=tenant_id)
