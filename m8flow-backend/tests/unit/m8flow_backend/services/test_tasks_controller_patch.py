from __future__ import annotations

from dataclasses import dataclass, field
import sys
from types import ModuleType

from flask import Flask
from flask import jsonify

from m8flow_backend.routes import tasks_controller_patch


def test_extract_process_instance_id_handles_kwargs_args_and_invalid_values() -> None:
    assert tasks_controller_patch._extract_process_instance_id((), {"process_instance_id": 7}) == 7
    assert tasks_controller_patch._extract_process_instance_id((), {"process_instance_id": "9"}) == 9
    assert tasks_controller_patch._extract_process_instance_id((11,), {}) == 11
    assert tasks_controller_patch._extract_process_instance_id((), {}) is None
    assert tasks_controller_patch._extract_process_instance_id((), {"process_instance_id": None}) is None
    assert tasks_controller_patch._extract_process_instance_id((), {"process_instance_id": "abc"}) is None


def _build_patched_tasks_controller(monkeypatch):
    """Apply the patch against a fake tasks_controller module and return it plus a call tracker."""
    fake_tasks_controller_module = ModuleType("spiffworkflow_backend.routes.tasks_controller")
    calls: list[str] = []

    def fake_task_list_my_tasks(*args, **kwargs):
        calls.append("original")
        return jsonify({"results": [{"id": "original"}], "pagination": {"count": 1, "total": 1, "pages": 1}})

    fake_tasks_controller_module._get_tasks = fake_task_list_my_tasks
    fake_tasks_controller_module.task_list_my_tasks = fake_task_list_my_tasks

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.tasks_controller",
        fake_tasks_controller_module,
    )
    monkeypatch.setattr(tasks_controller_patch, "_MODULE_PATCHED", False)
    monkeypatch.setattr(tasks_controller_patch, "_ORIGINAL_TASK_DATA_SHOW", None)
    monkeypatch.setattr(
        tasks_controller_patch,
        "display_group_identifier",
        lambda group_identifier: group_identifier,
    )

    tasks_controller_patch._apply_module_patches()
    return fake_tasks_controller_module, calls


def test_super_admin_per_instance_call_defers_to_original_handler(monkeypatch) -> None:
    # When a process_instance_id is present (the ProcessInstanceShow "Tasks I can complete" call),
    # super admins must defer to the original handler rather than the global all-open-tasks view.
    # The fake tasks_controller module lacks the DB/model attributes the global view needs, so if the
    # global branch were taken it would raise instead of returning the original sentinel payload.
    fake_tasks_controller_module, calls = _build_patched_tasks_controller(monkeypatch)

    monkeypatch.setattr(tasks_controller_patch, "is_super_admin_request", lambda: True)

    app = Flask(__name__)
    with app.app_context():
        response = fake_tasks_controller_module.task_list_my_tasks(process_instance_id=5)
        payload = response.get_json()

    assert calls == ["original"]
    assert payload["results"][0]["id"] == "original"


def test_non_super_admin_uses_original_handler(monkeypatch) -> None:
    fake_tasks_controller_module, calls = _build_patched_tasks_controller(monkeypatch)

    monkeypatch.setattr(tasks_controller_patch, "is_super_admin_request", lambda: False)

    app = Flask(__name__)
    with app.app_context():
        response = fake_tasks_controller_module.task_list_my_tasks()
        payload = response.get_json()

    assert calls == ["original"]
    assert payload["results"][0]["id"] == "original"


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
    monkeypatch.setattr(tasks_controller_patch, "_MODULE_PATCHED", False)
    monkeypatch.setattr(tasks_controller_patch, "_ORIGINAL_TASK_DATA_SHOW", None)
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
    monkeypatch.setattr(tasks_controller_patch, "_MODULE_PATCHED", False)
    monkeypatch.setattr(tasks_controller_patch, "_ORIGINAL_TASK_DATA_SHOW", None)

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
    monkeypatch.setattr(tasks_controller_patch, "_MODULE_PATCHED", False)
    monkeypatch.setattr(tasks_controller_patch, "_ORIGINAL_TASK_DATA_SHOW", None)

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


def test_apply_rewrites_task_data_show_for_task_data_route_when_handler_identity_is_wrapped(monkeypatch) -> None:
    fake_tasks_controller_module = ModuleType("spiffworkflow_backend.routes.tasks_controller")

    def fake_get_task_model_from_guid_or_raise(*args, **kwargs):
        return _FakeTaskModel(
            task_data={},
            properties_json={
                "delta": {
                    "updates": {
                        "lane_owners": {"Manager": ["admin"]},
                    }
                }
            },
        )

    def wrapped_connexion_handler(*args, **kwargs):
        return jsonify({})

    fake_tasks_controller_module._get_task_model_from_guid_or_raise = fake_get_task_model_from_guid_or_raise
    fake_tasks_controller_module._get_tasks = lambda *args, **kwargs: jsonify({"results": [], "pagination": {}})
    fake_tasks_controller_module.task_list_my_tasks = fake_tasks_controller_module._get_tasks
    fake_tasks_controller_module.task_data_show = lambda *args, **kwargs: jsonify({})

    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.tasks_controller",
        fake_tasks_controller_module,
    )
    monkeypatch.setattr(tasks_controller_patch, "_MODULE_PATCHED", False)
    monkeypatch.setattr(tasks_controller_patch, "_ORIGINAL_TASK_DATA_SHOW", None)

    app = Flask(__name__)
    app.add_url_rule(
        "/v1.0/task-data/<modified_process_model_identifier>/<int:process_instance_id>/<task_guid>",
        endpoint="connexion_wrapped_task_data_endpoint",
        view_func=wrapped_connexion_handler,
        methods=["GET"],
    )
    with app.app_context():
        tasks_controller_patch.apply(app)
        response = app.view_functions["connexion_wrapped_task_data_endpoint"](
            modified_process_model_identifier="model",
            process_instance_id=1,
            task_guid="task",
        )
        payload = response.get_json()

    assert payload["data"]["lane_owners"] == {"Manager": ["admin"]}
