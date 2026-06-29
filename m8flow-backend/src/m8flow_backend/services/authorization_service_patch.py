from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from m8flow_backend.services.tenant_identity_helpers import active_organization_from_payload
from m8flow_backend.services.tenant_identity_helpers import authentication_identifier_from_payload
from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer
from m8flow_backend.services.tenant_identity_helpers import is_group_for_tenant
from m8flow_backend.services.tenant_identity_helpers import is_global_permission_group_identifier
from m8flow_backend.services.tenant_identity_helpers import normalize_group_identifiers
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifiers
from m8flow_backend.services.tenant_identity_helpers import normalize_group_permissions
from m8flow_backend.services.tenant_identity_helpers import organization_group_identifiers_from_payload
from m8flow_backend.services.tenant_identity_helpers import organization_memberships_from_payload
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import qualified_config_group_identifier
from m8flow_backend.services.tenant_identity_helpers import realm_from_service
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.services.tenant_group_mapping import tenant_roles_for_organization_group
from m8flow_backend.tenancy import is_concrete_tenant_id

_PATCHED = False
logger = logging.getLogger(__name__)

# Sentinel that distinguishes "no permission scope active" from "scope explicitly set to None".
# An explicit None is needed for master-realm sign-ins, which must NOT inherit an unrelated
# request tenant id when qualifying group identifiers.
_PERMISSION_SCOPE_TENANT_ID_NOT_SET: object = object()
_PERMISSION_SCOPE_TENANT_ID: ContextVar[Any] = ContextVar(
    "m8flow_permission_scope_tenant_id",
    default=_PERMISSION_SCOPE_TENANT_ID_NOT_SET,
)

# Endpoints that must bypass the standard auth/tenant-authorization path because they run
# before tenant finalization or with server-side auth only.
M8FLOW_AUTH_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.get_tenant_login_url",
    "m8flow_backend.routes.keycloak_controller.get_current_user_organization_memberships",
    "m8flow_backend.tenancy.health_check",
    "m8flow_backend.routes.events_controller.m8flow_trigger",
    "m8flow_backend.routes.external_forms_controller.external_form_show",
    "m8flow_backend.routes.external_forms_controller.external_form_submit",
]

# Endpoints that still require authenticated users but must bypass the generic
# pre-controller permission gate so their route-local tenant-aware auth logic can run.
M8FLOW_PERMISSION_CHECK_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.update_tenant_name",
]

M8FLOW_ROLE_GROUP_IDENTIFIERS = frozenset(
    {"super-admin", "tenant-admin", "editor", "viewer", "integrator", "reviewer", "submitter"}
)
M8FLOW_TENANT_ROLE_ALIASES = {
    "admin": "tenant-admin",
    "tenant-admin": "tenant-admin",
    "editor": "editor",
    "viewer": "viewer",
    "integrator": "integrator",
    "reviewer": "reviewer",
}


def _active_permission_scope_tenant_id(fallback: str | None = None) -> str | None:
    """
    Resolve the tenant id to use for permission import/check logic.

    The authorization patch cannot always rely on request-local tenant context,
    especially during login. In that case, the login token already provides an
    effective tenant id, so the patch stores it in a context variable while
    syncing groups and importing permissions.

    An explicit None scope (set via ``_permission_scope_tenant(None)``) is honored
    and short-circuits the request-tenant fallback so master-realm code paths,
    which intentionally have no tenant context, get unqualified group identifiers
    instead of accidentally being qualified with an unrelated request tenant id.
    """
    scoped_value = _PERMISSION_SCOPE_TENANT_ID.get()
    if scoped_value is not _PERMISSION_SCOPE_TENANT_ID_NOT_SET:
        return scoped_value
    return fallback or current_tenant_id_or_none()


@contextmanager
def _permission_scope_tenant(tenant_id: str | None):
    """Temporarily force permission logic to use the tenant resolved from the token."""
    token = _PERMISSION_SCOPE_TENANT_ID.set(tenant_id)
    try:
        yield
    finally:
        _PERMISSION_SCOPE_TENANT_ID.reset(token)


def _normalize_external_group_identifier(group_identifier: str) -> str | None:
    """
    Normalize external role/group names from Keycloak.

    Keycloak can emit group paths such as "/tenant-admin" or "/foo/tenant-admin".
    Internally, permission YAML and group identifiers expect the leaf name, such
    as "tenant-admin". Role aliases are also normalized here.
    """
    value = group_identifier.strip()
    if not value:
        return None

    if "/" in value:
        value = value.rstrip("/").split("/")[-1].strip()

    if not value:
        return None

    return M8FLOW_TENANT_ROLE_ALIASES.get(value, value)


def _group_identifier_applies_to_active_permission_scope(
    group_identifier: str,
    tenant_id: str | None = None,
) -> bool:
    """
    Return whether a group should contribute principals/permissions now.

    Only explicit global groups stay effective without tenant context. All
    tenant-scoped RBAC groups must be qualified for the active tenant.

    Exception: the default user group ("everybody") is also effective when there
    is no tenant context.  Master-realm super-admins never have a tenant context,
    so without this carve-out they would lose all "everybody" permissions even
    though they are enrolled in the group.
    """
    normalized_group_identifier = group_identifier.strip()
    if not normalized_group_identifier:
        return False

    if is_global_permission_group_identifier(normalized_group_identifier):
        return True

    tenant_identifiers = current_tenant_identifiers(tenant_id)
    if not tenant_identifiers:
        # Allow the default-user-group identifier to remain effective for users
        # who have no tenant context (e.g. master-realm admins).
        try:
            from flask import current_app

            bare_default_group = str(current_app.config.get("SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP") or "").strip()
            qualified_default_group = (
                qualified_config_group_identifier("SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP") or ""
            ).strip()
        except RuntimeError:
            return False
        return normalized_group_identifier in {
            identifier
            for identifier in (bare_default_group, qualified_default_group)
            if identifier
        }

    tenant_prefix, separator, _ = normalized_group_identifier.partition(":")
    return bool(separator and tenant_prefix in tenant_identifiers)


def _group_applies_to_active_permission_scope(group: Any, tenant_id: str | None = None) -> bool:
    """Return whether the group's principal should count for the active tenant context."""
    group_identifier = getattr(group, "identifier", None)
    if not isinstance(group_identifier, str):
        return False
    return _group_identifier_applies_to_active_permission_scope(group_identifier, tenant_id=tenant_id)


def _permission_scoped_groups_for_user(user: Any, tenant_id: str | None = None) -> list[Any]:
    """Return only the groups whose permissions should apply in the active tenant context."""
    groups = getattr(user, "groups", None)
    if not isinstance(groups, Iterable) or isinstance(groups, str | bytes):
        return []
    return [group for group in groups if _group_applies_to_active_permission_scope(group, tenant_id=tenant_id)]


def _username_from_user_info(user_info: dict[str, Any]) -> str:
    """
    Derive the local username for an OpenID sign-in payload.

    Do not fall back to email. In the shared-realm model, duplicate emails are
    allowed and local user recreation must stay anchored to issuer+subject.
    """
    preferred_username = user_info.get("preferred_username")
    if isinstance(preferred_username, str):
        normalized_preferred_username = preferred_username.strip()
        if normalized_preferred_username:
            return normalized_preferred_username

    subject = user_info.get("sub")
    if isinstance(subject, str):
        normalized_subject = subject.strip()
        if normalized_subject:
            return normalized_subject

    issuer = user_info.get("iss")
    return f"{user_info['sub']}@{issuer}" if issuer is not None else str(user_info["sub"])


def _display_name_from_user_info(user_info: dict[str, Any]) -> str | None:
    """Return the best available non-identity display value from the sign-in payload."""
    for key in ("preferred_username", "nickname", "name"):
        value = user_info.get(key)
        if isinstance(value, str):
            normalized_value = value.strip()
            if normalized_value:
                return normalized_value
    return None


def _master_realm_identifier() -> str:
    from m8flow_backend.config import master_realm_name

    return master_realm_name()


def _shared_realm_identifier() -> str:
    from m8flow_backend.config import shared_realm_name

    return shared_realm_name()


def _normalize_string_claim_values(raw_values: Any) -> list[str]:
    """Return a deduplicated list of non-empty string claim values."""
    if not isinstance(raw_values, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            continue
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _keycloak_realm_roles_as_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Fallback for tokens that do not expose a top-level roles claim.

    Master-realm admin tokens commonly carry application roles in
    realm_access.roles instead.
    """
    realm_access = user_info.get("realm_access")
    if not isinstance(realm_access, dict):
        return []
    roles = realm_access.get("roles")
    if not isinstance(roles, list):
        return []

    normalized_roles: list[str] = []
    seen: set[str] = set()
    for role in roles:
        if not isinstance(role, str):
            continue

        value = role.strip()
        if not value or value in seen:
            continue

        normalized_value = _normalize_external_group_identifier(value)
        if normalized_value in M8FLOW_ROLE_GROUP_IDENTIFIERS:
            seen.add(value)
            normalized_roles.append(normalized_value)
            continue

        role_name, separator, tenant_suffix = value.rpartition("@")
        if separator and tenant_suffix:
            normalized_role_name = _normalize_external_group_identifier(role_name)
            if normalized_role_name in M8FLOW_TENANT_ROLE_ALIASES:
                seen.add(value)
                normalized_roles.append(value)

    return normalized_roles


def _is_master_realm_user_info(user_info: dict[str, Any]) -> bool:
    """Return whether the token belongs to the configured master realm."""
    authentication_identifier = authentication_identifier_from_payload(user_info)
    if authentication_identifier == _master_realm_identifier():
        return True

    return extract_realm_from_issuer(user_info.get("iss")) == _master_realm_identifier()


def _normalize_keycloak_roles(user_info: dict[str, Any]) -> list[str]:
    """
    Return permission-role identifiers from the token.

    When a top-level ``roles`` claim exists, it is authoritative. Otherwise,
    fall back to ``realm_access.roles`` for tokens such as master-realm admin
    tokens that omit the top-level claim.
    """
    if "roles" in user_info:
        return [
            role
            for role in _normalize_string_claim_values(user_info.get("roles"))
            if role in M8FLOW_ROLE_GROUP_IDENTIFIERS
        ]

    normalized: list[str] = []
    seen: set[str] = set()
    for role in _keycloak_realm_roles_as_groups(user_info):
        if role not in seen:
            seen.add(role)
            normalized.append(role)
    return normalized


def _tenant_id_for_user_info(user_info: dict[str, Any]) -> str | None:
    """Resolve the effective tenant for the current sign-in payload."""
    token_tenant = tenant_id_from_payload(user_info)
    if token_tenant:
        return token_tenant

    context_tenant = current_tenant_id_or_none()
    context_tenant_is_concrete = bool(context_tenant and context_tenant != "public")
    if context_tenant_is_concrete:
        return context_tenant

    authentication_identifier = authentication_identifier_from_payload(user_info)
    realm_from_iss = extract_realm_from_issuer(user_info.get("iss"))
    if (
        authentication_identifier in {_shared_realm_identifier(), _master_realm_identifier()}
        or realm_from_iss in {_shared_realm_identifier(), _master_realm_identifier()}
    ):
        return None

    if context_tenant_is_concrete:
        return context_tenant

    # Raw Keycloak tokens from the master or shared realm may lack the explicit
    # m8flow_realm_name claim, so check the iss-derived realm before returning it
    # as a tenant id.  Master-realm tokens must never be scoped to a tenant.
    if realm_from_iss in {_shared_realm_identifier(), _master_realm_identifier()}:
        return None
    return realm_from_iss


def _should_defer_tenant_group_sync(user_info: dict[str, Any], tenant_id: str | None) -> bool:
    """
    Allow shared-realm users to authenticate before an active tenant is finalized.

    The first shared-realm login now requests ``organization:*`` so the app can
    discover all memberships after credentials are entered. When multiple
    organizations are present and no tenant has been selected yet, tenant-scoped
    group normalization must wait until the user completes the tenant-specific
    follow-up login.
    """
    normalized_tenant_id = tenant_id.strip() if isinstance(tenant_id, str) else None
    if is_concrete_tenant_id(normalized_tenant_id):
        return False

    authentication_identifier = authentication_identifier_from_payload(user_info)
    if authentication_identifier != _shared_realm_identifier():
        return False

    return len(organization_memberships_from_payload(user_info)) > 1


def _normalize_permissions_yaml_config(permission_configs: dict[str, Any], tenant_id: str | None) -> dict[str, Any]:
    """Tenant-qualify group keys and references from tenant-agnostic permissions YAML."""
    normalized_permission_configs = dict(permission_configs)

    raw_groups = permission_configs.get("groups")
    if isinstance(raw_groups, dict):
        normalized_groups: dict[str, Any] = {}
        for group_identifier, group_config in raw_groups.items():
            if not isinstance(group_identifier, str):
                continue

            normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
            if not normalized_group_identifier:
                continue

            normalized_groups[qualify_group_identifier(normalized_group_identifier, tenant_id=tenant_id)] = group_config

        normalized_permission_configs["groups"] = normalized_groups

    raw_permissions = permission_configs.get("permissions")
    if isinstance(raw_permissions, dict):
        normalized_permissions: dict[str, Any] = {}
        for permission_identifier, permission_config in raw_permissions.items():
            if not isinstance(permission_config, dict):
                normalized_permissions[permission_identifier] = permission_config
                continue

            normalized_permission_config = dict(permission_config)
            groups = permission_config.get("groups")
            if isinstance(groups, list):
                normalized_group_identifiers = []
                for group_identifier in groups:
                    if not isinstance(group_identifier, str):
                        continue

                    normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
                    if normalized_group_identifier:
                        normalized_group_identifiers.append(normalized_group_identifier)

                normalized_permission_config["groups"] = normalize_group_identifiers(
                    normalized_group_identifiers,
                    tenant_id=tenant_id,
                )

            normalized_permissions[permission_identifier] = normalized_permission_config

        normalized_permission_configs["permissions"] = normalized_permissions

    return normalized_permission_configs


def _normalize_keycloak_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Normalize Keycloak group claims while preserving group-path semantics.

    Separated group claims should remain usable as organizational identifiers,
    so values such as ``/Engineering`` are preserved instead of being collapsed
    to their leaf segment.
    """
    return normalize_organizational_group_identifiers(_normalize_string_claim_values(user_info.get("groups")))


def _normalized_open_id_group_identifiers(user_info: dict[str, Any]) -> list[str]:
    """
    Return the effective group identifiers to sync from the token.

    Organizational groups come from ``groups`` and permission roles come from
    ``roles`` or ``realm_access.roles``.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for group_identifier in (
        _normalized_open_id_organizational_group_identifiers(user_info)
        + _normalized_open_id_permission_role_group_identifiers(user_info)
    ):
        if group_identifier not in seen:
            seen.add(group_identifier)
            normalized.append(group_identifier)
    return normalized


def _normalized_open_id_organizational_group_identifiers(user_info: dict[str, Any]) -> list[str]:
    """
    Return organizational group identifiers from the token.

    Shared-realm tokens use the built-in ``organization`` claim as the sole
    authority for swimlane / organizational groups. Legacy top-level ``groups``
    remain supported only for non-shared-realm tokens.
    """
    if authentication_identifier_from_payload(user_info) == _shared_realm_identifier():
        normalized_group_identifiers: list[str] = []
        seen_group_identifiers: set[str] = set()

        for group_identifier in organization_group_identifiers_from_payload(user_info):
            if not isinstance(group_identifier, str):
                continue

            normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
            if (
                normalized_group_identifier
                and normalized_group_identifier not in seen_group_identifiers
            ):
                seen_group_identifiers.add(normalized_group_identifier)
                normalized_group_identifiers.append(normalized_group_identifier)

        return normalized_group_identifiers

    return normalize_organizational_group_identifiers(_normalize_string_claim_values(user_info.get("groups")))


def _normalized_open_id_permission_role_group_identifiers(user_info: dict[str, Any]) -> list[str]:
    """Return permission-bearing role identifiers from the token."""
    return _normalize_keycloak_roles(user_info)


def _normalized_open_id_local_group_identifiers(
    role_group_identifiers: list[str],
    organizational_group_identifiers: list[str],
    tenant_id: str | None,
) -> list[str]:
    """Return tenant-qualified local group identifiers for the active token context."""
    return _normalize_openid_group_identifiers(
        organizational_group_identifiers + role_group_identifiers,
        tenant_id=tenant_id,
    )


def _shared_realm_role_identifiers_from_organization_groups(
    user_info: dict[str, Any],
    *,
    tenant_id: str | None,
    organization_group_identifiers: list[str],
) -> list[str]:
    """
    Resolve tenant roles from shared-realm organization-group membership.

    Default organization groups have a built-in mapping, while custom groups
    can define tenant roles dynamically through Keycloak organization-group
    attributes. Read those attributes when available, then fall back to the
    default static mapping for compatibility.
    """
    normalized_role_identifiers: list[str] = []
    seen_role_identifiers: set[str] = set()

    organization = active_organization_from_payload(user_info, tenant_id=tenant_id)
    organization_id = None
    if organization is not None:
        _organization_alias, organization_details = organization
        raw_organization_id = organization_details.get("id")
        if isinstance(raw_organization_id, str):
            normalized_organization_id = raw_organization_id.strip()
            if normalized_organization_id:
                organization_id = normalized_organization_id

    for group_identifier in organization_group_identifiers:
        normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
        if not normalized_group_identifier:
            continue

        resolved_role_identifiers: list[str] = []
        if organization_id:
            try:
                from m8flow_backend.services.keycloak_service import get_organization_group_by_id
                from m8flow_backend.services.keycloak_service import get_organization_group_by_name
                from m8flow_backend.services.keycloak_service import organization_group_role_names

                organization_group = get_organization_group_by_name(
                    organization_id,
                    normalized_group_identifier,
                )
                if isinstance(organization_group, Mapping):
                    full_organization_group = organization_group
                    organization_group_id = organization_group.get("id")
                    if isinstance(organization_group_id, str) and organization_group_id.strip():
                        full_organization_group = (
                            get_organization_group_by_id(
                                organization_id,
                                organization_group_id.strip(),
                            )
                            or organization_group
                        )
                    resolved_role_identifiers = list(organization_group_role_names(full_organization_group))
            except Exception:
                logger.warning(
                    "auth_group_role_mapping_lookup_failed: tenant_id=%s organization_id=%s group=%s",
                    tenant_id,
                    organization_id,
                    normalized_group_identifier,
                    exc_info=True,
                )

        if not resolved_role_identifiers:
            resolved_role_identifiers = list(tenant_roles_for_organization_group(normalized_group_identifier))

        for role_identifier in resolved_role_identifiers:
            normalized_role_identifier = _normalize_external_group_identifier(role_identifier)
            if normalized_role_identifier and normalized_role_identifier not in seen_role_identifiers:
                seen_role_identifiers.add(normalized_role_identifier)
                normalized_role_identifiers.append(normalized_role_identifier)

    return normalized_role_identifiers


def _tenant_group_identifier_for_external_role(
    group_identifier: str,
    tenant_id: str | None,
    tenant_identifiers: set[str],
) -> str | None:
    """Map external ``role@tenant`` values to the internal tenant-qualified group identifier."""
    normalized_group_identifier = group_identifier.strip()
    if not normalized_group_identifier:
        return None

    role_name, separator, tenant_suffix = normalized_group_identifier.rpartition("@")
    if not separator or not role_name or not tenant_suffix:
        return None

    normalized_role_name = _normalize_external_group_identifier(role_name)
    if normalized_role_name is None:
        return None

    internal_role_name = M8FLOW_TENANT_ROLE_ALIASES.get(normalized_role_name)
    if internal_role_name is None:
        return None

    normalized_tenant_suffix = tenant_suffix.strip().casefold()
    if not normalized_tenant_suffix:
        return None

    if normalized_tenant_suffix not in {identifier.casefold() for identifier in tenant_identifiers}:
        return None

    if not tenant_id:
        return None

    return qualify_group_identifier(internal_role_name, tenant_id=tenant_id)


def _normalize_openid_group_identifiers(
    group_identifiers: list[str],
    tenant_id: str | None,
) -> list[str]:
    """Normalize token groups to internal tenant-qualified identifiers for the active tenant only."""
    tenant_identifiers = current_tenant_identifiers(tenant_id)
    normalized_group_identifiers: list[str] = []
    seen: set[str] = set()

    for group_identifier in group_identifiers:
        normalized = group_identifier.strip()
        if not normalized:
            continue

        if normalized.startswith("/"):
            qualified_organizational_group = qualify_group_identifier(
                normalize_organizational_group_identifier(normalized),
                tenant_id=tenant_id,
            )
            if qualified_organizational_group not in seen:
                seen.add(qualified_organizational_group)
                normalized_group_identifiers.append(qualified_organizational_group)
            continue

        normalized_for_tenant = _tenant_group_identifier_for_external_role(
            normalized,
            tenant_id=tenant_id,
            tenant_identifiers=tenant_identifiers,
        )
        if normalized_for_tenant is not None:
            if normalized_for_tenant not in seen:
                seen.add(normalized_for_tenant)
                normalized_group_identifiers.append(normalized_for_tenant)
            continue

        role_name, separator, tenant_suffix = normalized.rpartition("@")
        if (
            tenant_id
            and separator
            and tenant_suffix
            and _normalize_external_group_identifier(role_name.strip()) in M8FLOW_TENANT_ROLE_ALIASES
        ):
            # Explicit tenant-scoped roles for a different tenant must not leak into the active context.
            continue

        normalized_external = _normalize_external_group_identifier(normalized)
        if not normalized_external:
            continue

        qualified = qualify_group_identifier(normalized_external, tenant_id=tenant_id)
        if qualified not in seen:
            seen.add(qualified)
            normalized_group_identifiers.append(qualified)

    return normalized_group_identifiers


def _openid_group_identifiers_from_user_info(
    user_info: dict[str, Any],
    tenant_id: str | None,
) -> list[str]:
    """
    Return the effective OpenID-managed groups for this sign-in payload.

    In the shared realm, swimlane / organizational authority comes exclusively
    from the active organization's memberships inside the ``organization``
    claim. Legacy top-level ``groups`` are ignored there and remain supported
    only for non-shared realms.
    """
    normalized_groups = _normalize_keycloak_groups(user_info)
    derived_groups = _normalize_keycloak_roles(user_info)
    raw_group_identifiers: list[str] = []
    seen_groups: set[str] = set()

    for group_name in normalized_groups:
        if group_name not in seen_groups:
            seen_groups.add(group_name)
            raw_group_identifiers.append(group_name)

    for group_name in derived_groups:
        normalized_group_name = _normalize_external_group_identifier(group_name)
        if normalized_group_name and normalized_group_name not in seen_groups:
            seen_groups.add(normalized_group_name)
            raw_group_identifiers.append(normalized_group_name)

    if _is_master_realm_user_info(user_info):
        master_realm_group_identifiers: list[str] = []
        seen_master_realm_groups: set[str] = set()
        for group_identifier in raw_group_identifiers:
            normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
            if (
                normalized_group_identifier
                and is_global_permission_group_identifier(normalized_group_identifier)
                and normalized_group_identifier not in seen_master_realm_groups
            ):
                seen_master_realm_groups.add(normalized_group_identifier)
                master_realm_group_identifiers.append(normalized_group_identifier)
        raw_group_identifiers = master_realm_group_identifiers

    if authentication_identifier_from_payload(user_info) == _shared_realm_identifier():
        organization_group_identifiers = organization_group_identifiers_from_payload(
            user_info,
            tenant_id=tenant_id,
        )

        normalized_organization_group_identifiers: list[str] = []
        seen_organization_groups: set[str] = set()

        for group_identifier in organization_group_identifiers:
            if not isinstance(group_identifier, str):
                continue

            normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
            if normalized_group_identifier and normalized_group_identifier not in seen_organization_groups:
                seen_organization_groups.add(normalized_group_identifier)
                normalized_organization_group_identifiers.append(normalized_group_identifier)

        shared_realm_role_identifiers: list[str] = []
        seen_shared_realm_roles: set[str] = set()

        for group_identifier in derived_groups:
            normalized_group_identifier = _normalize_external_group_identifier(group_identifier)
            if normalized_group_identifier and normalized_group_identifier not in seen_shared_realm_roles:
                seen_shared_realm_roles.add(normalized_group_identifier)
                shared_realm_role_identifiers.append(normalized_group_identifier)

        for role_identifier in _shared_realm_role_identifiers_from_organization_groups(
            user_info,
            tenant_id=tenant_id,
            organization_group_identifiers=normalized_organization_group_identifiers,
        ):
            normalized_role_identifier = _normalize_external_group_identifier(role_identifier)
            if (
                normalized_role_identifier
                and normalized_role_identifier not in seen_shared_realm_roles
            ):
                seen_shared_realm_roles.add(normalized_role_identifier)
                shared_realm_role_identifiers.append(normalized_role_identifier)

        raw_group_identifiers = shared_realm_role_identifiers

        seen_groups = set(raw_group_identifiers)

        for group_identifier in normalized_organization_group_identifiers:
            if group_identifier not in seen_groups:
                seen_groups.add(group_identifier)
                raw_group_identifiers.append(group_identifier)

    return _normalize_openid_group_identifiers(raw_group_identifiers, tenant_id=tenant_id)


def _user_recency_key(user: Any) -> tuple[int, int, int]:
    """Sort users by most recently updated, then created, then id."""
    return (
        int(getattr(user, "updated_at_in_seconds", 0) or 0),
        int(getattr(user, "created_at_in_seconds", 0) or 0),
        int(getattr(user, "id", 0) or 0),
    )


def _find_existing_user_in_same_realm(
    username: str | None,
    service: str | None,
    users: list[Any] | None = None,
) -> Any | None:
    """Find the most recent user with the same username in the same Keycloak realm."""
    if not isinstance(username, str) or not username.strip():
        return None
    if not isinstance(service, str) or not service.strip():
        return None

    candidate_users = users
    if candidate_users is None:
        from spiffworkflow_backend.models.user import UserModel

        candidate_users = UserModel.query.filter(UserModel.username == username).all()

    target_realm = realm_from_service(service)
    same_realm_users = [
        user for user in candidate_users if realm_from_service(getattr(user, "service", None)) == target_realm
    ]
    if not same_realm_users:
        return None

    same_realm_users.sort(key=_user_recency_key, reverse=True)
    if len(same_realm_users) > 1:
        logger.warning(
            "auth_realm_user_match: found %s local users for username=%s realm=%s; reusing id=%s",
            len(same_realm_users),
            username,
            target_realm,
            getattr(same_realm_users[0], "id", None),
        )
    return same_realm_users[0]


def _find_existing_user_for_sign_in(
    username: str | None,
    service: str | None,
    service_id: str | None,
    users: list[Any] | None = None,
) -> Any | None:
    """Resolve a local user by exact issuer+subject."""
    if users is not None:
        for user in users:
            if getattr(user, "service", None) == service and getattr(user, "service_id", None) == service_id:
                return user
        return None

    from spiffworkflow_backend.models.user import UserModel

    return UserModel.query.filter(UserModel.service == service).filter(UserModel.service_id == service_id).first()


def _ignore_duplicate_group_assignment_error(exc: Exception) -> bool:
    """Return whether an exception represents a benign duplicate user/group assignment race."""
    try:
        from sqlalchemy.exc import IntegrityError
    except Exception:
        IntegrityError = None  # type: ignore[assignment]

    if IntegrityError is not None and isinstance(exc, IntegrityError):
        return True

    message = str(exc).lower()
    return "user_group_assignment_unique" in message or "duplicate key value violates unique constraint" in message


def apply() -> None:
    """Patch AuthorizationService for m8flow auth behavior and tenant-qualified groups."""
    global _PATCHED

    if _PATCHED:
        return

    from flask import current_app
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.group import SPIFF_GUEST_GROUP
    from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
    from spiffworkflow_backend.models.principal import MissingPrincipalError
    from spiffworkflow_backend.models.principal import PrincipalModel
    from spiffworkflow_backend.models.user import SPIFF_GUEST_USER
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
    try:
        from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentNotFoundError
    except Exception:
        UserGroupAssignmentNotFoundError = Exception  # type: ignore[misc, assignment]
    from spiffworkflow_backend.models.user_group_assignment_waiting import UserGroupAssignmentWaitingModel
    from spiffworkflow_backend.services import authorization_service
    from spiffworkflow_backend.services.authorization_service import AuthorizationService
    from spiffworkflow_backend.services.user_service import UserService

    _original_exclusion_list = authorization_service.AuthorizationService.authentication_exclusion_list
    _original_add_permission_from_uri_or_macro = AuthorizationService.add_permission_from_uri_or_macro

    @classmethod
    def _patched_authentication_exclusion_list(cls) -> list:
        """Extend the auth exclusion list with m8flow bootstrap and tenant-selection endpoints."""
        raw = _original_exclusion_list.__func__(cls)
        result = list(raw) if raw is not None else []
        for path in M8FLOW_AUTH_EXCLUSION_ADDITIONS:
            if path not in result:
                result.append(path)
        return result

    authorization_service.AuthorizationService.authentication_exclusion_list = _patched_authentication_exclusion_list
    logger.info("auth_exclusion_patch: added %s to authentication_exclusion_list", M8FLOW_AUTH_EXCLUSION_ADDITIONS)

    def _safe_add_user_to_group(user_model: UserModel, group_model: Any) -> bool:
        """Add a user/group assignment idempotently even if overlapping requests race."""
        if getattr(group_model, "id", None) is None:
            return False
        if (
            UserGroupAssignmentModel.query.filter_by(
                user_id=user_model.id,
                group_id=group_model.id,
            ).first()
            is not None
        ):
            return False

        try:
            UserService.add_user_to_group(user_model, group_model)
            return True
        except Exception as exc:
            db.session.rollback()
            if (
                _ignore_duplicate_group_assignment_error(exc)
                and UserGroupAssignmentModel.query.filter_by(
                    user_id=user_model.id,
                    group_id=group_model.id,
                ).first()
                is not None
            ):
                current_app.logger.info(
                    "auth_group_assignment_race: ignored duplicate add for user_id=%s group_id=%s identifier=%s",
                    user_model.id,
                    group_model.id,
                    getattr(group_model, "identifier", None),
                )
                return False
            raise

    def _safe_add_user_to_group_identifier(
        user_model: UserModel,
        group_identifier: str,
        *,
        source_is_open_id: bool = False,
    ) -> Any | None:
        """Find or create the group, then add the membership idempotently."""
        if not hasattr(UserService, "find_or_create_group") or not hasattr(UserService, "add_user_to_group"):
            return UserService.add_user_to_group_by_group_identifier(
                user_model,
                group_identifier,
                source_is_open_id=source_is_open_id,
            )

        group_model = UserService.find_or_create_group(group_identifier, source_is_open_id=source_is_open_id)
        _safe_add_user_to_group(user_model, group_model)
        return group_model

    def _safe_remove_user_from_group(user_model: UserModel, group_id: int) -> bool:
        """Remove a user/group assignment idempotently when stale reads race with another request."""
        query = UserGroupAssignmentModel.query.filter_by(user_id=user_model.id, group_id=group_id)
        if hasattr(query, "delete"):
            try:
                deleted_count = query.delete(synchronize_session=False)
                if deleted_count:
                    db.session.commit()
                    return True
                return False
            except Exception:
                db.session.rollback()
                raise

        assignment_exists = query.first() is not None
        if not assignment_exists:
            return False

        try:
            UserService.remove_user_from_group(user_model, group_id)
            return True
        except UserGroupAssignmentNotFoundError:
            db.session.rollback()
            current_app.logger.info(
                "auth_group_assignment_race: ignored missing assignment during remove for user_id=%s group_id=%s",
                user_model.id,
                group_id,
            )
            return False

    @classmethod
    def patched_get_permission_targets_for_user(cls, user: UserModel, check_groups: bool = True) -> set[tuple[str, str, str]]:
        """Limit group-derived permission targets to the active tenant plus explicit global groups."""
        unique_permission_assignments = set()
        for permission_assignment in user.principal.permission_assignments:
            unique_permission_assignments.add(
                (
                    permission_assignment.permission_target_id,
                    permission_assignment.permission,
                    permission_assignment.grant_type,
                )
            )

        if check_groups:
            tenant_id = _active_permission_scope_tenant_id()
            for group in _permission_scoped_groups_for_user(user, tenant_id=tenant_id):
                for permission_assignment in group.principal.permission_assignments:
                    unique_permission_assignments.add(
                        (
                            permission_assignment.permission_target_id,
                            permission_assignment.permission,
                            permission_assignment.grant_type,
                        )
                    )
        return unique_permission_assignments

    UserService.get_permission_targets_for_user = patched_get_permission_targets_for_user

    @classmethod
    def patched_all_principals_for_user(cls, user: UserModel) -> list[PrincipalModel]:
        if user.principal is None:
            raise MissingPrincipalError(f"Missing principal for user with id: {user.id}")

        tenant_id = _active_permission_scope_tenant_id()
        scoped_groups = _permission_scoped_groups_for_user(user, tenant_id=tenant_id)

        principals = [user.principal]
        for group in scoped_groups:
            if group.principal is None:
                raise MissingPrincipalError(f"Missing principal for group with id: {group.id}")
            principals.append(group.principal)

        return principals

    UserService.all_principals_for_user = patched_all_principals_for_user

    @classmethod
    def patched_create_user_from_sign_in(cls, user_info: dict[str, Any]):
        """
        Keep upstream login behavior, but:
        - keep bare usernames for the relaxed username-uniqueness model
        - use preferred_username/sub instead of email for local user recreation
        - normalize token groups to tenant-qualified identifiers
        - only remove OpenID-managed groups for the current tenant
        - import tenant-agnostic YAML config into tenant-qualified groups
        """
        new_group_ids: set[int] = set()
        old_group_ids: set[int] = set()
        user_attributes: dict[str, Any] = {}

        user_attributes["username"] = _username_from_user_info(user_info)
        display_name = _display_name_from_user_info(user_info)
        if display_name is not None:
            user_attributes["display_name"] = display_name

        user_attributes["email"] = user_info.get("email")
        user_attributes["service"] = user_info["iss"]
        user_attributes["service_id"] = user_info["sub"]

        effective_tenant_id = _tenant_id_for_user_info(user_info)

        for field_index, tenant_specific_field in enumerate(
            current_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"]
        ):
            if tenant_specific_field in user_info:
                field_number = field_index + 1
                user_attributes[f"tenant_specific_field_{field_number}"] = user_info[tenant_specific_field]

        user_model = _find_existing_user_for_sign_in(
            user_attributes.get("username"),
            user_attributes.get("service"),
            user_attributes.get("service_id"),
        )
        new_user = False
        if user_model is None:
            conflicting_user = _find_existing_user_in_same_realm(
                user_attributes.get("username"),
                user_attributes.get("service"),
            )
            if conflicting_user is not None:
                current_app.logger.warning(
                    "auth_reuse_same_realm_user: reusing local user id=%s username=%s realm=%s old_sub=%s new_sub=%s instead of creating a duplicate",
                    getattr(conflicting_user, "id", None),
                    user_attributes.get("username"),
                    realm_from_service(user_attributes.get("service")),
                    getattr(conflicting_user, "service_id", None),
                    user_attributes.get("service_id"),
                )
                user_model = conflicting_user
            else:
                current_app.logger.debug("create_user in login_return")
                user_model = UserService().create_user(**user_attributes)
                new_user = True

        if not new_user:
            user_db_model_changed = False
            for key, value in user_attributes.items():
                current_value = getattr(user_model, key)
                if current_value != value:
                    user_db_model_changed = True
                    setattr(user_model, key, value)
            if user_db_model_changed:
                db.session.add(user_model)
                db.session.commit()

        is_master_realm_user = _is_master_realm_user_info(user_info)

        with _permission_scope_tenant(effective_tenant_id):
            desired_group_identifiers: list[str] | Any | None = None
            if is_master_realm_user:
                desired_group_identifiers = _openid_group_identifiers_from_user_info(
                    user_info,
                    tenant_id=effective_tenant_id,
                )
            elif current_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"]:
                desired_group_identifiers = _openid_group_identifiers_from_user_info(
                    user_info,
                    tenant_id=effective_tenant_id,
                )

            logger.warning("auth_effective_tenant_id=%s", effective_tenant_id)
            logger.warning("auth_context_tenant_id=%s", current_tenant_id_or_none())
            logger.warning("auth_desired_group_identifiers=%s", desired_group_identifiers)

            if _should_defer_tenant_group_sync(user_info, effective_tenant_id):
                return user_model

            if desired_group_identifiers is not None:
                if not isinstance(desired_group_identifiers, list):
                    current_app.logger.error(
                        "Invalid groups property in token: %s. If groups is specified, it must be a list",
                        desired_group_identifiers,
                    )
                else:
                    for desired_group_identifier in desired_group_identifiers:
                        new_group = _safe_add_user_to_group_identifier(
                            user_model,
                            desired_group_identifier,
                            source_is_open_id=True,
                        )
                        if new_group is not None:
                            new_group_ids.add(new_group.id)

                    db.session.expire(user_model, ["groups"])
                    group_ids_to_remove_from_user = []
                    for group in user_model.groups:
                        if group.identifier in desired_group_identifiers:
                            continue

                        if is_master_realm_user:
                            if is_global_permission_group_identifier(group.identifier):
                                continue
                            # Also preserve the default user group ("everybody") so that
                            # master realm users keep basic permissions between logins.
                            master_default_group_id = qualified_config_group_identifier(
                                "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"
                            )
                            if master_default_group_id and group.identifier == master_default_group_id:
                                continue
                            group_ids_to_remove_from_user.append(group.id)
                            continue

                        default_group_identifier = qualified_config_group_identifier(
                            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
                            tenant_id=effective_tenant_id,
                        )
                        if default_group_identifier and group.identifier == default_group_identifier:
                            continue
                        if effective_tenant_id and not is_group_for_tenant(group.identifier, effective_tenant_id):
                            continue
                        group_ids_to_remove_from_user.append(group.id)

                    for group_id in group_ids_to_remove_from_user:
                        old_group_ids.add(group_id)
                        _safe_remove_user_from_group(user_model, group_id)

                    db.session.expire(user_model, ["groups"])

            if is_master_realm_user:
                for target, permission in (
                    ("/frontend-access", "read"),
                    ("/m8flow/tenants", "read"),
                    ("/m8flow/tenants/*", "all"),
                    ("/m8flow/tenant-realms", "all"),
                    ("/m8flow/tenant-realms/*", "all"),
                ):
                    cls.add_permission_from_uri_or_macro("super-admin", permission, target)

                # Import the full YAML permission set so that:
                # - the "everybody" group is created and the user is enrolled in it, and
                # - all "everybody" permissions from m8flow.yml (onboarding, active-users, etc.)
                #   are assigned to the group and become visible at request time via
                #   _group_identifier_applies_to_active_permission_scope.
                group_ids_before_yaml_import = {group.id for group in user_model.groups}
                cls.import_permissions_from_yaml_file(user_model)
                db.session.expire(user_model, ["groups"])
                group_ids_after_yaml_import = {group.id for group in user_model.groups}
                new_group_ids.update(group_ids_after_yaml_import - group_ids_before_yaml_import)
                old_group_ids.update(group_ids_before_yaml_import - group_ids_after_yaml_import)
            else:
                group_ids_before_yaml_import = {group.id for group in user_model.groups}
                cls.import_permissions_from_yaml_file(user_model)

                db.session.expire(user_model, ["groups"])
                group_ids_after_yaml_import = {group.id for group in user_model.groups}
                yaml_added_group_ids = group_ids_after_yaml_import - group_ids_before_yaml_import
                yaml_removed_group_ids = group_ids_before_yaml_import - group_ids_after_yaml_import

                new_group_ids.update(yaml_added_group_ids)
                old_group_ids.update(yaml_removed_group_ids)

            if new_user:
                new_group_ids.update({group.id for group in user_model.groups})

            if len(new_group_ids) > 0 or len(old_group_ids) > 0:
                UserService.update_human_task_assignments_for_user(
                    user_model,
                    new_group_ids=new_group_ids,
                    old_group_ids=old_group_ids,
                )

        return user_model

    AuthorizationService.create_user_from_sign_in = patched_create_user_from_sign_in


    @classmethod
    def patched_parse_permissions_yaml_into_group_info(cls):
        """Parse tenant-agnostic YAML into tenant-qualified group permission definitions."""
        tenant_id = _active_permission_scope_tenant_id()
        permission_configs = _normalize_permissions_yaml_config(cls.load_permissions_yaml(), tenant_id=tenant_id)

        group_permissions_by_group: dict[str, Any] = {}
        default_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            tenant_id=tenant_id,
        )
        if default_group_identifier:
            group_permissions_by_group[default_group_identifier] = {
                "name": default_group_identifier,
                "users": [],
                "permissions": [],
            }

        raw_groups = permission_configs.get("groups")
        if isinstance(raw_groups, dict):
            for group_identifier, group_config in raw_groups.items():
                if not isinstance(group_identifier, str) or not isinstance(group_config, dict):
                    continue
                group_info: dict[str, Any] = {"name": group_identifier, "users": [], "permissions": []}
                users = group_config.get("users", [])
                if isinstance(users, list):
                    group_info["users"] = [username for username in users if isinstance(username, str)]
                group_permissions_by_group[group_identifier] = group_info

        raw_permissions = permission_configs.get("permissions")
        if isinstance(raw_permissions, dict):
            for permission_config in raw_permissions.values():
                if not isinstance(permission_config, dict):
                    continue
                uri = permission_config["uri"]
                actions = cls.get_permissions_from_config(permission_config)
                for group_identifier in permission_config.get("groups", []):
                    group_permissions_by_group[group_identifier]["permissions"].append({"actions": actions, "uri": uri})

        return normalize_group_permissions(list(group_permissions_by_group.values()), tenant_id=tenant_id)

    AuthorizationService.parse_permissions_yaml_into_group_info = patched_parse_permissions_yaml_into_group_info

    @classmethod
    def patched_add_permission_from_uri_or_macro(cls, group_identifier: str, permission: str, target: str):
        """Tenant-qualify group identifiers before delegating permission creation upstream."""
        tenant_id = _active_permission_scope_tenant_id()
        normalized_group_identifier = _normalize_external_group_identifier(group_identifier) or group_identifier
        qualified_group_identifier = qualify_group_identifier(normalized_group_identifier, tenant_id=tenant_id)
        return _original_add_permission_from_uri_or_macro.__func__(cls, qualified_group_identifier, permission, target)

    AuthorizationService.add_permission_from_uri_or_macro = patched_add_permission_from_uri_or_macro

    @classmethod
    def patched_add_permissions_from_group_permissions(
        cls,
        group_permissions: list[dict[str, Any]],
        user_model: UserModel | None = None,
        group_permissions_only: bool = False,
    ):
        """Refresh tenant-scoped groups and permissions without mutating shared app config."""
        tenant_id = _active_permission_scope_tenant_id()
        normalized_group_permissions = normalize_group_permissions(group_permissions, tenant_id=tenant_id)
        count = len(normalized_group_permissions)
        current_app.logger.debug(
            "ADD PERMISSIONS - START: Processing %s group permissions, group_permissions_only=%s",
            count,
            group_permissions_only,
        )

        unique_user_group_identifiers: set[str] = set()
        user_to_group_identifiers: list[dict[str, Any]] = []
        waiting_user_group_assignments: list[UserGroupAssignmentWaitingModel] = []
        permission_assignments = []

        default_group = None
        default_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            tenant_id=tenant_id,
        )
        public_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP",
            tenant_id=tenant_id,
        )
        if default_group_identifier:
            current_app.logger.debug("ADD PERMISSIONS - Finding or creating default group: %s", default_group_identifier)
            default_group = UserService.find_or_create_group(default_group_identifier)
            unique_user_group_identifiers.add(default_group_identifier)

        for group_index, group in enumerate(normalized_group_permissions, start=1):
            group_identifier = group["name"]
            current_app.logger.debug(
                "ADD PERMISSIONS - Processing group %s/%s: %s",
                group_index,
                len(normalized_group_permissions),
                group_identifier,
            )

            UserService.find_or_create_group(group_identifier)
            if public_group_identifier and group_identifier == public_group_identifier:
                unique_user_group_identifiers.add(group_identifier)

            if not group_permissions_only:
                current_app.logger.debug(
                    "ADD PERMISSIONS - Processing %s users for group: %s",
                    len(group["users"]),
                    group_identifier,
                )
                for user_index, username_identifier in enumerate(group["users"], start=1):
                    if user_model and username_identifier != user_model.username:
                        continue

                    current_app.logger.debug(
                        "ADD PERMISSIONS - Processing user %s/%s: %s for group: %s",
                        user_index,
                        len(group["users"]),
                        username_identifier,
                        group_identifier,
                    )
                    (wugam, new_user_to_group_identifiers) = UserService.add_user_to_group_or_add_to_waiting(
                        username_identifier, group_identifier
                    )
                    if wugam is not None:
                        waiting_user_group_assignments.append(wugam)
                        current_app.logger.debug(
                            "ADD PERMISSIONS - Added waiting group assignment for user: %s, group: %s",
                            username_identifier,
                            group_identifier,
                        )

                    user_to_group_identifiers = user_to_group_identifiers + new_user_to_group_identifiers
                    unique_user_group_identifiers.add(group_identifier)

        for group in normalized_group_permissions:
            group_identifier = group["name"]

            user_is_member_of_group = False
            if user_model and any(g.identifier == group_identifier for g in user_model.groups):
                user_is_member_of_group = True
                unique_user_group_identifiers.add(group_identifier)
                current_app.logger.debug(
                    "ADD PERMISSIONS - User %s is already a member of group %s",
                    user_model.username,
                    group_identifier,
                )

            if user_model and not user_is_member_of_group and group_identifier not in unique_user_group_identifiers:
                current_app.logger.debug(
                    "ADD PERMISSIONS - Skipping permissions for group %s - not in unique group identifiers",
                    group_identifier,
                )
                continue

            current_app.logger.debug(
                "ADD PERMISSIONS - Processing %s permissions for group: %s",
                len(group["permissions"]),
                group_identifier,
            )
            for permission_index, permission in enumerate(group["permissions"], start=1):
                current_app.logger.debug(
                    "ADD PERMISSIONS - Processing permission %s/%s for group: %s, uri: %s, actions: %s",
                    permission_index,
                    len(group["permissions"]),
                    group_identifier,
                    permission["uri"],
                    permission["actions"],
                )

                for crud_op in permission["actions"]:
                    current_app.logger.debug(
                        "ADD PERMISSIONS - Adding permission: %s on %s for group: %s",
                        crud_op,
                        permission["uri"],
                        group_identifier,
                    )
                    new_permissions = cls.add_permission_from_uri_or_macro(
                        group_identifier=group_identifier,
                        target=permission["uri"],
                        permission=crud_op,
                    )
                    current_app.logger.debug(
                        "ADD PERMISSIONS - Added %s permission assignments",
                        len(new_permissions),
                    )
                    permission_assignments.extend(new_permissions)
                    unique_user_group_identifiers.add(group_identifier)

        if not group_permissions_only and default_group is not None:
            if user_model:
                current_app.logger.debug(
                    "ADD PERMISSIONS - Adding user %s to default group: %s",
                    user_model.username,
                    default_group_identifier,
                )
                _safe_add_user_to_group(user_model, default_group)
            else:
                users = UserModel.query.filter(UserModel.username.not_in([SPIFF_GUEST_USER])).all()  # type: ignore
                current_app.logger.debug(
                    "ADD PERMISSIONS - Adding %s users to default group: %s",
                    len(users),
                    default_group_identifier,
                )
                for user in users:
                    _safe_add_user_to_group(user, default_group)

        result: dict[str, Any] = {
            "group_identifiers": unique_user_group_identifiers,
            "permission_assignments": permission_assignments,
            "user_to_group_identifiers": user_to_group_identifiers,
            "waiting_user_group_assignments": waiting_user_group_assignments,
        }

        current_app.logger.debug(
            "ADD PERMISSIONS - COMPLETED: Added %s permission assignments, %s unique group identifiers",
            len(permission_assignments),
            len(unique_user_group_identifiers),
        )
        return result

    AuthorizationService.add_permissions_from_group_permissions = patched_add_permissions_from_group_permissions

    @classmethod
    def patched_remove_old_permissions_from_added_permissions(
        cls,
        added_permissions: dict[str, Any],
        initial_permission_assignments: list[PermissionAssignmentModel],
        initial_user_to_group_assignments: list[UserGroupAssignmentModel],
        initial_waiting_group_assignments: list[UserGroupAssignmentWaitingModel],
        group_permissions_only: bool = False,
    ) -> None:
        """Remove stale tenant-local permissions and group assignments after a permission refresh."""
        tenant_id = _active_permission_scope_tenant_id()
        if tenant_id:
            filtered_permission_assignments: list[PermissionAssignmentModel] = []
            for assignment in initial_permission_assignments:
                principal = db.session.get(PrincipalModel, assignment.principal_id)
                if principal is None or principal.group is None:
                    continue
                if is_group_for_tenant(principal.group.identifier, tenant_id):
                    filtered_permission_assignments.append(assignment)
            initial_permission_assignments = filtered_permission_assignments

            initial_user_to_group_assignments = [
                assignment
                for assignment in initial_user_to_group_assignments
                if is_group_for_tenant(assignment.group.identifier, tenant_id)
            ]
            initial_waiting_group_assignments = [
                assignment
                for assignment in initial_waiting_group_assignments
                if is_group_for_tenant(assignment.group.identifier, tenant_id)
            ]

        added_permission_assignments = added_permissions["permission_assignments"]
        added_user_to_group_identifiers = added_permissions["user_to_group_identifiers"]
        added_waiting_group_assignments = added_permissions["waiting_user_group_assignments"]
        default_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            tenant_id=tenant_id,
        )

        for initial_permission_assignment in initial_permission_assignments:
            if initial_permission_assignment not in added_permission_assignments:
                db.session.delete(initial_permission_assignment)

        if not group_permissions_only:
            for initial_assignment in initial_user_to_group_assignments:
                keep_default_group_assignment = (
                    default_group_identifier is not None and default_group_identifier == initial_assignment.group.identifier
                )
                keep_guest_assignment = (
                    initial_assignment.group.identifier == SPIFF_GUEST_GROUP
                    or initial_assignment.user.username == SPIFF_GUEST_USER
                )
                if keep_default_group_assignment or keep_guest_assignment:
                    continue

                current_user_dict: dict[str, Any] = {
                    "username": initial_assignment.user.username,
                    "group_identifier": initial_assignment.group.identifier,
                }
                if current_user_dict not in added_user_to_group_identifiers:
                    db.session.delete(initial_assignment)

        for waiting_assignment in initial_waiting_group_assignments:
            if waiting_assignment not in added_waiting_group_assignments:
                db.session.delete(waiting_assignment)

        db.session.commit()
        return None

    AuthorizationService.remove_old_permissions_from_added_permissions = patched_remove_old_permissions_from_added_permissions

    original_request_is_excluded = getattr(
        AuthorizationService,
        "request_is_excluded_from_permission_check",
        None,
    )
    _original_request_is_excluded = getattr(
        original_request_is_excluded,
        "__func__",
        None,
    )

    @classmethod  # type: ignore[misc]
    def patched_request_is_excluded_from_permission_check(cls) -> bool:
        if _original_request_is_excluded is not None and _original_request_is_excluded(cls):
            return True
        get_fully_qualified_api_function = getattr(
            cls,
            "get_fully_qualified_api_function_from_request",
            None,
        )
        if get_fully_qualified_api_function is None:
            return False
        api_function_full_path, _module = get_fully_qualified_api_function()
        if api_function_full_path in M8FLOW_PERMISSION_CHECK_EXCLUSION_ADDITIONS:
            return True
        if api_function_full_path and api_function_full_path.startswith(
            "m8flow_backend.routes.tenant_role_controller."
        ):
            return True
        return False

    AuthorizationService.request_is_excluded_from_permission_check = patched_request_is_excluded_from_permission_check
    _PATCHED = True
