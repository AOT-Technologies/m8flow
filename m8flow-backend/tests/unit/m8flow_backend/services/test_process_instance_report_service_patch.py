from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from m8flow_backend.services import process_instance_report_service_patch


def test_apply_rewrites_assigned_group_identifier_for_report_display(
    monkeypatch,
) -> None:
    fake_service_module = ModuleType(
        "spiffworkflow_backend.services.process_instance_report_service"
    )
    fake_process_instance_module = ModuleType(
        "spiffworkflow_backend.models.process_instance"
    )

    class FakeProcessInstanceReportService:
        @classmethod
        def get_basic_query(cls, filters):
            return filters

        @classmethod
        def add_human_task_fields(
            cls, process_instance_dicts: list[dict], restrict_human_tasks_to_user=None
        ) -> list[dict]:
            return [
                {"id": 1, "assigned_user_group_identifier": "tenant-id:Manager"},
                {"id": 2, "assigned_user_group_identifier": "already-a-slug:Finance"},
                {"id": 3, "potential_owner_usernames": "alex"},
            ]

    class FakeProcessInstanceModel:
        process_initiator_id = SimpleNamespace()
        m8f_tenant_id = SimpleNamespace()

    fake_service_module.ProcessInstanceReportService = FakeProcessInstanceReportService
    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_report_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
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


def test_get_basic_query_wraps_upstream_and_applies_tenant_initiator(
    monkeypatch,
) -> None:
    fake_service_module = ModuleType(
        "spiffworkflow_backend.services.process_instance_report_service"
    )
    fake_process_instance_module = ModuleType(
        "spiffworkflow_backend.models.process_instance"
    )

    upstream_filter_batches: list[list[dict]] = []

    class FakeQuery:
        def __init__(self) -> None:
            self.ops: list[tuple[str, object]] = []

        def filter(self, *args):
            self.ops.append(("filter", args))
            return self

        def filter_by(self, **kwargs):
            self.ops.append(("filter_by", kwargs))
            return self

    class FakeProcessInstanceReportService:
        @classmethod
        def get_basic_query(cls, filters):
            upstream_filter_batches.append(list(filters))
            return FakeQuery()

        @classmethod
        def check_filter_value(cls, filters, filter_key: str):
            for item in filters:
                if (
                    item.get("field_name") == filter_key
                    and item.get("field_value") is not None
                ):
                    yield item["field_value"]

        @classmethod
        def get_filter_value(cls, filters, filter_key: str):
            for item in filters:
                if (
                    item.get("field_name") == filter_key
                    and item.get("field_value") is not None
                ):
                    return item["field_value"]
            return None

        @classmethod
        def add_human_task_fields(
            cls, process_instance_dicts, restrict_human_tasks_to_user=None
        ):
            return process_instance_dicts

    class FakeColumn:
        def in_(self, values):
            return ("in_", tuple(values))

        def __eq__(self, other):
            return ("eq", other)

    class FakeProcessInstanceModel:
        process_initiator_id = FakeColumn()
        m8f_tenant_id = FakeColumn()

    fake_service_module.ProcessInstanceReportService = FakeProcessInstanceReportService
    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_report_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )
    monkeypatch.setattr(process_instance_report_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_report_service_patch,
        "find_users_for_current_tenant_by_username",
        lambda username: (
            [SimpleNamespace(id=11), SimpleNamespace(id=22)]
            if username == "editor"
            else []
        ),
    )
    monkeypatch.setattr(
        "m8flow_backend.tenancy.is_super_admin_request",
        lambda: False,
    )

    process_instance_report_service_patch.apply()

    filters = [
        {"field_name": "start_from", "field_value": 100},
        {"field_name": "process_initiator_username", "field_value": "editor"},
        {"field_name": "last_milestone_bpmn_name", "field_value": "Done"},
    ]
    query = FakeProcessInstanceReportService.get_basic_query(filters)

    assert upstream_filter_batches == [
        [
            {"field_name": "start_from", "field_value": 100},
            {"field_name": "last_milestone_bpmn_name", "field_value": "Done"},
        ]
    ]
    assert query.ops == [("filter", (("in_", (11, 22)),))]


class _ReportQuery:
    def __init__(self) -> None:
        self.ops: list[tuple[str, object]] = []

    def filter(self, *args):
        self.ops.append(("filter", args))
        return self

    def filter_by(self, **kwargs):
        self.ops.append(("filter_by", kwargs))
        return self


class _ReportColumn:
    def in_(self, values):
        return ("in_", tuple(values))

    def __eq__(self, other):
        return ("eq", other)


def _install_report_service_fakes(monkeypatch, *, is_super_admin: bool = False):
    fake_service_module = ModuleType(
        "spiffworkflow_backend.services.process_instance_report_service"
    )
    fake_process_instance_module = ModuleType(
        "spiffworkflow_backend.models.process_instance"
    )
    upstream_filter_batches: list[list[dict]] = []

    class FakeProcessInstanceReportService:
        @classmethod
        def get_basic_query(cls, filters):
            upstream_filter_batches.append(list(filters))
            return _ReportQuery()

        @classmethod
        def check_filter_value(cls, filters, filter_key: str):
            for item in filters:
                if (
                    item.get("field_name") == filter_key
                    and item.get("field_value") is not None
                ):
                    yield item["field_value"]

        @classmethod
        def get_filter_value(cls, filters, filter_key: str):
            for item in filters:
                if (
                    item.get("field_name") == filter_key
                    and item.get("field_value") is not None
                ):
                    return item["field_value"]
            return None

        @classmethod
        def add_human_task_fields(
            cls, process_instance_dicts, restrict_human_tasks_to_user=None
        ):
            return process_instance_dicts

        @classmethod
        def add_metadata_columns_to_process_instance(
            cls, process_instance_sqlalchemy_rows, metadata_columns
        ):
            return [{"id": row[0].id} for row in process_instance_sqlalchemy_rows]

    class FakeProcessInstanceModel:
        process_initiator_id = _ReportColumn()
        m8f_tenant_id = _ReportColumn()

    fake_service_module.ProcessInstanceReportService = FakeProcessInstanceReportService
    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_report_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )
    monkeypatch.setattr(process_instance_report_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        "m8flow_backend.tenancy.is_super_admin_request",
        lambda: is_super_admin,
    )
    return FakeProcessInstanceReportService, upstream_filter_batches


def test_get_basic_query_uses_sentinel_initiator_when_username_is_unknown(
    monkeypatch,
) -> None:
    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch
    )
    monkeypatch.setattr(
        process_instance_report_service_patch,
        "find_users_for_current_tenant_by_username",
        lambda username: [],
    )
    process_instance_report_service_patch.apply()

    query = FakeProcessInstanceReportService.get_basic_query(
        [{"field_name": "process_initiator_username", "field_value": "missing"}]
    )
    assert query.ops == [("filter_by", {"process_initiator_id": -1})]


def test_get_basic_query_applies_sa_tenant_filter_from_filters(monkeypatch) -> None:
    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch, is_super_admin=True
    )
    monkeypatch.setattr(
        process_instance_report_service_patch,
        "find_users_for_current_tenant_by_username",
        lambda username: [],
    )
    process_instance_report_service_patch.apply()

    query = FakeProcessInstanceReportService.get_basic_query(
        [{"field_name": "tenant_id", "field_value": "tenant-a"}]
    )
    assert query.ops == [("filter", (("eq", "tenant-a"),))]


def test_get_basic_query_applies_sa_tenant_filter_from_request_args(
    monkeypatch,
) -> None:
    from flask import Flask

    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch, is_super_admin=True
    )
    process_instance_report_service_patch.apply()

    app = Flask(__name__)
    with app.test_request_context("/reports?tenantId=tenant-b"):
        query = FakeProcessInstanceReportService.get_basic_query([])

    assert query.ops == [("filter", (("eq", "tenant-b"),))]


def test_get_basic_query_skips_request_arg_filter_outside_request_context(
    monkeypatch,
) -> None:
    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch, is_super_admin=True
    )
    process_instance_report_service_patch.apply()

    query = FakeProcessInstanceReportService.get_basic_query([])
    assert query.ops == []


def test_add_metadata_columns_injects_tenant_fields_for_super_admin(
    monkeypatch,
) -> None:
    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch, is_super_admin=True
    )

    class FakeTenantQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return [SimpleNamespace(id="tenant-a", name="Acme")]

    monkeypatch.setattr(
        "m8flow_backend.models.m8flow_tenant.M8flowTenantModel",
        SimpleNamespace(
            query=FakeTenantQuery(),
            id=SimpleNamespace(in_=lambda values: ("in", values)),
        ),
    )
    process_instance_report_service_patch.apply()

    rows = [(SimpleNamespace(id=1, m8f_tenant_id="tenant-a"),)]
    results = FakeProcessInstanceReportService.add_metadata_columns_to_process_instance(
        rows, []
    )
    assert results == [{"id": 1, "tenantId": "tenant-a", "tenantName": "Acme"}]


def test_add_metadata_columns_passthrough_for_non_super_admin(monkeypatch) -> None:
    FakeProcessInstanceReportService, _batches = _install_report_service_fakes(
        monkeypatch, is_super_admin=False
    )
    process_instance_report_service_patch.apply()

    rows = [(SimpleNamespace(id=1, m8f_tenant_id="tenant-a"),)]
    results = FakeProcessInstanceReportService.add_metadata_columns_to_process_instance(
        rows, []
    )
    assert results == [{"id": 1}]


def test_add_human_task_fields_leaves_non_string_group_identifier_untouched(
    monkeypatch,
) -> None:
    fake_service_module = ModuleType(
        "spiffworkflow_backend.services.process_instance_report_service"
    )
    fake_process_instance_module = ModuleType(
        "spiffworkflow_backend.models.process_instance"
    )

    class FakeProcessInstanceReportService:
        @classmethod
        def get_basic_query(cls, filters):
            return filters

        @classmethod
        def add_human_task_fields(
            cls, process_instance_dicts, restrict_human_tasks_to_user=None
        ):
            return process_instance_dicts

    fake_service_module.ProcessInstanceReportService = FakeProcessInstanceReportService
    fake_process_instance_module.ProcessInstanceModel = SimpleNamespace(
        process_initiator_id=SimpleNamespace(),
        m8f_tenant_id=SimpleNamespace(),
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_report_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )
    monkeypatch.setattr(process_instance_report_service_patch, "_PATCHED", False)
    rewritten: list[str] = []
    monkeypatch.setattr(
        process_instance_report_service_patch,
        "display_group_identifier",
        lambda group_identifier: rewritten.append(group_identifier) or group_identifier,
    )
    process_instance_report_service_patch.apply()

    results = FakeProcessInstanceReportService.add_human_task_fields(
        [
            {"assigned_user_group_identifier": None},
            {"assigned_user_group_identifier": ["Manager"]},
            {"assigned_user_group_identifier": "tenant-a:Manager"},
        ]
    )
    assert results[0]["assigned_user_group_identifier"] is None
    assert results[1]["assigned_user_group_identifier"] == ["Manager"]
    assert results[2]["assigned_user_group_identifier"] == "tenant-a:Manager"
    assert rewritten == ["tenant-a:Manager"]
