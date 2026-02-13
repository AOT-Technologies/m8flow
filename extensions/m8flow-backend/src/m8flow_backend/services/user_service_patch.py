
# user_service_patch.py
from __future__ import annotations
import logging
from sqlalchemy import and_, or_
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel
from spiffworkflow_backend.services import user_service

from m8flow_backend.models.human_task import HumanTaskModel
from m8flow_backend.models.human_task_user import HumanTaskUserAddedBy, HumanTaskUserModel

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

    # Patch 1: add_user_to_group_or_add_to_waiting — multi-tenant email handling (HEAD)
    try:
        from flask import g
        from spiffworkflow_backend.services.user_service import UserService
    except ImportError:
        logger.error("Could not import UserService for patching")
        return

    _ORIGINAL_ADD_USER_TO_GROUP_OR_ADD_TO_WAITING = user_service.UserService.add_user_to_group_or_add_to_waiting

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

    user_service.UserService.add_user_to_group_or_add_to_waiting = patched_add_user_to_group_or_add_to_waiting
    logger.info("UserService.add_user_to_group_or_add_to_waiting patched to handle multi-tenant email duplicates")

    # Patch 2: update_human_task_assignments_for_user — tenant-scoped human task assignments (main)
    def patched_update_human_task_assignments(cls, user: UserModel, new_group_ids: set[int], old_group_ids: set[int]) -> None:
        with db.session.no_autoflush:
            current_assignments = HumanTaskUserModel.query.filter(
                HumanTaskUserModel.user_id == user.id
            ).all()
            current_human_task_ids = {ca.human_task_id for ca in current_assignments}

            human_tasks = (
                HumanTaskModel.query.outerjoin(HumanTaskUserModel)
                .filter(
                    HumanTaskModel.lane_assignment_id.in_(new_group_ids),  # type: ignore
                    HumanTaskModel.completed == False,  # noqa: E712
                    or_(
                        and_(
                            HumanTaskUserModel.user_id != user.id,
                            HumanTaskUserModel.added_by == HumanTaskUserAddedBy.lane_assignment.value,
                        ),
                        HumanTaskUserModel.user_id == None,  # noqa: E711
                    ),
                )
                .distinct(HumanTaskModel.id)
                .all()
            )

        # insert (tenant comes from the task itself)
        for human_task in human_tasks:
            if human_task.id not in current_human_task_ids:
                db.session.add(
                    HumanTaskUserModel(
                        user_id=user.id,
                        human_task_id=human_task.id,
                        added_by=HumanTaskUserAddedBy.lane_assignment.value,
                        m8f_tenant_id=human_task.m8f_tenant_id,
                    )
                )

        # delete (avoid cross-tenant delete by tying tenant ids together)
        to_delete = (
            HumanTaskUserModel.query.join(HumanTaskModel)
            .filter(
                HumanTaskUserModel.user_id == user.id,
                HumanTaskUserModel.added_by == HumanTaskUserAddedBy.lane_assignment.value,
                HumanTaskModel.lane_assignment_id.in_(old_group_ids),  # type: ignore
                HumanTaskModel.completed == False,  # noqa: E712
                # tenant safety
                HumanTaskUserModel.m8f_tenant_id == HumanTaskModel.m8f_tenant_id,
            )
            .all()
        )
        for row in to_delete:
            db.session.delete(row)

        db.session.commit()

    user_service.UserService.update_human_task_assignments_for_user = classmethod(patched_update_human_task_assignments)  # type: ignore[assignment]
    _PATCHED = True
