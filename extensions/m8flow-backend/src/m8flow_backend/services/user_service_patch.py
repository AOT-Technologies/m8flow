from __future__ import annotations

from sqlalchemy import and_, or_

from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel
from spiffworkflow_backend.services import user_service

from m8flow_backend.models.human_task import HumanTaskModel
from m8flow_backend.models.human_task_user import HumanTaskUserAddedBy, HumanTaskUserModel

_PATCHED = False


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    def patched(cls, user: UserModel, new_group_ids: set[int], old_group_ids: set[int]) -> None:
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

    user_service.UserService.update_human_task_assignments_for_user = classmethod(patched)  # type: ignore[assignment]
    _PATCHED = True
