from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from flask import Flask

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


def _setup_potential_owner_patch_fakes(monkeypatch, existing_groups=None, lane_owner_users=None):  # noqa: ANN001
    fake_spiff_task_module = ModuleType("SpiffWorkflow.task")
    fake_interfaces_module = ModuleType("spiffworkflow_backend.interfaces")
    fake_group_module = ModuleType("spiffworkflow_backend.models.group")
    fake_human_task_user_module = ModuleType("spiffworkflow_backend.models.human_task_user")
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")

    class FakeAddedBy:
        guest = SimpleNamespace(value="guest")
        process_initiator = SimpleNamespace(value="process_initiator")
        lane_owner = SimpleNamespace(value="lane_owner")
        lane_assignment = SimpleNamespace(value="lane_assignment")

    group_models = existing_groups or {}
    lane_owner_map = lane_owner_users or {}
    group_lookups: list[str] = []
    created_group_identifiers: list[str] = []

    class FakeGroupQuery:
        def filter_by(self, **kwargs):
            identifier = kwargs["identifier"]
            group_lookups.append(identifier)
            return SimpleNamespace(first=lambda: group_models.get(identifier))

    class FakeGroupModel:
        query = FakeGroupQuery()

    class FakeUserService:
        @classmethod
        def find_or_create_guest_user(cls):
            return SimpleNamespace(id=999)

        @classmethod
        def find_or_create_group(cls, identifier: str):
            created_group_identifiers.append(identifier)
            group_model = group_models.get(identifier)
            if group_model is None:
                group_model = SimpleNamespace(
                    id=1000 + len(created_group_identifiers),
                    identifier=identifier,
                    user_group_assignments=[],
                )
                group_models[identifier] = group_model
            return group_model

    class FakeCustomBpmnScriptEngine:
        def evaluate(self, task, expression: str, external_context: dict | None = None):  # noqa: ANN001
            return external_context

    class FakeProcessInstanceProcessor:
        def __init__(self):
            self.process_instance_model = SimpleNamespace(process_initiator_id=321)

        def raise_if_no_potential_owners(self, potential_owners, message: str):  # noqa: ANN001
            if not potential_owners:
                raise RuntimeError(message)

    fake_spiff_task_module.Task = object
    fake_interfaces_module.PotentialOwnerIdList = dict
    fake_group_module.GroupModel = FakeGroupModel
    fake_human_task_user_module.HumanTaskUserAddedBy = FakeAddedBy
    fake_user_service_module.UserService = FakeUserService
    fake_processor_module.CustomBpmnScriptEngine = FakeCustomBpmnScriptEngine
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor

    monkeypatch.setitem(sys.modules, "SpiffWorkflow.task", fake_spiff_task_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.interfaces", fake_interfaces_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.group", fake_group_module)
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
        "find_users_for_current_tenant_by_identifier",
        lambda username_or_email: lane_owner_map.get(username_or_email, []),
    )
    monkeypatch.setattr(
        process_instance_processor_patch,
        "qualify_group_identifier",
        lambda group_identifier: f"tenant-a:{group_identifier}" if ":" not in group_identifier else group_identifier,
    )

    return FakeProcessInstanceProcessor, group_lookups, created_group_identifiers


def test_get_potential_owners_from_task_lane_owners_win_over_group_assignment(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:/Engineering": SimpleNamespace(
                id=41,
                user_group_assignments=[SimpleNamespace(user_id=7)],
            )
        },
        lane_owner_users={"owner@example.com": [SimpleNamespace(id=91)]},
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Engineering", extensions={}),
            data={"lane_owners": {"Engineering": ["owner@example.com"]}},
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_owner", "user_id": 91}],
        "lane_assignment_id": None,
    }
    assert group_lookups == []
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_reads_lane_owners_from_workflow_data_objects(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:/Manager": SimpleNamespace(
                id=41,
                user_group_assignments=[SimpleNamespace(user_id=7)],
            )
        },
        lane_owner_users={"admin": [SimpleNamespace(id=91)]},
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Manager", extensions={}),
            data={},
            workflow=SimpleNamespace(
                data={"data_objects": {"lane_owners": {"Manager": ["admin"]}}},
                data_objects={"lane_owners": {"Manager": ["admin"]}},
            ),
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_owner", "user_id": 91}],
        "lane_assignment_id": None,
    }
    assert group_lookups == []
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_raises_when_explicit_lane_owner_users_do_not_exist(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        lane_owner_users={},
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Employee", extensions={}),
            data={"lane_owners": {"Employee": ["submitter"]}},
        )

        try:
            processor.get_potential_owners_from_task(task)
            raised_message = None
        except RuntimeError as exc:
            raised_message = str(exc)

    assert group_lookups == []
    assert created_group_identifiers == []
    assert (
        raised_message
        == "No users found in task data lane owner list for lane: Employee. The user list used: ['submitter']"
    )


def test_get_potential_owners_from_task_resolves_bare_lane_to_existing_org_group(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:/Engineering": SimpleNamespace(
                id=41,
                user_group_assignments=[SimpleNamespace(user_id=7), SimpleNamespace(user_id=8)],
            )
        },
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Engineering", extensions={}),
            data={},
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [
            {"added_by": "lane_assignment", "user_id": 7},
            {"added_by": "lane_assignment", "user_id": 8},
        ],
        "lane_assignment_id": 41,
    }
    assert group_lookups == ["tenant-a:/Engineering"]
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_resolves_full_path_lane_to_existing_org_group(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:/Engineering": SimpleNamespace(
                id=52,
                user_group_assignments=[SimpleNamespace(user_id=12)],
            )
        },
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="/Engineering", extensions={}),
            data={},
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_assignment", "user_id": 12}],
        "lane_assignment_id": 52,
    }
    assert group_lookups == ["tenant-a:/Engineering"]
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_keeps_lane_assignment_for_existing_empty_group(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:/Operations": SimpleNamespace(
                id=77,
                user_group_assignments=[],
            )
        },
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Operations", extensions={}),
            data={},
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [],
        "lane_assignment_id": 77,
    }
    assert group_lookups == ["tenant-a:/Operations"]
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_falls_back_to_existing_legacy_raw_group(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={
            "tenant-a:reviewer": SimpleNamespace(
                id=61,
                user_group_assignments=[SimpleNamespace(user_id=23)],
            )
        },
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="reviewer", extensions={}),
            data={},
        )

        result = processor.get_potential_owners_from_task(task)

    assert result == {
        "potential_owners": [{"added_by": "lane_assignment", "user_id": 23}],
        "lane_assignment_id": 61,
    }
    assert group_lookups == ["tenant-a:/reviewer", "tenant-a:reviewer"]
    assert created_group_identifiers == []


def test_get_potential_owners_from_task_creates_placeholder_group_when_no_matching_group_exists(monkeypatch) -> None:
    FakeProcessor, group_lookups, created_group_identifiers = _setup_potential_owner_patch_fakes(
        monkeypatch,
        existing_groups={},
    )
    process_instance_processor_patch.apply()
    app = Flask(__name__)

    with app.app_context():
        processor = FakeProcessor()
        task = SimpleNamespace(
            task_spec=SimpleNamespace(lane="Operations", extensions={}),
            data={},
        )

        result = processor.get_potential_owners_from_task(task)

    assert group_lookups == ["tenant-a:/Operations", "tenant-a:Operations"]
    assert created_group_identifiers == ["tenant-a:/Operations"]
    assert result == {
        "potential_owners": [],
        "lane_assignment_id": 1001,
    }
