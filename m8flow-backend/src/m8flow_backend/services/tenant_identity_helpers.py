from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any

from m8flow_backend.tenancy import TENANT_CLAIM
from m8flow_backend.tenancy import get_tenant_id

TENANT_ALIAS_CLAIM = "m8flow_tenant_alias"
TENANT_NAME_CLAIM = "m8flow_tenant_name"
REALM_NAME_CLAIM = "m8flow_realm_name"
REALM_ID_CLAIM = "m8flow_realm_id"
AUTHENTICATION_IDENTIFIER_CLAIM = "m8flow_authentication_identifier"
ORGANIZATION_CLAIM = "organization"
ORGANIZATION_SCOPE = "organization"
ALL_ORGANIZATIONS_SCOPE = "organization:*"

logger = logging.getLogger(__name__)


def _string_claim(payload: Mapping[str, Any] | None, claim: str) -> str | None:
    if payload is None:
        return None
    value = payload.get(claim)
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return None


def organization_memberships_from_payload(
    payload: Mapping[str, Any] | None,
) -> list[tuple[str, Mapping[str, Any]]]:
    """Return normalized organization memberships from the built-in organization claim."""
    if payload is None:
        return []

    organization_claim = payload.get(ORGANIZATION_CLAIM)
    if isinstance(organization_claim, Mapping):
        return [
            (alias.strip(), details)
            for alias, details in organization_claim.items()
            if isinstance(alias, str)
            and alias.strip()
            and isinstance(details, Mapping)
        ]

    if isinstance(organization_claim, list):
        normalized_memberships: list[tuple[str, Mapping[str, Any]]] = []
        for item in organization_claim:
            if isinstance(item, str):
                normalized_alias = item.strip()
                if normalized_alias:
                    normalized_memberships.append((normalized_alias, {}))
                continue

            if not isinstance(item, Mapping):
                continue

            alias_value = item.get("alias")
            if isinstance(alias_value, str) and alias_value.strip():
                details = item if isinstance(item, Mapping) else {}
                normalized_memberships.append((alias_value.strip(), details))

        return normalized_memberships

    return []


def single_organization_from_payload(
    payload: Mapping[str, Any] | None,
) -> tuple[str, Mapping[str, Any]] | None:
    """Return the single organization entry from the built-in organization claim."""
    organizations = organization_memberships_from_payload(payload)
    if len(organizations) != 1:
        return None
    return organizations[0]


def _canonical_tenant_id_from_identifiers(*identifiers: str | None) -> str | None:
    """
    Resolve token-provided tenant identifiers to the local canonical tenant id.

    Keycloak organization tokens may carry the organization UUID while older local
    M8Flow rows still use the organization alias as ``m8flow_tenant.id``. When a
    matching tenant row exists, always return that local row id so downstream
    tenant scoping, group qualification, and FK-backed records stay consistent.
    """
    normalized_identifiers: list[str] = []
    seen: set[str] = set()
    for identifier in identifiers:
        if not isinstance(identifier, str):
            continue
        normalized_identifier = identifier.strip()
        if not normalized_identifier or normalized_identifier in seen:
            continue
        seen.add(normalized_identifier)
        normalized_identifiers.append(normalized_identifier)

    if not normalized_identifiers:
        return None

    try:
        from sqlalchemy import or_

        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
        from spiffworkflow_backend.models.db import db

        filters = []
        for normalized_identifier in normalized_identifiers:
            filters.extend(
                (
                    M8flowTenantModel.id == normalized_identifier,
                    M8flowTenantModel.slug == normalized_identifier,
                )
            )
        tenant = db.session.query(M8flowTenantModel).filter(or_(*filters)).one_or_none()
    except Exception:
        tenant = None

    if tenant is None or not isinstance(tenant.id, str):
        return None

    canonical_tenant_id = tenant.id.strip()
    return canonical_tenant_id or None


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
    """Extract the configured tenant claim as the local canonical tenant id when possible."""
    organization = single_organization_from_payload(payload)
    if organization is not None:
        organization_alias, organization_details = organization
        organization_id = organization_details.get("id")
        if isinstance(organization_id, str):
            organization_id = organization_id.strip()
        else:
            organization_id = None

        canonical_organization_tenant_id = _canonical_tenant_id_from_identifiers(
            organization_id,
            organization_alias,
        )
        if canonical_organization_tenant_id:
            return canonical_organization_tenant_id
        if organization_id:
            return organization_id
        if organization_alias:
            return organization_alias

    explicit_tenant_id = _string_claim(payload, TENANT_CLAIM)
    if not explicit_tenant_id:
        return None

    canonical_explicit_tenant_id = _canonical_tenant_id_from_identifiers(
        explicit_tenant_id,
        _string_claim(payload, TENANT_ALIAS_CLAIM),
    )
    return canonical_explicit_tenant_id or explicit_tenant_id


def tenant_alias_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Extract the active tenant alias from a decoded token payload."""
    tenant_alias = _string_claim(payload, TENANT_ALIAS_CLAIM)
    if tenant_alias:
        return tenant_alias

    organization = single_organization_from_payload(payload)
    if organization is None:
        return None
    organization_alias, _ = organization
    return organization_alias


def tenant_name_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Extract the active tenant display name from a decoded token payload."""
    return _string_claim(payload, TENANT_NAME_CLAIM)


def realm_name_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Extract the Keycloak realm name from a decoded token payload."""
    realm_name = _string_claim(payload, AUTHENTICATION_IDENTIFIER_CLAIM)
    if realm_name:
        return realm_name

    realm_name = _string_claim(payload, REALM_NAME_CLAIM)
    if realm_name:
        return realm_name

    realm_name = _string_claim(payload, "realm_name")
    if realm_name:
        return realm_name

    # Legacy RealmInfoMapper tokens used m8flow_tenant_name for the realm name.
    return _string_claim(payload, TENANT_NAME_CLAIM)


def authentication_identifier_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Extract the auth-config identifier from a decoded token payload."""
    return realm_name_from_payload(payload)


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


def _shared_realm_service_issuer() -> str | None:
    """Return the configured shared-realm issuer URL used for local user rows."""
    try:
        from m8flow_backend.config import keycloak_url
        from m8flow_backend.config import shared_realm_name

        return f"{keycloak_url().rstrip('/')}/realms/{shared_realm_name().strip()}"
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

    tenant_slug = _tenant_slug_for_identifier(effective_tenant_id)
    if not tenant_slug:
        return None

    shared_realm_service = _shared_realm_service_issuer()
    if not shared_realm_service:
        return None

    try:
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.services.user_service import UserService

        from m8flow_backend.services.keycloak_service import get_organization_by_alias
        from m8flow_backend.services.keycloak_service import get_organization_member_by_username

        organization = get_organization_by_alias(tenant_slug)
        if not isinstance(organization, Mapping):
            return None

        organization_id = organization.get("id")
        if not isinstance(organization_id, str) or not organization_id.strip():
            return None

        member = get_organization_member_by_username(organization_id.strip(), normalized_username)
        if not isinstance(member, Mapping):
            return None

        member_id = member.get("id")
        if not isinstance(member_id, str) or not member_id.strip():
            return None
        member_id = member_id.strip()

        exact_user = (
            UserModel.query.filter(UserModel.service == shared_realm_service)
            .filter(UserModel.service_id == member_id)
            .first()
        )
        if exact_user is not None:
            updated = False

            member_username = member.get("username")
            if isinstance(member_username, str):
                member_username = member_username.strip()
            else:
                member_username = ""
            if member_username and exact_user.username != member_username:
                exact_user.username = member_username
                updated = True

            member_email = member.get("email")
            if isinstance(member_email, str):
                member_email = member_email.strip()
            else:
                member_email = ""
            if exact_user.email != member_email:
                exact_user.email = member_email
                updated = True

            display_name = _display_name_from_keycloak_member(member)
            if exact_user.display_name != display_name:
                exact_user.display_name = display_name
                updated = True

            if updated:
                db.session.add(exact_user)
                db.session.commit()
            return exact_user

        same_username_matches = UserModel.query.filter(UserModel.username == normalized_username).all()
        for user in same_username_matches:
            if realm_from_service(getattr(user, "service", None)) == realm_from_service(shared_realm_service):
                logger.warning(
                    "shared_realm_user_provision_conflict: username=%s tenant=%s existing_user_id=%s",
                    normalized_username,
                    effective_tenant_id,
                    getattr(user, "id", None),
                )
                return None

        member_email = member.get("email")
        if not isinstance(member_email, str):
            member_email = ""

        return UserService.create_user(
            normalized_username,
            shared_realm_service,
            member_id,
            email=member_email,
            display_name=_display_name_from_keycloak_member(member) or "",
        )
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
    from spiffworkflow_backend.models.user import UserModel

    matches = UserModel.query.filter(UserModel.username == username).all()
    tenant_matches = filter_users_for_current_tenant(matches, tenant_id=tenant_id)
    if tenant_matches:
        return tenant_matches

    provisioned_user = _provision_shared_realm_user_for_tenant(username, tenant_id=tenant_id)
    if provisioned_user is None:
        return []
    return [provisioned_user]


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
    if ":" in identifier:
        prefix, _, remainder = identifier.partition(":")
        if prefix and remainder:
            return identifier

    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return identifier

    return f"{effective_tenant_id}:{identifier}"


def _tenant_slug_for_identifier(tenant_identifier: str) -> str | None:
    """Resolve a tenant id or slug to the canonical tenant slug."""
    effective_tenant_identifier = tenant_identifier.strip()
    if not effective_tenant_identifier:
        return None

    try:
        from sqlalchemy import or_

        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
        from spiffworkflow_backend.models.db import db

        tenant = (
            db.session.query(M8flowTenantModel)
            .filter(
                or_(
                    M8flowTenantModel.id == effective_tenant_identifier,
                    M8flowTenantModel.slug == effective_tenant_identifier,
                )
            )
            .one_or_none()
        )
    except Exception:
        tenant = None

    if tenant is None or not isinstance(tenant.slug, str):
        return None

    slug = tenant.slug.strip()
    return slug or None


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
