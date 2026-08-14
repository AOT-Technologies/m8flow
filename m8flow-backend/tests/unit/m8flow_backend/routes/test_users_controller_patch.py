from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace

import pytest
from flask import Flask, g
from spiffworkflow_backend.exceptions.api_error import ApiError


def _install_users_controller_fakes(monkeypatch, *, tenant_id: str | None = "tenant-a"):
    """Fake upstream users_controller so apply() rebinds tenant-aware endpoints."""
    fake_users_controller = ModuleType("spiffworkflow_backend.routes.users_controller")
    fake_users_controller.user_exists_by_username = lambda body: body
    fake_users_controller.user_search = lambda prefix: prefix
    fake_users_controller.user_group_list_for_current_user = lambda: None

    fake_routes = ModuleType("spiffworkflow_backend.routes")
    fake_routes.users_controller = fake_users_controller

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_routes)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.users_controller",
        fake_users_controller,
    )
    users_controller_patch = import_module(
        "m8flow_backend.routes.users_controller_patch"
    )
    monkeypatch.setattr(users_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(
        users_controller_patch,
        "qualified_config_group_identifier",
        lambda config_key: "tenant-a:everybody",
    )
    monkeypatch.setattr(
        users_controller_patch, "current_tenant_id_or_none", lambda: tenant_id
    )
    monkeypatch.setattr(
        users_controller_patch,
        "is_group_for_tenant",
        lambda group_identifier, tenant_id: group_identifier.startswith(
            f"{tenant_id}:"
        ),
    )
    return fake_users_controller, users_controller_patch


def test_user_group_list_filters_to_current_tenant_hides_default_group_and_keeps_global_super_admin(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

    fake_users_controller, users_controller_patch = _install_users_controller_fakes(
        monkeypatch
    )
    users_controller_patch.apply()

    with app.app_context():
        with app.test_request_context():
            g.user = SimpleNamespace(
                groups=[
                    SimpleNamespace(identifier="tenant-a:reviewer"),
                    SimpleNamespace(identifier="tenant-a:everybody"),
                    SimpleNamespace(identifier="tenant-a:admin"),
                    SimpleNamespace(identifier="tenant-b:viewer"),
                    SimpleNamespace(identifier="super-admin"),
                ]
            )
            response = fake_users_controller.user_group_list_for_current_user()

    assert response.status_code == 200
    assert response.get_json() == ["super-admin", "tenant-a:admin", "tenant-a:reviewer"]


def test_user_group_list_when_tenant_id_is_none_hides_only_the_default_group(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    fake_users_controller, users_controller_patch = _install_users_controller_fakes(
        monkeypatch, tenant_id=None
    )
    users_controller_patch.apply()

    with app.app_context():
        with app.test_request_context():
            g.user = SimpleNamespace(
                groups=[
                    SimpleNamespace(identifier="tenant-a:reviewer"),
                    SimpleNamespace(identifier="tenant-a:everybody"),
                    SimpleNamespace(identifier="tenant-b:viewer"),
                    SimpleNamespace(identifier="super-admin"),
                ]
            )
            response = fake_users_controller.user_group_list_for_current_user()

    assert response.status_code == 200
    assert response.get_json() == [
        "super-admin",
        "tenant-a:reviewer",
        "tenant-b:viewer",
    ]


def test_user_exists_by_username_reports_tenant_scoped_match(monkeypatch) -> None:
    app = Flask(__name__)
    fake_users_controller, users_controller_patch = _install_users_controller_fakes(
        monkeypatch
    )
    monkeypatch.setattr(
        users_controller_patch,
        "find_users_for_current_tenant_by_username",
        lambda username: (
            [SimpleNamespace(username=username)] if username == "alice" else []
        ),
    )
    users_controller_patch.apply()

    with app.app_context():
        with app.test_request_context():
            found = fake_users_controller.user_exists_by_username({"username": "alice"})
            missing = fake_users_controller.user_exists_by_username(
                {"username": "nobody"}
            )

    assert found.status_code == 200
    assert found.get_json() == {"user_found": True}
    assert missing.status_code == 200
    assert missing.get_json() == {"user_found": False}


def test_user_exists_by_username_requires_username(monkeypatch) -> None:
    fake_users_controller, users_controller_patch = _install_users_controller_fakes(
        monkeypatch
    )
    users_controller_patch.apply()

    with pytest.raises(ApiError) as exc_info:
        fake_users_controller.user_exists_by_username({})

    assert exc_info.value.error_code == "username_not_given"
    assert exc_info.value.status_code == 400


def test_user_search_returns_tenant_scoped_prefix_matches(monkeypatch) -> None:
    app = Flask(__name__)
    matches = [{"username": "alice"}, {"username": "alex"}]
    fake_users_controller, users_controller_patch = _install_users_controller_fakes(
        monkeypatch
    )
    monkeypatch.setattr(
        users_controller_patch,
        "find_users_for_current_tenant_by_username_prefix",
        lambda prefix: matches if prefix == "al" else [],
    )
    users_controller_patch.apply()

    with app.app_context():
        with app.test_request_context():
            response = fake_users_controller.user_search("al")

    assert response.status_code == 200
    assert response.get_json() == {"users": matches, "username_prefix": "al"}
