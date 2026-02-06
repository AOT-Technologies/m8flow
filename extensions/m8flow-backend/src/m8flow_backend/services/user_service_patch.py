# user_service_patch.py
from __future__ import annotations
import logging
from sqlalchemy import or_

_PATCHED = False
logger = logging.getLogger(__name__)

def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    try:
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
        """Patch to handle multiple users with the same email in multi-tenant mode."""
        group = cls.find_or_create_group(group_identifier)
        
        # In multi-tenant mode, multiple users might have the same email but different usernames.
        # We find ALL matching users and add them all to the group.
        users = UserModel.query.filter(or_(UserModel.username == username_or_email, UserModel.email == username_or_email)).all()
        
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
