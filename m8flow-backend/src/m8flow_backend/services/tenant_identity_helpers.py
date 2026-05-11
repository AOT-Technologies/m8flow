from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any

from flask import g
from flask import has_request_context

from m8flow_backend.tenancy import TENANT_CLAIM
from m8flow_backend.tenancy import get_context_tenant_id
from m8flow_backend.tenancy import is_concrete_tenant_id

TENANT_ALIAS_CLAIM = "m8flow_tenant_alias"
TENANT_NAME_CLAIM = "m8flow_tenant_name"
REALM_NAME_CLAIM = "m8flow_realm_name"
REALM_ID_CLAIM = "m8flow_realm_id"
AUTHENTICATION_IDENTIFIER_CLAIM = "m8flow_authentication_identifier"
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


def active_organization_from_payload(
    payload: Mapping[str, Any] | None,
    tenant_id: str | None = None,
) -> tuple[str, Mapping[str, Any]] | None:
    """Return the active organization entry, or ``None`` when it cannot be resolved safely."""
    organizations = organization_memberships_from_payload(payload)
    if not organizations:
        return None

    if len(organizations) == 1:
        return organizations[0]

    tenant_identifiers = current_tenant_identifiers(tenant_id)
    if not tenant_identifiers:
        return None

    matching_organizations: list[tuple[str, Mapping[str, Any]]] = []
    for organization_alias, organization_details in organizations:
        organization_identifiers = {organization_alias}
        organization_id = organization_details.get("id")
        if isinstance(organization_id, str):
            normalized_organization_id = organization_id.strip()
            if normalized_organization_id:
                organization_identifiers.add(normalized_organization_id)
        else:
            normalized_organization_id = None

        canonical_tenant_id = _canonical_tenant_id_from_identifiers(
            normalized_organization_id,
            organization_alias,
        )
        if canonical_tenant_id:
            organization_identifiers.add(canonical_tenant_id)

        if organization_identifiers.intersection(tenant_identifiers):
            matching_organizations.append((organization_alias, organization_details))

    if len(matching_organizations) != 1:
        return None
    return matching_organizations[0]


def organization_group_identifiers_from_payload(
    payload: Mapping[str, Any] | None,
    tenant_id: str | None = None,
) -> list[str]:
    """Return normalized organization-local group identifiers for the active organization."""
    organization = active_organization_from_payload(payload, tenant_id=tenant_id)
    if organization is None:
        return []

    _organization_alias, organization_details = organization
    organization_groups = organization_details.get("groups")
    if not isinstance(organization_groups, list):
        return []

    normalized_group_identifiers: list[str] = []
    seen: set[str] = set()
    for organization_group in organization_groups:
        if not isinstance(organization_group, str):
            continue
        value = organization_group.strip()
        if not value:
            continue
        normalized_value = value.rstrip("/")
        if "/" in normalized_value:
            normalized_value = normalized_value.split("/")[-1].strip()
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            normalized_group_identifiers.append(normalized_value)

    return normalized_group_identifiers


def _canonical_tenant_id_from_identifiers(*identifiers: str | None) -> str | None:
    """
    Resolve token-provided tenant identifiers to the local canonical tenant id.

    When a matching tenant row exists, always return that row's primary key so
    downstream tenant scoping, group qualification, and FK-backed records stay
    consistent.
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
    if has_request_context():
        if getattr(g, "_m8flow_global_request", False) or getattr(g, "_m8flow_public_request", False):
            return None

        request_tenant = getattr(g, "m8flow_tenant_id", None)
        if isinstance(request_tenant, str):
            normalized_request_tenant = request_tenant.strip()
            if is_concrete_tenant_id(normalized_request_tenant):
                return normalized_request_tenant

    context_tenant = get_context_tenant_id()
    if isinstance(context_tenant, str):
        normalized_context_tenant = context_tenant.strip()
        if is_concrete_tenant_id(normalized_context_tenant):
            return normalized_context_tenant

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
    organization = active_organization_from_payload(payload)
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

    organization = active_organization_from_payload(payload)
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
    from spiffworkflow_backend.models.db import db

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
        db.session.add(local_user)
        db.session.commit()
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

    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.user_service import UserService

    exact_user = (
        UserModel.query.filter(UserModel.service == shared_realm_service)
        .filter(UserModel.service_id == member_id)
        .first()
    )
    if exact_user is not None:
        if exact_user.username != member_username:
            exact_user.username = member_username
            db.session.add(exact_user)
            db.session.commit()
        return _refresh_local_shared_realm_user(
            exact_user,
            member,
            member_id=member_id,
            shared_realm_service=shared_realm_service,
        )

    same_username_matches = UserModel.query.filter(UserModel.username == member_username).all()
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
        return UserService.create_user(
            member_username,
            shared_realm_service,
            member_id,
            email=member_email,
            display_name=_display_name_from_keycloak_member(member) or "",
        )
    except Exception:
        fallback_matches = UserModel.query.filter(UserModel.username == member_username).all()
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


def _organization_id_for_tenant(tenant_id: str | None = None) -> str | None:
    """Resolve the active tenant to the Keycloak organization id in the shared realm."""
    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return None

    tenant_slug = _tenant_slug_for_identifier(effective_tenant_id)

    from m8flow_backend.services.keycloak_service import get_organization_by_alias
    from m8flow_backend.services.keycloak_service import get_organization_by_id

    organization_candidates: list[tuple[str, str]] = []
    if effective_tenant_id:
        organization_candidates.append(("id", effective_tenant_id))
    if tenant_slug:
        organization_candidates.append(("alias", tenant_slug))

    for lookup_kind, organization_identifier in organization_candidates:
        if lookup_kind == "id":
            organization = get_organization_by_id(organization_identifier)
        else:
            organization = get_organization_by_alias(organization_identifier)

        if not isinstance(organization, Mapping):
            continue

        organization_id = organization.get("id")
        if isinstance(organization_id, str):
            normalized_organization_id = organization_id.strip()
            if normalized_organization_id:
                return normalized_organization_id

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
        from m8flow_backend.services.keycloak_service import get_organization_member_by_username

        organization_id = _organization_id_for_tenant(effective_tenant_id)
        if not organization_id:
            return None

        member = get_organization_member_by_username(organization_id, normalized_username)
        if not isinstance(member, Mapping):
            return None
        return _upsert_local_shared_realm_member(member)
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
    return find_users_for_current_tenant_by_identifier(username, tenant_id=tenant_id)


def find_users_for_current_tenant_by_username_prefix(
    username_prefix: str,
    tenant_id: str | None = None,
) -> list[Any]:
    """Find users by username prefix within the current tenant."""
    from spiffworkflow_backend.models.user import UserModel

    matches = UserModel.query.filter(UserModel.username.like(f"{username_prefix}%")).all()  # type: ignore[arg-type]
    tenant_matches = filter_users_for_current_tenant(matches, tenant_id=tenant_id)
    normalized_prefix = username_prefix.strip()
    if not normalized_prefix:
        return tenant_matches

    try:
        from m8flow_backend.services.keycloak_service import search_organization_members

        organization_id = _organization_id_for_tenant(tenant_id)
        if organization_id:
            seen_user_ids = {getattr(user, "id", None) for user in tenant_matches}
            seen_usernames = {getattr(user, "username", None) for user in tenant_matches}

            for member in search_organization_members(organization_id, normalized_prefix, exact=False):
                member_username = member.get("username")
                if not isinstance(member_username, str) or not member_username.startswith(normalized_prefix):
                    continue

                local_user = _upsert_local_shared_realm_member(member)
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


def tenant_slug_for_identifier(tenant_identifier: str) -> str | None:
    """Public wrapper for resolving a tenant id or alias to the canonical tenant slug."""
    if not isinstance(tenant_identifier, str):
        return None
    return _tenant_slug_for_identifier(tenant_identifier)


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
