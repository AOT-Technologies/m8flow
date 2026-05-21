from __future__ import annotations

from collections.abc import Callable
from typing import Any

from SpiffWorkflow.bpmn.specs.mixins.events.event_types import CatchingEvent
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.util.task import TaskState

_PATCHED = False


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    def patched_refresh_waiting_tasks(
        self: BpmnWorkflow,
        will_refresh_task: Callable[[Any], None] | None = None,
        did_refresh_task: Callable[[Any], None] | None = None,
    ) -> None:
        """Restore waiting-event refresh behavior removed in newer SpiffWorkflow versions.

        spiffworkflow-backend still expects this workflow hook to revisit WAITING catching
        events so due timers can transition to READY. Newer SpiffWorkflow releases made the
        method a no-op, which leaves timer catch events stuck in WAITING forever.
        """

        waiting_tasks = self.get_tasks(state=TaskState.WAITING, spec_class=CatchingEvent)
        for task in waiting_tasks:
            if will_refresh_task is not None:
                will_refresh_task(task)
            task.task_spec._update(task)
            if did_refresh_task is not None:
                did_refresh_task(task)

    BpmnWorkflow.refresh_waiting_tasks = patched_refresh_waiting_tasks
    _PATCHED = True
