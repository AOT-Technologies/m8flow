from __future__ import annotations

import logging
import re

from sqlalchemy import and_, or_

from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel
from spiffworkflow_backend.services import user_service

from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier
from m8flow_backend.services.tenant_identity_helpers import is_group_for_tenant
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier

_PATCHED = False

logger = logging.getLogger(__name__)


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    # Patch 0: centralize tenant-qualified group identifiers.
    original_find_or_create_group = user_service.UserService.find_or_create_group.__func__

    @classmethod
    def patched_find_or_create_group(cls, group_identifier: str, source_is_open_id: bool = False):
        qualified_group_identifier = qualify_group_identifier(group_identifier)
        return original_find_or_create_group(
            cls,
            qualified_group_identifier,
            source_is_open_id=source_is_open_id,
        )

    user_service.UserService.find_or_create_group = patched_find_or_create_group
    logger.info("find_or_create_group_patch: tenant-qualifying group identifiers")

    # Patch 1: handle duplicate emails by narrowing matches to the current tenant.
    @classmethod
    def patched_add_user_to_group_or_add_to_waiting(cls, username_or_email: str, group_identifier: str):
        """
        Handle multiple users with the same email in multi-tenant mode.

        Only users in the current tenant context are added.
        """
        group = cls.find_or_create_group(group_identifier)
        users = find_users_for_current_tenant_by_identifier(username_or_email)

        if users:
            user_to_group_identifiers = []
            for user in users:
                user_to_group_identifiers.append({"username": user.username, "group_identifier": group.identifier})
                cls.add_user_to_group(user, group)
            return (None, user_to_group_identifiers)

        return cls.add_waiting_group_assignment(username_or_email, group)

    user_service.UserService.add_user_to_group_or_add_to_waiting = patched_add_user_to_group_or_add_to_waiting
    logger.info("UserService.add_user_to_group_or_add_to_waiting patched for multi-tenant email duplicates")

    @classmethod
    def patched_apply_waiting_group_assignments(cls, user: UserModel) -> None:
        tenant_identifiers = current_tenant_identifiers()

        waiting = (
            user_service.UserGroupAssignmentWaitingModel()
            .query.filter(
                user_service.UserGroupAssignmentWaitingModel.username.in_([user.username, user.email])  # type: ignore[arg-type]
            )
            .all()
        )
        for assignment in waiting:
            if tenant_identifiers and not any(
                is_group_for_tenant(assignment.group.identifier, tenant_id) for tenant_id in tenant_identifiers
            ):
                continue
            cls.add_user_to_group(user, assignment.group)
            db.session.delete(assignment)

        wildcards = (
            user_service.UserGroupAssignmentWaitingModel()
            .query.filter(user_service.UserGroupAssignmentWaitingModel.username.regexp_match("^REGEX:"))  # type: ignore[arg-type]
            .all()
        )
        for wildcard in wildcards:
            if tenant_identifiers and not any(
                is_group_for_tenant(wildcard.group.identifier, tenant_id) for tenant_id in tenant_identifiers
            ):
                continue
            pattern = wildcard.pattern_from_wildcard_username()
            if pattern is not None and (
                re.match(pattern, user.username) or (user.email and re.match(pattern, user.email))
            ):
                cls.add_user_to_group(user, wildcard.group)
        db.session.commit()

    user_service.UserService.apply_waiting_group_assignments = patched_apply_waiting_group_assignments
    logger.info("apply_waiting_group_assignments_patch: limiting waiting assignments to current-tenant groups")

    # Patch 2: keep human-task lane assignment updates tenant-safe.
    def patched_update_human_task_assignments(
        cls,
        user: UserModel,
        new_group_ids: set[int],
        old_group_ids: set[int],
    ) -> None:
        from m8flow_backend.models.human_task import HumanTaskModel
        from m8flow_backend.models.human_task_user import HumanTaskUserAddedBy, HumanTaskUserModel

        with db.session.no_autoflush:
            current_assignments = HumanTaskUserModel.query.filter(HumanTaskUserModel.user_id == user.id).all()
            current_human_task_ids = {assignment.human_task_id for assignment in current_assignments}

            human_tasks = (
                HumanTaskModel.query.outerjoin(HumanTaskUserModel)
                .filter(
                    HumanTaskModel.lane_assignment_id.in_(new_group_ids),  # type: ignore[arg-type]
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

        to_delete = (
            HumanTaskUserModel.query.join(HumanTaskModel)
            .filter(
                HumanTaskUserModel.user_id == user.id,
                HumanTaskUserModel.added_by == HumanTaskUserAddedBy.lane_assignment.value,
                HumanTaskModel.lane_assignment_id.in_(old_group_ids),  # type: ignore[arg-type]
                HumanTaskModel.completed == False,  # noqa: E712
                HumanTaskUserModel.m8f_tenant_id == HumanTaskModel.m8f_tenant_id,
            )
            .all()
        )
        for row in to_delete:
            db.session.delete(row)

        db.session.commit()

    user_service.UserService.update_human_task_assignments_for_user = classmethod(
        patched_update_human_task_assignments
    )
    _PATCHED = True
