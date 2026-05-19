from __future__ import annotations

import sys
from flask import Flask
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
        def create_process_instance(*_args, **_kwargs):
            return (SimpleNamespace(id=0, m8f_tenant_id=None), None)

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
        def create_process_instance(*_args, **_kwargs):
            return (SimpleNamespace(id=0, m8f_tenant_id=None), None)

        @staticmethod
        def schedule_next_process_model_cycle(*_args, **_kwargs):
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
    }
    assert workflow.data_objects == {
        "lane_owners": {"Manager": ["editor"]},
        "amount": 999,
        "decision": "Rejected",
    }


def test_validate_queued_follow_up_work_turns_explicit_lane_owner_failure_into_api_error(monkeypatch) -> None:
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_error_handling_module = ModuleType("spiffworkflow_backend.services.error_handling_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")

    class FakeApiError(Exception):
        def __init__(self, error_code: str, message: str, status_code: int) -> None:
            super().__init__(message)
            self.error_code = error_code
            self.message = message
            self.status_code = status_code

    class FakeNoPotentialOwnersForTaskError(Exception):
        pass

    rollback_calls: list[None] = []
    handle_error_calls: list[tuple[object, Exception]] = []

    class FakeDbSession:
        def rollback(self) -> None:
            rollback_calls.append(None)

    class FakeErrorHandlingService:
        @staticmethod
        def handle_error(process_instance, error: Exception) -> None:
            handle_error_calls.append((process_instance, error))

    fake_api_error_module.ApiError = FakeApiError
    fake_db_module.db = SimpleNamespace(session=FakeDbSession())
    fake_error_handling_module.ErrorHandlingService = FakeErrorHandlingService
    fake_processor_module.NoPotentialOwnersForTaskError = FakeNoPotentialOwnersForTaskError

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.error_handling_service", fake_error_handling_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.process_instance_processor", fake_processor_module)

    process_instance = SimpleNamespace(id=44)
    do_engine_steps_calls: list[dict[str, object]] = []

    def fake_do_engine_steps(*, save: bool, execution_strategy_name: str, should_schedule_waiting_timer_events: bool) -> None:
        do_engine_steps_calls.append(
            {
                "save": save,
                "execution_strategy_name": execution_strategy_name,
                "should_schedule_waiting_timer_events": should_schedule_waiting_timer_events,
            }
        )
        raise FakeNoPotentialOwnersForTaskError(
            "No users found in task data lane owner list for lane: Employee. The user list used: ['submitter']"
        )

    processor = SimpleNamespace(
        process_instance_model=process_instance,
        do_engine_steps=fake_do_engine_steps,
    )

    try:
        process_instance_service_patch._validate_queued_follow_up_work(processor)
        raised_error = None
    except FakeApiError as exc:
        raised_error = exc

    assert do_engine_steps_calls == [
        {
            "save": True,
            "execution_strategy_name": "run_until_user_message",
            "should_schedule_waiting_timer_events": False,
        }
    ]
    assert rollback_calls == [None]
    assert handle_error_calls == []
    assert raised_error is not None
    assert raised_error.error_code == "task_lane_assignment_error"
    assert raised_error.status_code == 400
    assert raised_error.message == (
        "Task submission could not continue. No users found in task data lane owner list for lane: Employee. "
        "The user list used: ['submitter']"
    )


def test_validate_queued_process_start_turns_missing_lane_assignment_into_api_error(monkeypatch) -> None:
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_error_handling_module = ModuleType("spiffworkflow_backend.services.error_handling_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")
    fake_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")

    class FakeApiError(Exception):
        def __init__(self, error_code: str, message: str, status_code: int) -> None:
            super().__init__(message)
            self.error_code = error_code
            self.message = message
            self.status_code = status_code

    class FakeNoPotentialOwnersForTaskError(Exception):
        pass

    rollback_calls: list[None] = []
    handle_error_calls: list[tuple[object, Exception]] = []
    run_calls: list[dict[str, object]] = []

    class FakeDbSession:
        def rollback(self) -> None:
            rollback_calls.append(None)

    class FakeErrorHandlingService:
        @staticmethod
        def handle_error(process_instance, error: Exception) -> None:
            handle_error_calls.append((process_instance, error))

    class FakeProcessInstanceService:
        @staticmethod
        def run_process_instance_with_processor(
            process_instance,
            status_value: str | None = None,
            execution_strategy_name: str | None = None,
            should_schedule_waiting_timer_events: bool = True,
        ) -> tuple[None, str]:
            run_calls.append(
                {
                    "process_instance": process_instance,
                    "status_value": status_value,
                    "execution_strategy_name": execution_strategy_name,
                    "should_schedule_waiting_timer_events": should_schedule_waiting_timer_events,
                }
            )
            raise FakeNoPotentialOwnersForTaskError(
                "No users found in task data lane owner list for lane: Employee. The user list used: ['submitter']"
            )

    fake_api_error_module.ApiError = FakeApiError
    fake_db_module.db = SimpleNamespace(session=FakeDbSession())
    fake_error_handling_module.ErrorHandlingService = FakeErrorHandlingService
    fake_processor_module.NoPotentialOwnersForTaskError = FakeNoPotentialOwnersForTaskError
    fake_service_module.ProcessInstanceService = FakeProcessInstanceService

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.error_handling_service", fake_error_handling_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.process_instance_processor", fake_processor_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.process_instance_service", fake_service_module)

    process_instance = SimpleNamespace(id=55)

    try:
        process_instance_service_patch._validate_queued_process_start(process_instance)
        raised_error = None
    except FakeApiError as exc:
        raised_error = exc

    assert run_calls == [
        {
            "process_instance": process_instance,
            "status_value": None,
            "execution_strategy_name": "run_until_user_message",
            "should_schedule_waiting_timer_events": False,
        }
    ]
    assert rollback_calls == [None]
    assert handle_error_calls == []
    assert raised_error is not None
    assert raised_error.error_code == "task_lane_assignment_error"
    assert raised_error.status_code == 400
    assert raised_error.message == (
        "Process start could not continue. No users found in task data lane owner list for lane: Employee. "
        "The user list used: ['submitter']"
    )


def test_apply_preflights_queued_form_submissions_before_returning(monkeypatch) -> None:
    fake_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")
    fake_processor_module = ModuleType("spiffworkflow_backend.services.process_instance_processor")
    fake_queue_module = ModuleType("spiffworkflow_backend.services.process_instance_queue_service")
    fake_migrator_module = ModuleType("spiffworkflow_backend.data_migrations.process_instance_migrator")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_workflow_execution_module = ModuleType("spiffworkflow_backend.services.workflow_execution_service")
    fake_queue_producer_module = ModuleType(
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer"
    )
    fake_jinja_module = ModuleType("spiffworkflow_backend.services.jinja_service")
    fake_spiff_task_state_module = ModuleType("SpiffWorkflow.util.task")
    fake_spiff_enum_module = ModuleType("spiffworkflow_backend.helpers.spiff_enum")

    class FakeTaskRunnability:
        unknown_if_ready_tasks = "unknown_if_ready_tasks"

    class FakeTaskState:
        WAITING = 1
        READY = 2

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

    class FakeJinjaService:
        add_instruction_calls: list[dict[str, object]] = []

        @staticmethod
        def add_instruction_for_end_user_if_appropriate(tasks, process_instance_id: int, tasks_that_have_been_seen) -> None:
            FakeJinjaService.add_instruction_calls.append(
                {
                    "tasks": tasks,
                    "process_instance_id": process_instance_id,
                    "tasks_that_have_been_seen": tasks_that_have_been_seen,
                }
            )

    class FakeProcessInstanceExecutionMode:
        synchronous = SimpleNamespace(value="synchronous")

    class FakeProcessInstanceService:
        original_update_form_task_data_calls: list[dict[str, object]] = []

        @staticmethod
        def create_process_instance(*_args, **_kwargs):
            return (SimpleNamespace(id=0, m8f_tenant_id=None), None)

        @staticmethod
        def schedule_next_process_model_cycle(*_args, **_kwargs):
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
    fake_queue_producer_module.should_queue_process_instance = lambda execution_mode: True
    fake_jinja_module.JinjaService = FakeJinjaService
    fake_spiff_task_state_module.TaskState = FakeTaskState
    fake_spiff_enum_module.ProcessInstanceExecutionMode = FakeProcessInstanceExecutionMode

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
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer",
        fake_queue_producer_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.jinja_service",
        fake_jinja_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "SpiffWorkflow.util.task",
        fake_spiff_task_state_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.helpers.spiff_enum",
        fake_spiff_enum_module,
    )

    validate_calls: list[object] = []
    monkeypatch.setattr(
        process_instance_service_patch,
        "_validate_queued_follow_up_work",
        lambda processor, handle_error=False: validate_calls.append(processor),
    )
    monkeypatch.setattr(process_instance_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_service_patch,
        "current_app",
        SimpleNamespace(logger=SimpleNamespace(info=lambda *args, **kwargs: None)),
    )

    process_instance_service_patch.apply()

    refresh_calls: list[None] = []
    get_tasks_calls: list[int] = []
    complete_task_calls: list[dict[str, object]] = []

    processor = SimpleNamespace(
        process_instance_model=SimpleNamespace(id=17),
        complete_task=lambda spiff_task, human_task, user: complete_task_calls.append(
            {
                "spiff_task": spiff_task,
                "human_task": human_task,
                "user": user,
            }
        ),
        bpmn_process_instance=SimpleNamespace(
            refresh_waiting_tasks=lambda: refresh_calls.append(None),
            get_tasks=lambda state: get_tasks_calls.append(state) or ["ready-task"],
        ),
    )
    spiff_task = SimpleNamespace(id="task-1")
    human_task = SimpleNamespace(id=6)
    user = SimpleNamespace(id=9)
    data = {"decision": "Approved"}

    app = Flask(__name__)
    with app.app_context():
        FakeProcessInstanceService.complete_form_task(processor, spiff_task, data, user, human_task, execution_mode="queued")

    assert FakeProcessInstanceService.original_update_form_task_data_calls == [
        {
            "process_instance": processor.process_instance_model,
            "spiff_task": spiff_task,
            "data": data,
            "user": user,
        }
    ]
    assert complete_task_calls == [{"spiff_task": spiff_task, "human_task": human_task, "user": user}]
    assert validate_calls == [processor]
    assert refresh_calls == [None]
    assert get_tasks_calls == [FakeTaskState.WAITING | FakeTaskState.READY]
    assert FakeJinjaService.add_instruction_calls == [
        {
            "tasks": ["ready-task"],
            "process_instance_id": 17,
            "tasks_that_have_been_seen": set(),
        }
    ]
