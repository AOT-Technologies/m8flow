from __future__ import annotations

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username

_PATCHED = False


def apply() -> None:
    """Patch report queries so initiator filters resolve users within the current tenant."""
    global _PATCHED
    if _PATCHED:
        return

    from flask_sqlalchemy.query import Query
    from sqlalchemy.orm import selectinload

    from spiffworkflow_backend.exceptions.api_error import ApiError
    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
    from spiffworkflow_backend.models.process_instance_report import FilterValue
    from spiffworkflow_backend.services.process_instance_report_service import ProcessInstanceReportService
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    original_add_human_task_fields = ProcessInstanceReportService.add_human_task_fields.__func__

    @classmethod
    def patched_get_basic_query(cls, filters: list[FilterValue]) -> Query:
        """Build the report base query with tenant-aware process initiator resolution."""
        process_instance_query: Query = ProcessInstanceModel.query
        process_instance_query = process_instance_query.options(selectinload(ProcessInstanceModel.process_initiator))

        for value in cls.check_filter_value(filters, "process_model_identifier"):
            process_model = ProcessModelService.get_process_model(f"{value}")
            process_instance_query = process_instance_query.filter_by(process_model_identifier=process_model.id)

        if ProcessInstanceModel.start_in_seconds is None or ProcessInstanceModel.end_in_seconds is None:
            raise ApiError(
                error_code="unexpected_condition",
                message="Something went very wrong",
                status_code=500,
            )

        for value in cls.check_filter_value(filters, "start_from"):
            process_instance_query = process_instance_query.filter(ProcessInstanceModel.start_in_seconds >= value)
        for value in cls.check_filter_value(filters, "start_to"):
            process_instance_query = process_instance_query.filter(ProcessInstanceModel.start_in_seconds <= value)
        for value in cls.check_filter_value(filters, "end_from"):
            process_instance_query = process_instance_query.filter(ProcessInstanceModel.end_in_seconds >= value)
        for value in cls.check_filter_value(filters, "end_to"):
            process_instance_query = process_instance_query.filter(ProcessInstanceModel.end_in_seconds <= value)

        has_active_status = cls.get_filter_value(filters, "has_active_status")
        if has_active_status:
            process_instance_query = process_instance_query.filter(
                ProcessInstanceModel.status.in_(ProcessInstanceModel.active_statuses())  # type: ignore[arg-type]
            )

        for value in cls.check_filter_value(filters, "process_initiator_username"):
            initiators = find_users_for_current_tenant_by_username(value)
            if initiators:
                process_instance_query = process_instance_query.filter(
                    ProcessInstanceModel.process_initiator_id.in_([initiator.id for initiator in initiators])  # type: ignore[arg-type]
                )
            else:
                process_instance_query = process_instance_query.filter_by(process_initiator_id=-1)

        for value in cls.check_filter_value(filters, "last_milestone_bpmn_name"):
            if value:
                process_instance_query = process_instance_query.filter(
                    ProcessInstanceModel.last_milestone_bpmn_name == value
                )

        return process_instance_query

    @classmethod
    def patched_add_human_task_fields(cls, process_instance_dicts: list[dict], restrict_human_tasks_to_user=None) -> list[dict]:
        """Keep report task ownership displays tenant-friendly without changing stored identifiers."""
        results = original_add_human_task_fields(
            cls,
            process_instance_dicts,
            restrict_human_tasks_to_user=restrict_human_tasks_to_user,
        )
        for process_instance_dict in results:
            assigned_user_group_identifier = process_instance_dict.get("assigned_user_group_identifier")
            if isinstance(assigned_user_group_identifier, str):
                process_instance_dict["assigned_user_group_identifier"] = display_group_identifier(
                    assigned_user_group_identifier
                )
        return results

    ProcessInstanceReportService.get_basic_query = patched_get_basic_query
    ProcessInstanceReportService.add_human_task_fields = patched_add_human_task_fields
    _PATCHED = True
