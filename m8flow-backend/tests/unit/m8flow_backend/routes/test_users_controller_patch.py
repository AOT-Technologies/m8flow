from __future__ import annotations

from types import SimpleNamespace

from flask import Flask, g

from spiffworkflow_backend.routes import users_controller

import m8flow_backend.routes.users_controller_patch as users_controller_patch


def test_user_group_list_filters_qualified_default_group(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

    original_exists = users_controller.user_exists_by_username
    original_search = users_controller.user_search
    original_group_list = users_controller.user_group_list_for_current_user

    monkeypatch.setattr(users_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(
        users_controller_patch,
        "qualified_config_group_identifier",
        lambda config_key: "tenant-a:everybody",
    )

    try:
        users_controller_patch.apply()
        with app.app_context():
            with app.test_request_context():
                g.user = SimpleNamespace(
                    groups=[
                        SimpleNamespace(identifier="tenant-a:reviewer"),
                        SimpleNamespace(identifier="tenant-a:everybody"),
                        SimpleNamespace(identifier="tenant-a:admin"),
                    ]
                )
                response = users_controller.user_group_list_for_current_user()
    finally:
        users_controller.user_exists_by_username = original_exists
        users_controller.user_search = original_search
        users_controller.user_group_list_for_current_user = original_group_list
        monkeypatch.setattr(users_controller_patch, "_PATCHED", False)

    assert response.status_code == 200
    assert response.get_json() == ["tenant-a:admin", "tenant-a:reviewer"]
