# user_service_patch.py
from __future__ import annotations
import logging
from sqlalchemy import or_

_PATCHED = False
logger = logging.getLogger(__name__)


def _realm_from_service(service: str) -> str:
    """Extract realm from Keycloak issuer URL, e.g. http://localhost:7002/realms/foo -> foo."""
    if not service:
        return "unknown"
    s = (service or "").rstrip("/")
    if "/realms/" in s:
        return s.split("/realms/")[-1].split("/")[0]
    return s.replace("://", "_").replace("/", "_")[-32:] or "unknown"


def _user_belongs_to_tenant(username: str, service: str, current_tenant_id: str) -> bool:
    """True if the user belongs to current_tenant_id. Tenant is derived from username suffix or service when no tenant column exists."""
    if not current_tenant_id:
        return True
    if username.endswith("@" + current_tenant_id):
        return True
    if "@" not in username and _realm_from_service(service) == current_tenant_id:
        return True
    return False


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    try:
        from flask import g
        from spiffworkflow_backend.services.user_service import UserService
        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.models.db import db
    except ImportError:
        logger.error("Could not import UserService or UserModel for patching")
        return

    _ORIGINAL_ADD_USER_TO_GROUP_OR_ADD_TO_WAITING = UserService.add_user_to_group_or_add_to_waiting

    @classmethod
    def patched_add_user_to_group_or_add_to_waiting(
        cls, username_or_email: str, group_identifier: str
    ):
        """Patch to handle multiple users with the same email in multi-tenant mode. Only users in the current tenant context are added; tenant is derived from username suffix or service when no tenant column exists."""
        group = cls.find_or_create_group(group_identifier)

        base = UserModel.query.filter(
            or_(UserModel.username == username_or_email, UserModel.email == username_or_email)
        ).all()
        current_tenant_id = getattr(g, "m8flow_tenant_id", None) or ""
        users = [u for u in base if _user_belongs_to_tenant(u.username, getattr(u, "service", "") or "", current_tenant_id)]

        if users:
            user_to_group_identifiers = []
            for user in users:
                user_to_group_identifiers.append({"username": user.username, "group_identifier": group.identifier})
                cls.add_user_to_group(user, group)
            return (None, user_to_group_identifiers)
        else:
            return cls.add_waiting_group_assignment(username_or_email, group)

    UserService.add_user_to_group_or_add_to_waiting = patched_add_user_to_group_or_add_to_waiting
    _PATCHED = True
    logger.info("UserService.add_user_to_group_or_add_to_waiting patched to handle multi-tenant email duplicates")
