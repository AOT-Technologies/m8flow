from __future__ import annotations

import sys
from types import SimpleNamespace
from types import ModuleType

from spiffworkflow_backend.models.json_data import JsonDataModel
from spiffworkflow_backend.services.jinja_service import JinjaService
import spiffworkflow_backend.services.process_instance_processor as process_instance_processor_module

from m8flow_backend.services import jinja_service_patch


def test_apply_merges_process_data_into_task_instruction_rendering(monkeypatch) -> None:
    data_by_hash = {
        "task-json-hash": {
            "overall_status": "task-level",
        },
        "task-python-hash": {},
        "process-hash": {
            "data_objects": {
                "ignored_data_object": "present",
            },
            "overall_status": "process-level",
            "test_results": {
                "get_v1": {
                    "status": "success",
                }
            },
        },
    }

    monkeypatch.setattr(JsonDataModel, "find_data_dict_by_hash", lambda data_hash: data_by_hash[data_hash])
    monkeypatch.setattr(
        JinjaService,
        "render_instructions_for_end_user",
        JinjaService.__dict__["render_instructions_for_end_user"],
        raising=False,
    )
    monkeypatch.setattr(jinja_service_patch, "_PATCHED", False)

    jinja_service_patch.apply()

    task_model = SimpleNamespace(
        get_data=lambda: {
            "overall_status": "task-level",
        },
        properties_json={},
        bpmn_process=SimpleNamespace(json_data_hash="process-hash"),
    )

    rendered = JinjaService.render_instructions_for_end_user(
        task_model,
        extensions={
            "instructionsForEndUser": "{{ overall_status }} | {{ test_results['get_v1']['status'] }}",
        },
    )

    assert rendered == "task-level | success"


def test_apply_uses_historical_process_instance_context_when_available(monkeypatch) -> None:
    data_by_hash = {
        "current-hash": {
            "overall_status": "current-process",
        },
    }

    class _FakeQuery:
        def filter_by(self, **kwargs):  # noqa: ANN003
            return self

        def first(self):  # noqa: D401
            return SimpleNamespace(id=1)

    fake_process_instance_module = ModuleType("spiffworkflow_backend.models.process_instance")

    class _FakeProcessInstanceModel:
        query = _FakeQuery()

    fake_process_instance_module.ProcessInstanceModel = _FakeProcessInstanceModel

    class _FakeProcessInstanceProcessor:
        def __init__(
            self,
            process_instance_model,  # noqa: ANN001
            include_task_data_for_completed_tasks: bool = False,
            include_completed_subprocesses: bool = False,
        ) -> None:
            self.bpmn_process_instance = SimpleNamespace(
                data={
                    "overall_status": "historical-process",
                },
                data_objects={},
            )

        @classmethod
        def get_tasks_with_data(cls, workflow):  # noqa: ANN001
            return [
                SimpleNamespace(
                    data={
                        "test_results": {
                            "get_v1": {
                                "status": "success",
                            }
                        }
                    },
                    last_state_change=1,
                )
            ]

    monkeypatch.setattr(JsonDataModel, "find_data_dict_by_hash", lambda data_hash: data_by_hash[data_hash])
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.process_instance", fake_process_instance_module)
    monkeypatch.setattr(
        process_instance_processor_module,
        "ProcessInstanceProcessor",
        _FakeProcessInstanceProcessor,
    )
    monkeypatch.setattr(
        JinjaService,
        "render_instructions_for_end_user",
        JinjaService.__dict__["render_instructions_for_end_user"],
        raising=False,
    )
    monkeypatch.setattr(jinja_service_patch, "_PATCHED", False)

    jinja_service_patch.apply()

    task_model = SimpleNamespace(
        get_data=lambda: {},
        properties_json={},
        bpmn_process=SimpleNamespace(json_data_hash="current-hash"),
        process_instance_id=1,
    )

    rendered = JinjaService.render_instructions_for_end_user(
        task_model,
        extensions={
            "instructionsForEndUser": "{{ overall_status }} | {{ test_results['get_v1']['status'] }}",
        },
    )

    assert rendered == "historical-process | success"
