from __future__ import annotations

from dataclasses import dataclass, field
import sys
from types import ModuleType

from flask import Flask
from flask import jsonify

from m8flow_backend.routes import tasks_controller_patch


def test_apply_rewrites_assigned_group_identifier_for_task_list_responses(monkeypatch) -> None:
    fake_tasks_controller_module = ModuleType("spiffworkflow_backend.routes.tasks_controller")

    def fake_get_tasks(*args, **kwargs):
        return jsonify(
            {
                "results": [
                    {"id": 1, "assigned_user_group_identifier": "tenant-id:Manager"},
                    {"id": 2, "assigned_user_group_identifier": "already-a-slug:Finance"},
                    {"id": 3, "potential_owner_usernames": "alex"},
                ],
                "pagination": {"count": 3, "total": 3, "pages": 1},
            }
        )

    fake_tasks_controller_module._get_tasks = fake_get_tasks
    fake_tasks_controller_module.task_list_my_tasks = fake_get_tasks

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.tasks_controller",
        fake_tasks_controller_module,
    )
    monkeypatch.setattr(tasks_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(
        tasks_controller_patch,
        "display_group_identifier",
        lambda group_identifier: {
            "tenant-id:Manager": "tenant-slug:Manager",
            "already-a-slug:Finance": "already-a-slug:Finance",
        }.get(group_identifier, group_identifier),
    )

    app = Flask(__name__)
    with app.app_context():
        tasks_controller_patch.apply(app)
        response = fake_tasks_controller_module._get_tasks()
        payload = response.get_json()

    assert payload["results"][0]["assigned_user_group_identifier"] == "tenant-slug:Manager"
    assert payload["results"][1]["assigned_user_group_identifier"] == "already-a-slug:Finance"
    assert payload["results"][2]["potential_owner_usernames"] == "alex"


@dataclass
class _FakeTaskModel:
    task_data: dict
    properties_json: dict = field(default_factory=dict)
    data: dict | None = None

    def get_data(self) -> dict:
        return self.task_data


def test_apply_rewrites_task_data_show_to_return_combined_task_data(monkeypatch) -> None:
    fake_tasks_controller_module = ModuleType("spiffworkflow_backend.routes.tasks_controller")

    def fake_get_task_model_from_guid_or_raise(*args, **kwargs):
        return _FakeTaskModel(
            task_data={
                "json_only": "from-json",
                "python_env_only": "from-python-env",
            }
        )

    def fake_task_data_show(*args, **kwargs):
        return jsonify({})

    fake_task_data_show.__module__ = "spiffworkflow_backend.routes.tasks_controller"

    fake_tasks_controller_module._get_task_model_from_guid_or_raise = fake_get_task_model_from_guid_or_raise
    fake_tasks_controller_module._get_tasks = lambda *args, **kwargs: jsonify({"results": [], "pagination": {}})
    fake_tasks_controller_module.task_list_my_tasks = fake_tasks_controller_module._get_tasks
    fake_tasks_controller_module.task_data_show = fake_task_data_show

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.tasks_controller",
        fake_tasks_controller_module,
    )
    monkeypatch.setattr(tasks_controller_patch, "_PATCHED", False)

    app = Flask(__name__)
    app.add_url_rule(
        "/v1.0/task-data/<modified_process_model_identifier>/<int:process_instance_id>/<task_guid>",
        endpoint="wrapped_task_data_show",
        view_func=fake_tasks_controller_module.task_data_show,
        methods=["GET"],
    )
    with app.app_context():
        tasks_controller_patch.apply(app)
        response = app.view_functions["wrapped_task_data_show"](
            modified_process_model_identifier="model",
            process_instance_id=1,
            task_guid="task",
        )
        payload = response.get_json()

    assert payload["data"]["json_only"] == "from-json"
    assert payload["data"]["python_env_only"] == "from-python-env"


def test_apply_rewrites_task_data_show_to_use_delta_updates_when_task_hashes_are_empty(monkeypatch) -> None:
    fake_tasks_controller_module = ModuleType("spiffworkflow_backend.routes.tasks_controller")

    def fake_get_task_model_from_guid_or_raise(*args, **kwargs):
        return _FakeTaskModel(
            task_data={},
            properties_json={
                "delta": {
                    "updates": {
                        "decision": "Approved",
                    }
                }
            },
        )

    fake_tasks_controller_module._get_task_model_from_guid_or_raise = fake_get_task_model_from_guid_or_raise
    fake_tasks_controller_module._get_tasks = lambda *args, **kwargs: jsonify({"results": [], "pagination": {}})
    fake_tasks_controller_module.task_list_my_tasks = fake_tasks_controller_module._get_tasks
    fake_tasks_controller_module.task_data_show = lambda *args, **kwargs: jsonify({})

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.tasks_controller",
        fake_tasks_controller_module,
    )
    monkeypatch.setattr(tasks_controller_patch, "_PATCHED", False)

    app = Flask(__name__)
    app.add_url_rule(
        "/v1.0/task-data/<modified_process_model_identifier>/<int:process_instance_id>/<task_guid>",
        endpoint="wrapped_task_data_show_delta",
        view_func=fake_tasks_controller_module.task_data_show,
        methods=["GET"],
    )
    with app.app_context():
        tasks_controller_patch.apply(app)
        response = app.view_functions["wrapped_task_data_show_delta"](
            modified_process_model_identifier="model",
            process_instance_id=1,
            task_guid="task",
        )
        payload = response.get_json()

    assert payload["data"]["decision"] == "Approved"
