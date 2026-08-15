from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from spiffworkflow_backend.routes import authentication_controller

from m8flow_backend.services.cookie_path_patch import (
    COOKIE_PATH,
    _frontend_cookie_domain,
    _set_new_access_token_in_cookie_with_path,
    apply_cookie_path_patch,
)


def test_frontend_cookie_domain_omits_domain_for_localhost() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:8001"

    assert _frontend_cookie_domain(app) is None


def test_frontend_cookie_domain_keeps_named_host() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = (
        "https://app.example.com:8443"
    )

    assert _frontend_cookie_domain(app) == "app.example.com:8443"


def test_set_new_access_token_in_cookie_writes_tokens_with_root_path(
    monkeypatch,
) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(
        authentication_controller,
        "_clear_auth_tokens_from_thread_local_data",
        lambda: cleared.append(True),
    )

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
        new_id_token="id-token",
        new_authentication_identifier="master",
        user_has_logged_out=False,
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = _set_new_access_token_in_cookie_with_path(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any(
        "access_token=access-token" in header and "Path=/" in header
        for header in headers
    )
    assert any(
        "id_token=id-token" in header and "Path=/" in header for header in headers
    )
    assert any(
        "authentication_identifier=master" in header and "Path=/" in header
        for header in headers
    )
    assert any("Domain=app.example.com" in header for header in headers)
    assert COOKIE_PATH == "/"
    assert cleared == [True]


def test_set_new_access_token_in_cookie_expires_tokens_on_logout(monkeypatch) -> None:
    monkeypatch.setattr(
        authentication_controller,
        "_clear_auth_tokens_from_thread_local_data",
        lambda: None,
    )

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:8001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token=None,
        new_id_token=None,
        new_authentication_identifier=None,
        user_has_logged_out=True,
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = _set_new_access_token_in_cookie_with_path(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any(
        header.startswith("access_token=") and "Path=/" in header for header in headers
    )
    assert any(
        header.startswith("id_token=") and "Path=/" in header for header in headers
    )
    assert any(
        header.startswith("authentication_identifier=") and "Path=/" in header
        for header in headers
    )
    assert all("Max-Age=0" in header for header in headers)
    assert all("Domain=" not in header for header in headers)


def test_apply_cookie_path_patch_rebinds_set_cookie_helper() -> None:
    original = authentication_controller._set_new_access_token_in_cookie
    try:
        apply_cookie_path_patch()
        assert (
            authentication_controller._set_new_access_token_in_cookie
            is _set_new_access_token_in_cookie_with_path
        )
    finally:
        authentication_controller._set_new_access_token_in_cookie = original
