from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from m8flow_backend.services import process_instance_processor_patch


def test_apply_injects_workflow_data_objects_into_script_evaluation(monkeypatch) -> None:
    fake_interfaces_module = ModuleType("spiffworkflow_backend.interfaces")
    fake_human_task_user_module = ModuleType("spiffworkflow_backend.models.human_task_user")
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")

    class FakeAddedBy:
        guest = SimpleNamespace(value="guest")
        process_initiator = SimpleNamespace(value="process_initiator")
        lane_owner = SimpleNamespace(value="lane_owner")
        lane_assignment = SimpleNamespace(value="lane_assignment")

    class FakeCustomBpmnScriptEngine:
        calls: list[dict[str, object] | None] = []

        def evaluate(self, task, expression: str, external_context: dict | None = None):  # noqa: ANN001
            FakeCustomBpmnScriptEngine.calls.append(external_context)
            return external_context

    class FakeProcessInstanceProcessor:
        get_tasks_with_data_calls: list[object] = []

        @classmethod
        def get_tasks_with_data(cls, workflow):
            cls.get_tasks_with_data_calls.append(workflow)
            return [
                SimpleNamespace(data={"decision": "Rejected"}, last_state_change=1.0),
                SimpleNamespace(data={"amount": 300}, last_state_change=2.0),
            ]

    fake_interfaces_module.PotentialOwnerIdList = dict
    fake_human_task_user_module.HumanTaskUserAddedBy = FakeAddedBy
    fake_user_service_module.UserService = SimpleNamespace()
    fake_processor_module.CustomBpmnScriptEngine = FakeCustomBpmnScriptEngine
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.interfaces", fake_interfaces_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.human_task_user", fake_human_task_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_processor",
        fake_processor_module,
    )
    monkeypatch.setattr(process_instance_processor_patch, "_PATCHED", False)

    process_instance_processor_patch.apply()

    engine = FakeCustomBpmnScriptEngine()
    task = SimpleNamespace(
        workflow=SimpleNamespace(
            data={"data_objects": {"decision": "Draft"}, "amount": 250},
            data_objects={"decision": "Approved"},
        )
    )

    result = engine.evaluate(task, "amount <= 500", external_context={"decision": "Approved", "finance_decision": "Approved"})

    assert result == {"amount": 300, "decision": "Approved", "finance_decision": "Approved"}
    assert FakeCustomBpmnScriptEngine.calls == [
        {"amount": 300, "decision": "Approved", "finance_decision": "Approved"}
    ]
    assert FakeProcessInstanceProcessor.get_tasks_with_data_calls == [task.workflow]


def test_apply_resolves_lane_owners_from_workflow_data_when_task_data_is_empty(monkeypatch) -> None:
    fake_interfaces_module = ModuleType("spiffworkflow_backend.interfaces")
    fake_human_task_user_module = ModuleType("spiffworkflow_backend.models.human_task_user")
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")

    class FakeAddedBy:
        guest = SimpleNamespace(value="guest")
        process_initiator = SimpleNamespace(value="process_initiator")
        lane_owner = SimpleNamespace(value="lane_owner")
        lane_assignment = SimpleNamespace(value="lane_assignment")

    class FakeCustomBpmnScriptEngine:
        def evaluate(self, task, expression: str, external_context: dict | None = None):  # noqa: ANN001
            return external_context

    class FakeProcessInstanceProcessor:
        def __init__(self) -> None:
            self.process_instance_model = SimpleNamespace(process_initiator_id=99)

        @classmethod
        def get_tasks_with_data(cls, workflow):
            return []

        @staticmethod
        def raise_if_no_potential_owners(potential_owners, message: str) -> None:
            if not potential_owners:
                raise AssertionError(message)

    fake_interfaces_module.PotentialOwnerIdList = dict
    fake_human_task_user_module.HumanTaskUserAddedBy = FakeAddedBy
    fake_user_service_module.UserService = SimpleNamespace(
        find_or_create_group=lambda identifier: SimpleNamespace(id=11, user_group_assignments=[])
    )
    fake_processor_module.CustomBpmnScriptEngine = FakeCustomBpmnScriptEngine
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.interfaces", fake_interfaces_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.human_task_user", fake_human_task_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_processor",
        fake_processor_module,
    )
    monkeypatch.setattr(process_instance_processor_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_processor_patch,
        "current_app",
        SimpleNamespace(config={"SPIFFWORKFLOW_BACKEND_USE_LANES_FOR_TASK_ASSIGNMENT": True}),
    )
    monkeypatch.setattr(
        process_instance_processor_patch,
        "find_users_for_current_tenant_by_identifier",
        lambda username_or_email: [SimpleNamespace(id=42)] if username_or_email == "reviewer" else [],
    )

    process_instance_processor_patch.apply()

    processor = FakeProcessInstanceProcessor()
    task = SimpleNamespace(
        task_spec=SimpleNamespace(lane="Finance", extensions={}),
        data={},
        workflow=SimpleNamespace(
            data={"data_objects": {"lane_owners": {"Finance": ["reviewer"]}}},
            data_objects={"lane_owners": {"Finance": ["reviewer"]}},
        ),
    )

    result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_owner", "user_id": 42}],
        "lane_assignment_id": 11,
    }
