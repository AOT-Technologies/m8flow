"""Shared-realm user provisioning (materializing/refreshing local user rows
from Keycloak organization members, including the admin-API calls that
requires) and tenant-qualified group-identifier string normalization.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any

from m8flow_backend.db import db

from m8flow_backend.auth.claims import realm_from_service
from m8flow_backend.auth.canonicalize import (
    _tenant_slug_for_identifier,
    current_tenant_id_or_none,
    current_tenant_identifiers,
)
from m8flow_backend.integrations.auth.base.models import VerifiedClaims

REALM_ID_CLAIM = "m8flow_realm_id"
ORGANIZATION_CLAIM = "organization"
ORGANIZATION_SCOPE = "organization"
ALL_ORGANIZATIONS_SCOPE = "organization:*"

logger = logging.getLogger(__name__)
GLOBAL_PERMISSION_GROUP_IDENTIFIERS = frozenset({"super-admin"})


def is_global_permission_group_identifier(group_identifier: str) -> bool:
    """Return whether the identifier should stay global instead of tenant-qualified."""
    normalized_group_identifier = group_identifier.strip()
    if not normalized_group_identifier:
        return False
    return normalized_group_identifier in GLOBAL_PERMISSION_GROUP_IDENTIFIERS


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

    groups = getattr(user, "groups", None)
    if isinstance(groups, Iterable):
        for group in groups:
            group_identifier = getattr(group, "identifier", None)
            if not isinstance(group_identifier, str):
                continue
            tenant_prefix, separator, _ = group_identifier.partition(":")
            if separator and tenant_prefix in effective_identifiers:
                return True

    return False


def local_user_from_claims(claims: VerifiedClaims | None) -> Any | None:
    """Resolve the local mirrored user row for a verified session's claims.

    Replaces the former ``local_user_from_payload(payload)`` (auth-provider-
    seam wayfinder map, ticket 10): ``claims.issuer``/``claims.subject`` are
    the same values a raw payload's ``iss``/``sub`` claims held, now read
    from the typed contract instead of a raw dict.
    """
    if claims is None:
        return None

    issuer = getattr(claims, "issuer", None)
    subject = getattr(claims, "subject", None)
    if not isinstance(issuer, str) or not issuer.strip():
        return None
    if not isinstance(subject, str) or not subject.strip():
        return None

    try:
        from m8flow_backend import identity

        return identity.find_user_by_service_identity(
            db.session, service=issuer.strip(), service_id=subject.strip()
        )
    except Exception:
        return None


def claims_user_belongs_to_tenant(
    claims: VerifiedClaims | None,
    tenant_id: str | None = None,
    tenant_identifiers: set[str] | None = None,
) -> bool:
    """Return whether the local mirrored user for a verified session belongs to the given tenant."""
    user = local_user_from_claims(claims)
    if user is None:
        return False
    return user_belongs_to_current_tenant(
        user,
        tenant_id=tenant_id,
        tenant_identifiers=tenant_identifiers,
    )


def _shared_realm_service_issuer() -> str | None:
    """Return the configured shared-realm issuer URL used for local user rows."""
    try:
        from m8flow_backend.integrations.auth import get_auth_provider

        return get_auth_provider().default_issuer_claim()
    except Exception:
        return None


def _display_name_from_keycloak_member(member: Mapping[str, Any]) -> str | None:
    """Build a best-effort display name from a Keycloak user representation."""
    first_name = member.get("firstName")
    last_name = member.get("lastName")
    if isinstance(first_name, str) and isinstance(last_name, str):
        full_name = " ".join(part.strip() for part in (first_name, last_name) if part and part.strip())
        if full_name:
            return full_name

    for key in ("firstName", "lastName", "username"):
        value = member.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _user_recency_key(user: Any) -> tuple[int, int, int]:
    """Sort users by most recently updated, then created, then id."""
    return (
        int(getattr(user, "updated_at_in_seconds", 0) or 0),
        int(getattr(user, "created_at_in_seconds", 0) or 0),
        int(getattr(user, "id", 0) or 0),
    )


def _refresh_local_shared_realm_user(
    local_user: Any,
    member: Mapping[str, Any],
    *,
    member_id: str,
    shared_realm_service: str,
) -> Any:
    """Refresh a local user row from a shared-realm Keycloak member representation."""
    from flask import g

    updated = False

    if getattr(local_user, "service", None) != shared_realm_service:
        local_user.service = shared_realm_service
        updated = True

    if getattr(local_user, "service_id", None) != member_id:
        local_user.service_id = member_id
        updated = True

    member_email = member.get("email")
    if isinstance(member_email, str):
        member_email = member_email.strip()
    else:
        member_email = ""
    if getattr(local_user, "email", None) != member_email:
        local_user.email = member_email
        updated = True

    display_name = _display_name_from_keycloak_member(member)
    if getattr(local_user, "display_name", None) != display_name:
        local_user.display_name = display_name
        updated = True

    if updated:
        g.db_session.add(local_user)
        g.db_session.commit()
    return local_user


def _upsert_local_shared_realm_member(member: Mapping[str, Any]) -> Any | None:
    """Create or refresh one local user row from a shared-realm Keycloak member representation."""
    member_id = member.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        return None
    member_id = member_id.strip()

    member_username = member.get("username")
    if isinstance(member_username, str):
        member_username = member_username.strip()
    else:
        member_username = ""
    if not member_username:
        return None

    shared_realm_service = _shared_realm_service_issuer()
    if not shared_realm_service:
        return None

    from flask import g
    from m8flow_backend import identity

    exact_user = identity.find_user_by_service_identity(
        db.session, service=shared_realm_service, service_id=member_id
    )
    if exact_user is not None:
        if exact_user.username != member_username:
            exact_user.username = member_username
            g.db_session.add(exact_user)
            g.db_session.commit()
        return _refresh_local_shared_realm_user(
            exact_user,
            member,
            member_id=member_id,
            shared_realm_service=shared_realm_service,
        )

    same_username_matches = identity.find_users_by_username(db.session, member_username)
    if same_username_matches:
        shared_realm = realm_from_service(shared_realm_service)
        same_username_matches.sort(
            key=lambda user: (
                realm_from_service(getattr(user, "service", None)) == shared_realm,
                *_user_recency_key(user),
            ),
            reverse=True,
        )
        if len(same_username_matches) > 1:
            logger.warning(
                "shared_realm_user_provision_match: found %s local users for username=%s realm=%s; reusing id=%s",
                len(same_username_matches),
                member_username,
                realm_from_service(shared_realm_service),
                getattr(same_username_matches[0], "id", None),
            )

        existing_user = same_username_matches[0]
        if realm_from_service(getattr(existing_user, "service", None)) != shared_realm:
            logger.warning(
                "shared_realm_user_provision_match: reusing username=%s from service=%s for shared realm service=%s",
                member_username,
                getattr(existing_user, "service", None),
                shared_realm_service,
            )
        return _refresh_local_shared_realm_user(
            existing_user,
            member,
            member_id=member_id,
            shared_realm_service=shared_realm_service,
        )

    member_email = member.get("email")
    if not isinstance(member_email, str):
        member_email = ""
    try:
        return identity.ensure_user(
            g.db_session,
            username=member_username,
            service=shared_realm_service,
            service_id=member_id,
            email=member_email,
        )
    except Exception:
        fallback_matches = identity.find_users_by_username(db.session, member_username)
        if not fallback_matches:
            raise

        fallback_matches.sort(
            key=lambda user: (
                realm_from_service(getattr(user, "service", None)) == realm_from_service(shared_realm_service),
                *_user_recency_key(user),
            ),
            reverse=True,
        )
        fallback_user = fallback_matches[0]
        logger.warning(
            "shared_realm_user_provision_fallback: reusing username=%s from service=%s after create_user failure",
            member_username,
            getattr(fallback_user, "service", None),
        )
        return _refresh_local_shared_realm_user(
            fallback_user,
            member,
            member_id=member_id,
            shared_realm_service=shared_realm_service,
        )


def upsert_local_shared_realm_member(member: Mapping[str, Any]) -> Any | None:
    """Public wrapper for provisioning or refreshing one shared-realm user locally."""
    return _upsert_local_shared_realm_member(member)


def member_mapping_from_user(user: Any) -> dict[str, Any]:
    return {
        "id": user.subject,
        "username": user.username,
        "email": user.email,
        "firstName": user.display_name or "",
    }


def _organization_id_for_tenant(tenant_id: str | None = None) -> str | None:
    """Resolve the active tenant to the Keycloak organization id in the shared realm."""
    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return None

    tenant_slug = _tenant_slug_for_identifier(effective_tenant_id)

    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.base.errors import TenantNotFound
    from m8flow_backend.integrations.auth.base.models import TenantRef

    try:
        tenant = get_auth_provider().directory_admin.get_tenant(
            TenantRef(
                id=effective_tenant_id or None,
                alias=tenant_slug or None,
            )
        )
    except TenantNotFound:
        return None
    tenant_id_value = tenant.ref.id
    if isinstance(tenant_id_value, str) and tenant_id_value.strip():
        return tenant_id_value.strip()
    return None


def _provision_shared_realm_user_for_tenant(username: str, tenant_id: str | None = None) -> Any | None:
    """
    Materialize a shared-realm organization member as a local user when needed.

    This is intentionally narrow: it only runs for exact username lookups scoped
    to the current tenant organization, so lane-owner assignment can resolve
    legitimate Keycloak users who have not logged in to M8Flow yet.
    """
    normalized_username = username.strip()
    if not normalized_username:
        return None

    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return None

    try:
        from m8flow_backend.integrations.auth import get_auth_provider
        from m8flow_backend.integrations.auth.base.errors import UserNotFound
        from m8flow_backend.integrations.auth.base.models import TenantRef

        organization_id = _organization_id_for_tenant(effective_tenant_id)
        if not organization_id:
            return None

        user = get_auth_provider().directory_admin.get_member(
            username=normalized_username,
            tenant_ref=TenantRef(id=organization_id),
        )
        return _upsert_local_shared_realm_member(member_mapping_from_user(user))
    except UserNotFound:
        return None
    except Exception:
        logger.exception(
            "shared_realm_user_provision_failed: username=%s tenant=%s",
            normalized_username,
            effective_tenant_id,
        )
        return None


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


def find_users_for_current_tenant_by_identifier(username: str, tenant_id: str | None = None) -> list[Any]:
    """
    Find users by username and narrow the result set to the active tenant.

    The helper keeps its historical name because several call sites still treat
    workflow/user-group inputs as generic "identifiers", but email is no longer
    used as a local user key in the shared-realm architecture.
    """
    from m8flow_backend import identity

    matches = identity.find_users_by_username(db.session, username)
    tenant_matches = filter_users_for_current_tenant(matches, tenant_id=tenant_id)
    if tenant_matches:
        return tenant_matches

    provisioned_user = _provision_shared_realm_user_for_tenant(username, tenant_id=tenant_id)
    if provisioned_user is None:
        return []
    return [provisioned_user]


def find_users_for_current_tenant_by_username(username: str, tenant_id: str | None = None) -> list[Any]:
    """Find users by exact username within the current tenant."""
    return find_users_for_current_tenant_by_identifier(username, tenant_id=tenant_id)


def find_users_for_current_tenant_by_username_prefix(
    username_prefix: str,
    tenant_id: str | None = None,
) -> list[Any]:
    """Find users by username prefix within the current tenant."""
    from m8flow_backend import identity

    matches = identity.find_users_by_username_prefix(db.session, username_prefix)
    tenant_matches = filter_users_for_current_tenant(matches, tenant_id=tenant_id)
    normalized_prefix = username_prefix.strip()
    if not normalized_prefix:
        return tenant_matches

    try:
        from m8flow_backend.integrations.auth import get_auth_provider
        from m8flow_backend.integrations.auth.base.models import TenantRef

        organization_id = _organization_id_for_tenant(tenant_id)
        if organization_id:
            seen_user_ids = {getattr(user, "id", None) for user in tenant_matches}
            seen_usernames = {getattr(user, "username", None) for user in tenant_matches}

            for user in get_auth_provider().directory_admin.list_members(
                tenant_ref=TenantRef(id=organization_id),
                query=normalized_prefix,
                limit=100,
            ):
                member_username = user.username
                if not isinstance(member_username, str) or not member_username.startswith(normalized_prefix):
                    continue

                local_user = _upsert_local_shared_realm_member(member_mapping_from_user(user))
                if local_user is None:
                    continue

                local_user_id = getattr(local_user, "id", None)
                local_username = getattr(local_user, "username", None)
                if local_user_id in seen_user_ids or local_username in seen_usernames:
                    continue

                tenant_matches.append(local_user)
                seen_user_ids.add(local_user_id)
                seen_usernames.add(local_username)
    except Exception:
        logger.exception(
            "shared_realm_user_prefix_search_failed: prefix=%s tenant=%s",
            normalized_prefix,
            tenant_id or current_tenant_id_or_none(),
        )

    tenant_matches.sort(key=lambda user: str(getattr(user, "username", "")))
    return tenant_matches


def resolve_user_for_current_tenant(username: str, tenant_id: str | None = None) -> Any | None:
    """Resolve a single tenant-local user from an exact username."""
    matches = find_users_for_current_tenant_by_identifier(username, tenant_id=tenant_id)
    if not matches:
        return None

    exact_username_matches = [user for user in matches if getattr(user, "username", None) == username]
    if len(exact_username_matches) == 1:
        return exact_username_matches[0]

    return None


def qualify_group_identifier(group_identifier: str, tenant_id: str | None = None) -> str:
    """Return the canonical tenant-qualified group identifier."""
    identifier = group_identifier.strip()
    if not identifier:
        return identifier
    if is_global_permission_group_identifier(identifier):
        return "super-admin"
    if ":" in identifier:
        prefix, _, remainder = identifier.partition(":")
        if prefix and remainder:
            return identifier

    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return identifier

    return f"{effective_tenant_id}:{identifier}"


def normalize_organizational_group_identifier(group_identifier: str) -> str:
    """Return a canonical full-path organizational group identifier."""
    identifier = group_identifier.strip()
    if not identifier:
        return identifier

    tenant_prefix = ""
    if ":" in identifier:
        prefix, _, remainder = identifier.partition(":")
        if prefix and remainder:
            tenant_prefix = f"{prefix}:"
            identifier = remainder.strip()

    path_segments = [segment.strip() for segment in identifier.split("/") if segment.strip()]
    if not path_segments:
        return tenant_prefix

    normalized_path = "/" + "/".join(path_segments)
    return f"{tenant_prefix}{normalized_path}"


def normalize_organizational_group_identifiers(group_identifiers: list[str]) -> list[str]:
    """Return deduplicated canonical organizational group paths."""
    normalized: list[str] = []
    seen: set[str] = set()
    for group_identifier in group_identifiers:
        canonical_identifier = normalize_organizational_group_identifier(group_identifier)
        if canonical_identifier and canonical_identifier not in seen:
            seen.add(canonical_identifier)
            normalized.append(canonical_identifier)
    return normalized


def organization_scope_for_tenant(tenant_identifier: str | None = None) -> str:
    """Return the Keycloak organization scope value for an optional tenant alias."""
    if not isinstance(tenant_identifier, str):
        return ALL_ORGANIZATIONS_SCOPE

    normalized = tenant_identifier.strip()
    if not normalized:
        return ALL_ORGANIZATIONS_SCOPE

    tenant_slug = _tenant_slug_for_identifier(normalized) or normalized
    return f"{ORGANIZATION_SCOPE}:{tenant_slug}"


def display_group_identifier(group_identifier: str) -> str:
    """Return a tenant-qualified group identifier as ``tenant_slug:lane`` for display."""
    identifier = group_identifier.strip()
    if not identifier:
        return identifier
    if ":" not in identifier:
        return identifier

    tenant_identifier, _, remainder = identifier.partition(":")
    if not tenant_identifier or not remainder:
        return identifier

    tenant_slug = _tenant_slug_for_identifier(tenant_identifier) or tenant_identifier

    return f"{tenant_slug}:{remainder}"


def is_group_for_tenant(group_identifier: str, tenant_id: str | None = None) -> bool:
    """True when the group identifier is scoped to the given tenant."""
    if is_global_permission_group_identifier(group_identifier):
        return False
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
