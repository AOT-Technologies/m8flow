from __future__ import annotations

from SpiffWorkflow.bpmn.specs.mixins.events.event_types import CatchingEvent
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.util.task import TaskState

from m8flow_backend.services import spiff_timer_refresh_patch


class FakeTaskSpec:
    def __init__(self) -> None:
        self.updated_tasks: list[FakeTask] = []

    def _update(self, task: "FakeTask") -> None:
        self.updated_tasks.append(task)


class FakeTask:
    def __init__(self, label: str) -> None:
        self.label = label
        self.task_spec = FakeTaskSpec()


class FakeWorkflow:
    def __init__(self, tasks: list[FakeTask]) -> None:
        self.tasks = tasks
        self.get_tasks_calls: list[tuple[TaskState, type]] = []

    def get_tasks(self, *, state: TaskState, spec_class: type) -> list[FakeTask]:
        self.get_tasks_calls.append((state, spec_class))
        return list(self.tasks)


def test_refresh_waiting_tasks_updates_waiting_catching_events() -> None:
    spiff_timer_refresh_patch.apply()

    task_one = FakeTask("one")
    task_two = FakeTask("two")
    workflow = FakeWorkflow([task_one, task_two])
    refreshed: list[str] = []
    completed: list[str] = []

    BpmnWorkflow.refresh_waiting_tasks(
        workflow,
        will_refresh_task=lambda task: refreshed.append(task.label),
        did_refresh_task=lambda task: completed.append(task.label),
    )

    assert workflow.get_tasks_calls == [(TaskState.WAITING, CatchingEvent)]
    assert refreshed == ["one", "two"]
    assert completed == ["one", "two"]
    assert task_one.task_spec.updated_tasks == [task_one]
    assert task_two.task_spec.updated_tasks == [task_two]
