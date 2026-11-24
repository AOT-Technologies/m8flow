from __future__ import annotations

import sys

import pytest

from m8flow_backend.workflow.service_task_params import (
    keep_unparseable_service_task_literal,
    runtime_script_engine_class,
)


def _task_with_spec_named(name: str) -> object:
    spec = type(name, (), {})()
    return type("T", (), {"task_spec": spec})()


def test_unquoted_url_on_service_task_is_kept_as_literal():
    task = _task_with_spec_named("ServiceTask")
    assert keep_unparseable_service_task_literal(task, "https://example.test/hook") is True


def test_quoted_url_and_python_names_are_not_treated_as_literals():
    task = _task_with_spec_named("ServiceTask")
    assert keep_unparseable_service_task_literal(task, '"https://example.test/hook"') is False
    assert keep_unparseable_service_task_literal(task, "decision") is False
    assert keep_unparseable_service_task_literal(task, '{"ok": true}') is False


def test_unparseable_expression_on_a_gateway_is_not_swallowed():
    task = _task_with_spec_named("ExclusiveGateway")
    assert keep_unparseable_service_task_literal(task, "x === 1") is False


@pytest.mark.parametrize("engine", [None, type("NoEvaluate", (), {})], ids=["no-class", "no-evaluate"])
def test_missing_core_script_engine_names_what_core_lost(monkeypatch, engine):
    module = sys.modules[runtime_script_engine_class().__module__]
    if engine is None:
        monkeypatch.delattr(module, "_RuntimeServiceTaskScriptEngine")
    else:
        monkeypatch.setattr(module, "_RuntimeServiceTaskScriptEngine", engine)

    with pytest.raises(RuntimeError, match=rf"m8flow-core .* has no {module.__name__}\._RuntimeServiceTaskScriptEngine\.evaluate"):
        runtime_script_engine_class()
