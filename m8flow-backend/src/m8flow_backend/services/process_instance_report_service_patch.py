from __future__ import annotations

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username

_PATCHED = False


def apply() -> None:
    """Patch report queries so initiator filters resolve users within the current tenant."""
    global _PATCHED
    if _PATCHED:
        return

    from flask import request as flask_request
    from flask_sqlalchemy.query import Query
    from sqlalchemy.orm import selectinload

    from spiffworkflow_backend.exceptions.api_error import ApiError
    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
    from spiffworkflow_backend.models.process_instance_report import FilterValue
    from spiffworkflow_backend.services.process_instance_report_service import ProcessInstanceReportService
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.tenancy import is_super_admin_request

    original_add_human_task_fields = ProcessInstanceReportService.add_human_task_fields.__func__
    original_add_metadata_columns_method = getattr(
        ProcessInstanceReportService,
        "add_metadata_columns_to_process_instance",
        None,
    )
    original_add_metadata_columns = (
        original_add_metadata_columns_method.__func__
        if original_add_metadata_columns_method is not None
        else None
    )

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

        # Super admin tenant filter: supported via report filter_by or query param.
        if is_super_admin_request():
            # Check filter_by for tenant_id field (sent in POST body from UI)
            for value in cls.check_filter_value(filters, "tenant_id"):
                if value:
                    process_instance_query = process_instance_query.filter(
                        ProcessInstanceModel.m8f_tenant_id == value
                    )
            # Also accept tenantId query param as fallback
            if not cls.get_filter_value(filters, "tenant_id"):
                try:
                    filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
                except RuntimeError:
                    filter_tenant_id = None
                if filter_tenant_id:
                    process_instance_query = process_instance_query.filter(
                        ProcessInstanceModel.m8f_tenant_id == filter_tenant_id
                    )

        return process_instance_query

    if original_add_metadata_columns is not None:
        @classmethod
        def patched_add_metadata_columns_to_process_instance(cls, process_instance_sqlalchemy_rows, metadata_columns):
            """Add metadata columns and inject tenantId/tenantName for super admin."""
            results = original_add_metadata_columns(cls, process_instance_sqlalchemy_rows, metadata_columns)

            if not is_super_admin_request():
                return results

            # Collect tenant ids from the raw PI models
            tenant_ids: set[str] = set()
            for row in process_instance_sqlalchemy_rows:
                pi = row[0] if hasattr(row, "__getitem__") else row
                tid = getattr(pi, "m8f_tenant_id", None)
                if isinstance(tid, str) and tid:
                    tenant_ids.add(tid)

            tenant_name_by_id: dict[str, str] = {}
            if tenant_ids:
                tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
                tenant_name_by_id = {t.id: t.name for t in tenants}

            for i, (result_dict, row) in enumerate(zip(results, process_instance_sqlalchemy_rows)):
                pi = row[0] if hasattr(row, "__getitem__") else row
                tid = getattr(pi, "m8f_tenant_id", None)
                result_dict["tenantId"] = tid
                result_dict["tenantName"] = tenant_name_by_id.get(tid) if isinstance(tid, str) else None

            return results

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
    if original_add_metadata_columns is not None:
        ProcessInstanceReportService.add_metadata_columns_to_process_instance = patched_add_metadata_columns_to_process_instance
    ProcessInstanceReportService.add_human_task_fields = patched_add_human_task_fields
    _PATCHED = True
