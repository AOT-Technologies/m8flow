"""Service-task parameter values are Python expressions.

The properties panel writes URL fields as raw strings (``https://…``), which
are not valid Python. Spiff evaluates them before the connector runs, so an
unquoted URL fails the whole complete/submit. Treat unparseable expressions on
a Service Task as literals; sequence-flow conditions still fail loudly.
"""

from __future__ import annotations

import ast
import importlib
import threading
from typing import Any

# Process-wide "done once" flag; an Event avoids rebinding a module global.
_INSTALLED = threading.Event()


def runtime_script_engine_class() -> Any:
    """Core's private runtime script engine, wherever this core version keeps it.

    m8flow-core 1.0 moved it from ``workflow_runtime`` to ``workflow_engine``.
    ponytail: drop the 1.0.0b3 fallback once the pin moves past 1.0.0b3.
    """
    try:
        module = importlib.import_module("m8flow_core.services.workflow_engine")
    except ModuleNotFoundError:  # m8flow-core 1.0.0b3
        module = importlib.import_module("m8flow_core.services.workflow_runtime")
    return module._RuntimeServiceTaskScriptEngine


def is_service_task(task: object) -> bool:
    spec = getattr(task, "task_spec", None)
    return type(spec).__name__ == "ServiceTask"


def keep_unparseable_service_task_literal(task: object, expression: Any) -> bool:
    """True when ``expression`` should be used as-is instead of evaluated."""
    if not isinstance(expression, str) or not is_service_task(task):
        return False
    try:
        ast.parse(expression, mode="eval")
    except SyntaxError:
        return True
    return False


def install_service_task_literal_fallback() -> None:
    """Patch core's runtime script engine so unquoted Service Task params work.

    Idempotent: create_app() runs once per test process. Does not import
    ``spiffworkflow``.
    """
    if _INSTALLED.is_set():
        return

    engine = runtime_script_engine_class()
    original = engine.evaluate

    def evaluate(
        self: Any,
        task: object,
        expression: str,
        external_context: Any = None,
    ) -> object:
        if keep_unparseable_service_task_literal(task, expression):
            return expression
        return original(self, task, expression, external_context)

    engine.evaluate = evaluate
    _INSTALLED.set()
