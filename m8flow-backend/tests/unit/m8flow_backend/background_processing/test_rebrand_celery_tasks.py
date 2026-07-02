"""Regression tests for Celery task rebranding.

The m8flow wrappers (celery_task_process_instance_run / celery_task_event_notifier_run)
delegate to the upstream task via a lazy ``@shared_task`` Proxy that resolves the upstream
task *by its old name* at call time. ``rebrand_celery_tasks`` must therefore keep the upstream
registration alive for any task that has an m8flow wrapper, otherwise the proxy raises
``NotRegistered`` on every run and process instances never advance (infinite spinner).
"""

from __future__ import annotations

from m8flow_backend.background_processing import (
    M8FLOW_CELERY_TASK_EVENT_NOTIFIER,
    M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN,
    rebrand_celery_tasks,
)

# Synthetic upstream prefix so the post-rebrand importlib calls fail fast (module is absent)
# and the test stays hermetic — no real spiffworkflow_backend modules are mutated.
_OLD_PREFIX = "fakeupstream"
_MARKER = ".background_processing.celery_tasks."


class FakeTask:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeConf:
    def __init__(self) -> None:
        self.changes: dict[str, object] = {}


class FakeCeleryApp:
    def __init__(self, tasks: dict[str, object]) -> None:
        self.tasks = tasks
        self.conf = FakeConf()
        self.main = _OLD_PREFIX


class FakeFlaskApp:
    def __init__(self, celery_app: object) -> None:
        self.celery_app = celery_app
        self.name = "m8flow_backend"


def _old(suffix: str) -> str:
    return f"{_OLD_PREFIX}{_MARKER}{suffix}"


def test_rebrand_keeps_upstream_name_for_wrapped_tasks() -> None:
    upstream_run = _old("process_instance_task.celery_task_process_instance_run")
    upstream_notifier = _old("process_instance_task.celery_task_event_notifier_run")
    # An upstream task with no m8flow wrapper — this one SHOULD be rebranded/renamed.
    upstream_unwrapped = _old("some_other_task.celery_task_other")

    tasks: dict[str, object] = {
        upstream_run: FakeTask(upstream_run),
        upstream_notifier: FakeTask(upstream_notifier),
        upstream_unwrapped: FakeTask(upstream_unwrapped),
        # m8flow wrappers already registered under the new (m8flow) names.
        M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN: FakeTask(M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN),
        M8FLOW_CELERY_TASK_EVENT_NOTIFIER: FakeTask(M8FLOW_CELERY_TASK_EVENT_NOTIFIER),
    }

    rebrand_celery_tasks(FakeFlaskApp(FakeCeleryApp(tasks)))

    # The crux of the regression: wrapped upstream tasks keep their old-name registration
    # so the wrapper's lazy Proxy can resolve them and delegate at call time.
    assert upstream_run in tasks
    assert upstream_notifier in tasks

    # The m8flow wrapper names remain registered too.
    assert M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN in tasks
    assert M8FLOW_CELERY_TASK_EVENT_NOTIFIER in tasks

    # Upstream tasks without an m8flow wrapper are still rebranded to the m8flow prefix.
    rebranded_unwrapped = upstream_unwrapped.replace(_OLD_PREFIX, "m8flow_backend", 1)
    assert rebranded_unwrapped in tasks
    assert upstream_unwrapped not in tasks
