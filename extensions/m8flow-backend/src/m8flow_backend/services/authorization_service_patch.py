# extensions/m8flow-backend/src/m8flow_backend/services/authorization_service_patch.py
from __future__ import annotations

import logging
from typing import Any

_PATCHED = False
logger = logging.getLogger(__name__)

# Endpoints that must be callable without authentication (pre-login tenant selection, tenant login URL,
# and bootstrap: create realm / create tenant — no tenant in token yet; Keycloak admin is server-side).
M8FLOW_AUTH_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.get_tenant_login_url",
    "m8flow_backend.tenancy.health_check",
]
M8FLOW_ROLE_GROUP_IDENTIFIERS = frozenset(
    {"super-admin", "tenant-admin", "editor", "viewer", "integrator", "reviewer"}
)


def _extract_realm_from_issuer(iss: str | None) -> str | None:
    """Extract the Keycloak realm name from an issuer URL."""
    if isinstance(iss, str) and "/realms/" in iss:
        return iss.split("/realms/")[-1].split("/")[0]
    return None


def _apply_username_suffix(username: str, realm: str) -> str:
    """Append @realm once so usernames stay unique across realms."""
    suffix = f"@{realm}"
    if username.endswith(suffix):
        return username
    return f"{username}{suffix}"


def _keycloak_realm_roles_as_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Fallback for tokens that do not expose a top-level groups claim.

    Master-realm admin tokens commonly carry application roles in
    realm_access.roles instead.
    """
    realm_access = user_info.get("realm_access")
    if not isinstance(realm_access, dict):
        return []
    roles = realm_access.get("roles")
    if not isinstance(roles, list):
        return []
    return [
        role
        for role in roles
        if isinstance(role, str) and role in M8FLOW_ROLE_GROUP_IDENTIFIERS
    ]


def _normalize_keycloak_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Normalize Keycloak group claims to role/group identifiers used by permissions config.

    Keycloak groups are frequently emitted as paths (e.g. "/super-admin" or "/a/b/super-admin").
    Permission assignment expects plain identifiers like "super-admin".
    """
    groups = user_info.get("groups")
    if not isinstance(groups, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, str):
            continue
        value = group.strip()
        if not value:
            continue
        candidates = [value]
        if "/" in value:
            leaf = value.rstrip("/").split("/")[-1].strip()
            if leaf:
                candidates.append(leaf)
        for candidate in candidates:
            if candidate in M8FLOW_ROLE_GROUP_IDENTIFIERS and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
    return normalized


def apply() -> None:
    """Patch AuthorizationService: authentication_exclusion_list (M8Flow public endpoints) and create_user_from_sign_in (realm-scoped usernames)."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services import authorization_service
    from spiffworkflow_backend.services.authorization_service import AuthorizationService
    from spiffworkflow_backend.models.user import UserModel

    # Patch 1: authentication_exclusion_list — add M8Flow public endpoints
    _original_exclusion_list = authorization_service.AuthorizationService.authentication_exclusion_list

    @classmethod
    def _patched_authentication_exclusion_list(cls) -> list:
        raw = _original_exclusion_list.__func__(cls)
        result = list(raw) if raw is not None else []
        for path in M8FLOW_AUTH_EXCLUSION_ADDITIONS:
            if path not in result:
                result.append(path)
        return result

    authorization_service.AuthorizationService.authentication_exclusion_list = _patched_authentication_exclusion_list
    logger.info("auth_exclusion_patch: added %s to authentication_exclusion_list", M8FLOW_AUTH_EXCLUSION_ADDITIONS)

    # Patch 2: create_user_from_sign_in — realm-scoped usernames and disambiguation
    original_create_user_from_sign_in = AuthorizationService.create_user_from_sign_in

    @classmethod
    def patched_create_user_from_sign_in(cls, user_info: dict[str, Any]):
        """
        Wrap create_user_from_sign_in to ensure username uniqueness across realms.
        We append the realm name (extracted from 'iss') to the preferred_username.
        If the resulting username is already taken by another user (update path conflict),
        we append a short disambiguator from sub so the update does not violate user_username_key.
        """
        if "preferred_username" in user_info and "iss" in user_info:
            username = user_info["preferred_username"]
            iss = user_info["iss"]
            sub = user_info.get("sub") or ""

            normalized_groups = _normalize_keycloak_groups(user_info)
            derived_groups = _keycloak_realm_roles_as_groups(user_info)
            merged_groups = []
            seen_groups = set()
            for group_name in normalized_groups + derived_groups:
                if group_name not in seen_groups:
                    seen_groups.add(group_name)
                    merged_groups.append(group_name)
            if merged_groups:
                user_info = user_info.copy()
                user_info["groups"] = merged_groups

            realm = _extract_realm_from_issuer(iss)
            if realm:
                # Only append if not already appended (idempotency)
                desired_username = _apply_username_suffix(username, realm)
                if desired_username != username:
                    user_info = user_info.copy()
                    user_info["preferred_username"] = desired_username

            # Avoid UniqueViolation on update: if an existing user (same iss+sub) would be
            # updated to desired_username but that username is already taken by a different user,
            # use a unique variant so the UPDATE does not violate user_username_key.
            desired = user_info.get("preferred_username")
            if desired and sub:
                existing_user = (
                    UserModel.query.filter(UserModel.service == iss)
                    .filter(UserModel.service_id == sub)
                    .first()
                )
                if existing_user and existing_user.username != desired:
                    other = UserModel.query.filter(UserModel.username == desired).first()
                    if other is not None and other.id != existing_user.id:
                        disambiguator = (sub.replace("-", "")[:8]) or "0"
                        unique_username = f"{desired}_{disambiguator}"
                        user_info = user_info.copy()
                        user_info["preferred_username"] = unique_username

        return original_create_user_from_sign_in(user_info)

    AuthorizationService.create_user_from_sign_in = patched_create_user_from_sign_in
    _PATCHED = True
