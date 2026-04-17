from __future__ import annotations

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
        tasks_controller_patch.apply()
        response = fake_tasks_controller_module._get_tasks()
        payload = response.get_json()

    assert payload["results"][0]["assigned_user_group_identifier"] == "tenant-slug:Manager"
    assert payload["results"][1]["assigned_user_group_identifier"] == "already-a-slug:Finance"
    assert payload["results"][2]["potential_owner_usernames"] == "alex"
