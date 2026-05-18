from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace


def test_apply_preflights_queued_process_start_before_queueing(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch
    from m8flow_backend.services import process_instances_controller_patch

    fake_controller_module = ModuleType("spiffworkflow_backend.routes.process_instances_controller")
    fake_queue_module = ModuleType(
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer"
    )
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")
    fake_enum_module = ModuleType("spiffworkflow_backend.helpers.spiff_enum")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_error_handling_module = ModuleType("spiffworkflow_backend.services.error_handling_service")
    fake_queue_service_module = ModuleType("spiffworkflow_backend.services.process_instance_queue_service")
    fake_process_instance_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")
    fake_tmp_service_module = ModuleType("spiffworkflow_backend.services.process_instance_tmp_service")

    class FakeApiError(Exception):
        @classmethod
        def from_task(cls, error_code: str, message: str, status_code: int, task) -> "FakeApiError":  # noqa: ANN001
            return cls(message)

    class FakeProcessInstanceExecutionMode:
        synchronous = SimpleNamespace(value="synchronous")

    queue_calls: list[tuple[str, object | None]] = []
    handle_error_calls: list[tuple[object, Exception]] = []

    def fake_queue_process_instance_if_appropriate(process_instance, execution_mode: str | None = None) -> bool:
        queue_calls.append(("queue", execution_mode))
        return True

    fake_queue_module.queue_process_instance_if_appropriate = fake_queue_process_instance_if_appropriate
    fake_queue_module.should_queue_process_instance = lambda execution_mode=None: True
    fake_api_error_module.ApiError = FakeApiError
    fake_enum_module.ProcessInstanceExecutionMode = FakeProcessInstanceExecutionMode
    fake_db_module.db = SimpleNamespace(session=SimpleNamespace())
    fake_error_handling_module.ErrorHandlingService = SimpleNamespace(
        handle_error=lambda process_instance, error: handle_error_calls.append((process_instance, error))
    )
    fake_queue_service_module.ProcessInstanceIsAlreadyLockedError = type(
        "ProcessInstanceIsAlreadyLockedError", (Exception,), {}
    )
    fake_queue_service_module.ProcessInstanceIsNotEnqueuedError = type(
        "ProcessInstanceIsNotEnqueuedError", (Exception,), {}
    )
    fake_process_instance_service_module.ProcessInstanceService = SimpleNamespace(
        run_process_instance_with_processor=lambda *args, **kwargs: (None, "unknown_if_ready_tasks")
    )
    fake_tmp_service_module.ProcessInstanceTmpService = SimpleNamespace(
        add_event_to_process_instance=lambda *args, **kwargs: None,
        is_enqueued_to_run_in_the_future=lambda process_instance: False,
    )

    fake_controller_module._get_process_instance = lambda *args, **kwargs: None
    fake_controller_module._process_instance_run = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.process_instances_controller", fake_controller_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer",
        fake_queue_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.helpers.spiff_enum", fake_enum_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.error_handling_service", fake_error_handling_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_queue_service",
        fake_queue_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_service",
        fake_process_instance_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_tmp_service",
        fake_tmp_service_module,
    )

    preflight_calls: list[tuple[object, bool]] = []
    monkeypatch.setattr(
        process_instance_service_patch,
        "_validate_queued_process_start",
        lambda process_instance, handle_error=True: preflight_calls.append((process_instance, handle_error)),
    )
    monkeypatch.setattr(process_instances_controller_patch, "_PATCHED", False)

    process_instances_controller_patch.apply()

    process_instance = SimpleNamespace(id=8, status="not_started")
    fake_controller_module._process_instance_run(process_instance, execution_mode="asynchronous")

    assert preflight_calls == [(process_instance, False)]
    assert queue_calls == [("queue", "asynchronous")]
    assert handle_error_calls == []


def test_process_run_does_not_fault_instance_for_task_lane_assignment_api_error(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch
    from m8flow_backend.services import process_instances_controller_patch

    fake_controller_module = ModuleType("spiffworkflow_backend.routes.process_instances_controller")
    fake_queue_module = ModuleType(
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer"
    )
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")
    fake_enum_module = ModuleType("spiffworkflow_backend.helpers.spiff_enum")
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_error_handling_module = ModuleType("spiffworkflow_backend.services.error_handling_service")
    fake_queue_service_module = ModuleType("spiffworkflow_backend.services.process_instance_queue_service")
    fake_process_instance_service_module = ModuleType("spiffworkflow_backend.services.process_instance_service")
    fake_tmp_service_module = ModuleType("spiffworkflow_backend.services.process_instance_tmp_service")

    class FakeApiError(Exception):
        def __init__(self, error_code: str, message: str, status_code: int) -> None:
            super().__init__(message)
            self.error_code = error_code
            self.message = message
            self.status_code = status_code

        @classmethod
        def from_task(cls, error_code: str, message: str, status_code: int, task) -> "FakeApiError":  # noqa: ANN001
            return cls(error_code, message, status_code)

    class FakeProcessInstanceExecutionMode:
        synchronous = SimpleNamespace(value="synchronous")

    handle_error_calls: list[tuple[object, Exception]] = []

    fake_queue_module.queue_process_instance_if_appropriate = lambda process_instance, execution_mode=None: True
    fake_queue_module.should_queue_process_instance = lambda execution_mode=None: True
    fake_api_error_module.ApiError = FakeApiError
    fake_enum_module.ProcessInstanceExecutionMode = FakeProcessInstanceExecutionMode
    fake_db_module.db = SimpleNamespace(session=SimpleNamespace())
    fake_error_handling_module.ErrorHandlingService = SimpleNamespace(
        handle_error=lambda process_instance, error: handle_error_calls.append((process_instance, error))
    )
    fake_queue_service_module.ProcessInstanceIsAlreadyLockedError = type(
        "ProcessInstanceIsAlreadyLockedError", (Exception,), {}
    )
    fake_queue_service_module.ProcessInstanceIsNotEnqueuedError = type(
        "ProcessInstanceIsNotEnqueuedError", (Exception,), {}
    )
    fake_process_instance_service_module.ProcessInstanceService = SimpleNamespace(
        run_process_instance_with_processor=lambda *args, **kwargs: (None, "unknown_if_ready_tasks")
    )
    fake_tmp_service_module.ProcessInstanceTmpService = SimpleNamespace(
        add_event_to_process_instance=lambda *args, **kwargs: None,
        is_enqueued_to_run_in_the_future=lambda process_instance: False,
    )

    fake_controller_module._get_process_instance = lambda *args, **kwargs: None
    fake_controller_module._process_instance_run = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.process_instances_controller", fake_controller_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer",
        fake_queue_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.helpers.spiff_enum", fake_enum_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.error_handling_service", fake_error_handling_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_queue_service",
        fake_queue_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_service",
        fake_process_instance_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.process_instance_tmp_service",
        fake_tmp_service_module,
    )

    def fake_preflight(process_instance, handle_error=False):  # noqa: ANN001
        raise FakeApiError(
            "task_lane_assignment_error",
            "Process start could not continue. No users found in task data lane owner list for lane: Employee.",
            400,
        )

    monkeypatch.setattr(process_instances_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(
        process_instance_service_patch,
        "_validate_queued_process_start",
        fake_preflight,
    )

    process_instances_controller_patch.apply()

    process_instance = SimpleNamespace(id=8, status="not_started")

    try:
        fake_controller_module._process_instance_run(process_instance, execution_mode="asynchronous")
        raised_error = None
    except FakeApiError as exc:
        raised_error = exc

    assert raised_error is not None
    assert raised_error.error_code == "task_lane_assignment_error"
    assert handle_error_calls == []
