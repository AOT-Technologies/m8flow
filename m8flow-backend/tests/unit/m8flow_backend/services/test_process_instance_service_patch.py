from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from m8flow_backend.services import process_instance_service_patch


def test_apply_forces_completed_task_data_when_rehydrating_process_instance(monkeypatch) -> None:
    fake_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")
    fake_queue_module = ModuleType("spiffworkflow_backend.services.process_instance_queue_service")
    fake_migrator_module = ModuleType("spiffworkflow_backend.data_migrations.process_instance_migrator")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_workflow_execution_module = ModuleType("spiffworkflow_backend.services.workflow_execution_service")

    class FakeTaskRunnability:
        unknown_if_ready_tasks = "unknown_if_ready_tasks"

    class FakeProcessInstanceProcessor:
        init_calls: list[dict[str, object]] = []
        do_engine_steps_calls: list[dict[str, object]] = []
        get_tasks_with_data_calls: list[object] = []
        completed_tasks_with_data: list[object] = []

        def __init__(
            self,
            process_instance_model,
            script_engine=None,
            workflow_completed_handler=None,
            process_id_to_run=None,
            include_task_data_for_completed_tasks: bool = False,
            include_completed_subprocesses: bool = False,
        ) -> None:
            self.process_instance_model = process_instance_model
            self.bpmn_process_instance = SimpleNamespace(data={"existing": "value", "data_objects": {"preexisting": "keep"}})
            self.do_engine_steps_result = FakeTaskRunnability.unknown_if_ready_tasks
            self.workflow_completed_handler = workflow_completed_handler
            self.include_task_data_for_completed_tasks = include_task_data_for_completed_tasks
            self.include_completed_subprocesses = include_completed_subprocesses
            FakeProcessInstanceProcessor.init_calls.append(
                {
                    "process_instance_model": process_instance_model,
                    "script_engine": script_engine,
                    "workflow_completed_handler": workflow_completed_handler,
                    "process_id_to_run": process_id_to_run,
                    "include_task_data_for_completed_tasks": include_task_data_for_completed_tasks,
                    "include_completed_subprocesses": include_completed_subprocesses,
                }
            )

        @classmethod
        def get_tasks_with_data(cls, bpmn_process_instance):
            cls.get_tasks_with_data_calls.append(bpmn_process_instance)
            return cls.completed_tasks_with_data

        def do_engine_steps(
            self,
            save: bool = False,
            execution_strategy_name: str | None = None,
            should_schedule_waiting_timer_events: bool = True,
        ) -> str:
            FakeProcessInstanceProcessor.do_engine_steps_calls.append(
                {
                    "save": save,
                    "execution_strategy_name": execution_strategy_name,
                    "should_schedule_waiting_timer_events": should_schedule_waiting_timer_events,
                }
            )
            return self.do_engine_steps_result

    class FakeDequeuedContext:
        def __init__(self, process_instance) -> None:
            self.process_instance = process_instance

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeProcessInstanceQueueService:
        @staticmethod
        def dequeued(process_instance):
            return FakeDequeuedContext(process_instance)

    class FakeProcessInstanceMigrator:
        run_calls: list[object] = []

        @staticmethod
        def run(process_instance) -> None:
            FakeProcessInstanceMigrator.run_calls.append(process_instance)

    class FakeDbSession:
        def __init__(self) -> None:
            self.refresh_calls: list[object] = []

        def refresh(self, process_instance) -> None:
            self.refresh_calls.append(process_instance)

    class FakeProcessInstanceService:
        @staticmethod
        def schedule_next_process_model_cycle(*args, **kwargs):
            return None

        @staticmethod
        def can_optimistically_skip(processor, status_value):
            return False

        @classmethod
        def update_form_task_data(cls, process_instance, spiff_task, data, user):
            return None

    fake_service_module.ProcessInstanceService = FakeProcessInstanceService
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor
    fake_queue_module.ProcessInstanceQueueService = FakeProcessInstanceQueueService
    fake_migrator_module.ProcessInstanceMigrator = FakeProcessInstanceMigrator
    fake_db_module.db = SimpleNamespace(session=FakeDbSession())
    fake_workflow_execution_module.TaskRunnability = FakeTaskRunnability

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_processor",
        fake_processor_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_queue_service",
        fake_queue_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.data_migrations.process_instance_migrator",
        fake_migrator_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.db",
        fake_db_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.workflow_execution_service",
        fake_workflow_execution_module,
    )
    monkeypatch.setattr(process_instance_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_service_patch,
        "current_app",
        SimpleNamespace(logger=SimpleNamespace(info=lambda *args, **kwargs: None)),
    )

    process_instance_service_patch.apply()

    completed_task_data_calls: list[None] = []

    def fake_get_data() -> dict[str, str]:
        completed_task_data_calls.append(None)
        return {"finance_decision": "Approved"}

    FakeProcessInstanceProcessor.completed_tasks_with_data = [
        SimpleNamespace(data={"decision": "Rejected"}, last_state_change=1.0),
        SimpleNamespace(data={"finance_decision": "Approved"}, last_state_change=2.0),
    ]
    process_instance = SimpleNamespace(id=3, status="complete", get_data=fake_get_data)
    returned_processor, task_runnability = FakeProcessInstanceService.run_process_instance_with_processor(process_instance)

    assert returned_processor is not None
    assert task_runnability == FakeTaskRunnability.unknown_if_ready_tasks
    assert completed_task_data_calls == [None]
    assert returned_processor.bpmn_process_instance.data == {
        "existing": "value",
        "finance_decision": "Approved",
        "data_objects": {
            "preexisting": "keep",
            "decision": "Rejected",
            "finance_decision": "Approved",
        },
    }
    assert FakeProcessInstanceMigrator.run_calls == [process_instance]
    assert fake_db_module.db.session.refresh_calls == [process_instance]
    assert FakeProcessInstanceProcessor.init_calls[0]["process_instance_model"] is process_instance
    assert FakeProcessInstanceProcessor.init_calls[0]["workflow_completed_handler"] is (
        FakeProcessInstanceService.schedule_next_process_model_cycle
    )
    assert FakeProcessInstanceProcessor.init_calls[0]["include_task_data_for_completed_tasks"] is True
    assert FakeProcessInstanceProcessor.get_tasks_with_data_calls == [returned_processor.bpmn_process_instance]
    assert FakeProcessInstanceProcessor.do_engine_steps_calls == [
        {
            "save": True,
            "execution_strategy_name": None,
            "should_schedule_waiting_timer_events": True,
        }
    ]


def test_apply_promotes_submitted_form_data_into_workflow_data_objects(monkeypatch) -> None:
    fake_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")
    fake_queue_module = ModuleType("spiffworkflow_backend.services.process_instance_queue_service")
    fake_migrator_module = ModuleType("spiffworkflow_backend.data_migrations.process_instance_migrator")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_workflow_execution_module = ModuleType("spiffworkflow_backend.services.workflow_execution_service")

    class FakeTaskRunnability:
        unknown_if_ready_tasks = "unknown_if_ready_tasks"

    class FakeProcessInstanceProcessor:
        @classmethod
        def get_tasks_with_data(cls, bpmn_process_instance):
            return []

    class FakeDequeuedContext:
        def __init__(self, process_instance) -> None:
            self.process_instance = process_instance

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeProcessInstanceQueueService:
        @staticmethod
        def dequeued(process_instance):
            return FakeDequeuedContext(process_instance)

    class FakeProcessInstanceMigrator:
        @staticmethod
        def run(process_instance) -> None:
            return None

    class FakeDbSession:
        def refresh(self, process_instance) -> None:
            return None

    class FakeProcessInstanceService:
        original_update_form_task_data_calls: list[dict[str, object]] = []

        @staticmethod
        def schedule_next_process_model_cycle(*args, **kwargs):
            return None

        @staticmethod
        def can_optimistically_skip(processor, status_value):
            return False

        @classmethod
        def update_form_task_data(cls, process_instance, spiff_task, data, user):
            cls.original_update_form_task_data_calls.append(
                {
                    "process_instance": process_instance,
                    "spiff_task": spiff_task,
                    "data": data,
                    "user": user,
                }
            )

    fake_service_module.ProcessInstanceService = FakeProcessInstanceService
    fake_processor_module.ProcessInstanceProcessor = FakeProcessInstanceProcessor
    fake_queue_module.ProcessInstanceQueueService = FakeProcessInstanceQueueService
    fake_migrator_module.ProcessInstanceMigrator = FakeProcessInstanceMigrator
    fake_db_module.db = SimpleNamespace(session=FakeDbSession())
    fake_workflow_execution_module.TaskRunnability = FakeTaskRunnability

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_service",
        fake_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_processor",
        fake_processor_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_queue_service",
        fake_queue_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.data_migrations.process_instance_migrator",
        fake_migrator_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.db",
        fake_db_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.workflow_execution_service",
        fake_workflow_execution_module,
    )
    monkeypatch.setattr(process_instance_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_service_patch,
        "current_app",
        SimpleNamespace(logger=SimpleNamespace(info=lambda *args, **kwargs: None)),
    )

    process_instance_service_patch.apply()

    process_instance = SimpleNamespace(id=2)
    workflow = SimpleNamespace(
        data={
            "data_objects": {
                "lane_owners": {"Manager": ["editor"]},
                "amount": 999,
            },
            "existing": "value",
        },
        data_objects={
            "lane_owners": {"Manager": ["editor"]},
            "amount": 999,
        },
    )
    spiff_task = SimpleNamespace(workflow=workflow, data={})
    user = SimpleNamespace(id=7)
    submitted_data = {"decision": "Rejected"}

    FakeProcessInstanceService.update_form_task_data(process_instance, spiff_task, submitted_data, user)

    assert FakeProcessInstanceService.original_update_form_task_data_calls == [
        {
            "process_instance": process_instance,
            "spiff_task": spiff_task,
            "data": submitted_data,
            "user": user,
        }
    ]
    assert workflow.data == {
        "data_objects": {
            "lane_owners": {"Manager": ["editor"]},
            "amount": 999,
            "decision": "Rejected",
        },
        "existing": "value",
        "decision": "Rejected",
    }
    assert workflow.data_objects == {
        "lane_owners": {"Manager": ["editor"]},
        "amount": 999,
        "decision": "Rejected",
    }
