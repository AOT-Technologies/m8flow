"""Service-task parameter values are Python expressions.

The properties panel writes URL fields as raw strings (``https://…``), which
are not valid Python. Spiff evaluates them before the connector runs, so an
unquoted URL fails the whole complete/submit. Treat unparseable expressions on
a Service Task as literals; sequence-flow conditions still fail loudly.
"""

from __future__ import annotations

import ast
from typing import Any

_INSTALLED = False


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
    global _INSTALLED
    if _INSTALLED:
        return

    from m8flow_bpmn_core.services.workflow_runtime import _RuntimeServiceTaskScriptEngine

    original = _RuntimeServiceTaskScriptEngine.evaluate

    def evaluate(
        self: Any,
        task: object,
        expression: str,
        external_context: Any = None,
    ) -> object:
        if keep_unparseable_service_task_literal(task, expression):
            return expression
        return original(self, task, expression, external_context)

    _RuntimeServiceTaskScriptEngine.evaluate = evaluate  # type: ignore[method-assign]
    _INSTALLED = True
