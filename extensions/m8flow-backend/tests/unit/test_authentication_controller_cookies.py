from types import SimpleNamespace

from flask import Flask

from spiffworkflow_backend.routes.authentication_controller import (
    _frontend_cookie_domain,
    _set_new_access_token_in_cookie,
)


def test_frontend_cookie_domain_omits_domain_for_ip_frontend_url() -> None:
    assert _frontend_cookie_domain("http://192.168.1.105:8001") is None


def test_frontend_cookie_domain_strips_port_for_named_host() -> None:
    assert _frontend_cookie_domain("https://app.example.com:8443") == "app.example.com"


def test_set_new_access_token_in_cookie_uses_host_only_cookies_for_ip_frontend_url() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://192.168.1.105:8001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
        new_id_token="id-token",
        new_authentication_identifier="master",
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = _set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("access_token=access-token" in header for header in headers)
    assert any("id_token=id-token" in header for header in headers)
    assert any("authentication_identifier=master" in header for header in headers)
    assert all("Domain=" not in header for header in headers)


def test_set_new_access_token_in_cookie_uses_named_host_domain_when_valid() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com:8443"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = _set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("Domain=app.example.com" in header for header in headers)
