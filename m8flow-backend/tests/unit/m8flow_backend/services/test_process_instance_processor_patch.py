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


def _setup_processor_patch_fakes(monkeypatch, completed_tasks_with_data=None):  # noqa: ANN001
    """Return (FakeEngine class, apply_fn) with all spiffworkflow modules monkeypatched."""
    fake_interfaces_module = ModuleType("spiffworkflow_backend.interfaces")
    fake_human_task_user_module = ModuleType("spiffworkflow_backend.models.human_task_user")
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")
    fake_task_module = ModuleType("SpiffWorkflow.task")

    class FakeAddedBy:
        guest = SimpleNamespace(value="guest")
        process_initiator = SimpleNamespace(value="process_initiator")
        lane_owner = SimpleNamespace(value="lane_owner")
        lane_assignment = SimpleNamespace(value="lane_assignment")

    tasks = completed_tasks_with_data or []

    class FakeCustomBpmnScriptEngine:
        calls: list[dict[str, object] | None] = []

        def evaluate(self, task, expression: str, external_context: dict | None = None):  # noqa: ANN001
            FakeCustomBpmnScriptEngine.calls.append(external_context)
            return external_context

    class FakeProcessInstanceProcessor:
        @classmethod
        def get_tasks_with_data(cls, _workflow):  # noqa: ANN001
            return tasks

        def __init__(self):
            self.process_instance_model = SimpleNamespace(process_initiator_id=777)

        @staticmethod
        def raise_if_no_potential_owners(potential_owners, _message):  # noqa: ANN001
            if not potential_owners:
                raise AssertionError("expected potential owners")

    class FakeGroupModel:
        def __init__(self, identifier: str):
            self.id = 33
            self.identifier = identifier
            self.user_group_assignments = []

    class FakeUserServiceClass:
        @staticmethod
        def find_or_create_guest_user():
            return SimpleNamespace(id=999)

        @staticmethod
        def find_or_create_group(identifier: str):
            return FakeGroupModel(identifier)

    fake_interfaces_module.PotentialOwnerIdList = dict
    fake_human_task_user_module.HumanTaskUserAddedBy = FakeAddedBy
    fake_user_service_module.UserService = FakeUserServiceClass
    fake_processor_module.CustomBpmnScriptEngine = FakeCustomBpmnScriptEngine
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor
    fake_task_module.Task = object

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.interfaces", fake_interfaces_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.human_task_user", fake_human_task_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(sys.modules, "SpiffWorkflow.task", fake_task_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_processor",
        fake_processor_module,
    )
    monkeypatch.setattr(process_instance_processor_patch, "_PATCHED", False)

    return FakeCustomBpmnScriptEngine, FakeProcessInstanceProcessor


def test_evaluate_exposes_completed_task_variable_when_no_external_context_provided(monkeypatch) -> None:
    """Regression: after Celery rehydration the gateway's task.data is {}; decision must reach
    the script engine via completed-task injection so the gateway condition does not raise NameError."""
    FakeEngine, _FakeProcessor = _setup_processor_patch_fakes(
        monkeypatch,
        completed_tasks_with_data=[
            SimpleNamespace(data={"decision": "Rejected"}, last_state_change=1.0),
        ],
    )
    process_instance_processor_patch.apply()

    engine = FakeEngine()
    task = SimpleNamespace(workflow=SimpleNamespace(data={}, data_objects={}))

    result = engine.evaluate(task, "decision")

    assert result == {"decision": "Rejected"}
    assert FakeEngine.calls == [{"decision": "Rejected"}]


def test_evaluate_exposes_rehydrated_data_objects_without_external_context(monkeypatch) -> None:
    """After patched_run_process_instance_with_processor sets bpmn_process_instance.data['data_objects'],
    patched_evaluate must inject those variables even when no external_context is passed."""
    FakeEngine, _FakeProcessor = _setup_processor_patch_fakes(monkeypatch, completed_tasks_with_data=[])
    process_instance_processor_patch.apply()

    engine = FakeEngine()
    task = SimpleNamespace(
        workflow=SimpleNamespace(
            data={"data_objects": {"decision": "Approved", "lane_owners": {"Manager": ["editor"]}}},
            data_objects={},
        )
    )

    result = engine.evaluate(task, "decision")

    assert result == {"decision": "Approved", "lane_owners": {"Manager": ["editor"]}}
    assert FakeEngine.calls == [{"decision": "Approved", "lane_owners": {"Manager": ["editor"]}}]


def test_evaluate_external_context_takes_priority_over_completed_task_data(monkeypatch) -> None:
    """external_context must win over completed-task data so callers can always override the context."""
    FakeEngine, _FakeProcessor = _setup_processor_patch_fakes(
        monkeypatch,
        completed_tasks_with_data=[
            SimpleNamespace(data={"decision": "Rejected"}, last_state_change=1.0),
        ],
    )
    process_instance_processor_patch.apply()

    engine = FakeEngine()
    task = SimpleNamespace(workflow=SimpleNamespace(data={}, data_objects={}))

    result = engine.evaluate(task, "decision", external_context={"decision": "Approved"})

    assert result == {"decision": "Approved"}
    assert FakeEngine.calls == [{"decision": "Approved"}]


def test_get_potential_owners_uses_workflow_level_lane_owners_when_task_data_is_empty(monkeypatch) -> None:
    FakeEngine, FakeProcessor = _setup_processor_patch_fakes(monkeypatch, completed_tasks_with_data=[])
    monkeypatch.setattr(
        process_instance_processor_patch,
        "find_users_for_current_tenant_by_identifier",
        lambda username: [SimpleNamespace(id=41, username=username)] if username == "reviewer" else [],
    )
    process_instance_processor_patch.apply()

    from flask import Flask

    flask_app = Flask(__name__)  # NOSONAR - unit test
    with flask_app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            data={},
            task_spec=SimpleNamespace(lane="Finance", extensions={}),
            workflow=SimpleNamespace(
                data={"data_objects": {"lane_owners": {"Finance": ["reviewer"]}}},
                data_objects={},
            ),
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_owner", "user_id": 41}],
        "lane_assignment_id": 33,
    }
