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
    "m8flow_backend.routes.keycloak_controller.create_realm",
    "m8flow_backend.routes.tenant_controller.create_tenant",
]


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

            # Extract realm from issuer URL, e.g., http://.../realms/my-realm
            if "/realms/" in iss:
                realm = iss.split("/realms/")[-1].split("/")[0]
                # Only append if not already appended (idempotency)
                suffix = f"@{realm}"
                if not username.endswith(suffix):
                    user_info = user_info.copy()
                    user_info["preferred_username"] = f"{username}{suffix}"

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
