from __future__ import annotations

import sys
from types import ModuleType

from m8flow_backend.services import process_instance_report_service_patch


def test_apply_rewrites_assigned_group_identifier_for_report_display(monkeypatch) -> None:
    fake_service_module = ModuleType("spiffworkflow_backend.services.process_instance_report_service")
    fake_process_model_service_module = ModuleType("spiffworkflow_backend.services.process_model_service")
    fake_process_instance_module = ModuleType("spiffworkflow_backend.models.process_instance")
    fake_process_instance_report_module = ModuleType("spiffworkflow_backend.models.process_instance_report")
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")

    class FakeProcessInstanceReportService:
        @classmethod
        def get_basic_query(cls, filters):
            return filters

        @classmethod
        def add_human_task_fields(cls, process_instance_dicts: list[dict], restrict_human_tasks_to_user=None) -> list[dict]:
            return [
                {"id": 1, "assigned_user_group_identifier": "tenant-id:Manager"},
                {"id": 2, "assigned_user_group_identifier": "already-a-slug:Finance"},
                {"id": 3, "potential_owner_usernames": "alex"},
            ]

    class FakeProcessModelService:
        @classmethod
        def get_process_model(cls, identifier: str):
            return identifier

    class FakeProcessInstanceModel:
        pass

    class FakeApiError(Exception):
        pass

    fake_service_module.ProcessInstanceReportService = FakeProcessInstanceReportService
    fake_process_model_service_module.ProcessModelService = FakeProcessModelService
    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel
    fake_process_instance_report_module.FilterValue = dict
    fake_api_error_module.ApiError = FakeApiError

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_report_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_model_service",
        fake_process_model_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance_report",
        fake_process_instance_report_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.exceptions.api_error",
        fake_api_error_module,
    )
    monkeypatch.setattr(process_instance_report_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_report_service_patch,
        "display_group_identifier",
        lambda group_identifier: {
            "tenant-id:Manager": "tenant-slug:Manager",
            "already-a-slug:Finance": "already-a-slug:Finance",
        }.get(group_identifier, group_identifier),
    )

    process_instance_report_service_patch.apply()
    results = FakeProcessInstanceReportService.add_human_task_fields([{"id": 1}])

    assert results[0]["assigned_user_group_identifier"] == "tenant-slug:Manager"
    assert results[1]["assigned_user_group_identifier"] == "already-a-slug:Finance"
    assert results[2]["potential_owner_usernames"] == "alex"
