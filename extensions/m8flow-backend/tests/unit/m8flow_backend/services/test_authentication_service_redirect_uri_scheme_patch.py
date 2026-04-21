import pytest


@pytest.fixture
def reset_redirect_patch():
    from m8flow_backend.services.authentication_service_patch import reset_redirect_uri_scheme_patch

    reset_redirect_uri_scheme_patch()
    yield
    reset_redirect_uri_scheme_patch()


def _call_redirect_uri(app, *, base_url: str, forwarded_proto: str | None):
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from m8flow_backend.services.authentication_service_patch import apply_redirect_uri_scheme_patch

    headers = {}
    if forwarded_proto is not None:
        headers["X-Forwarded-Proto"] = forwarded_proto

    with app.test_request_context("/", base_url=base_url, headers=headers):
        apply_redirect_uri_scheme_patch()
        return AuthenticationService().get_redirect_uri_for_login_to_server()


def test_redirect_uri_upgrades_scheme_when_xfp_https(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="http://qa.m8flow.ai/",
            forwarded_proto="https",
        )

    assert redirect_uri == "https://qa.m8flow.ai/api/v1.0/login_return"


def test_redirect_uri_upgrades_scheme_when_xfp_https_list(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="http://qa.m8flow.ai/",
            forwarded_proto="https, http",
        )

    assert redirect_uri == "https://qa.m8flow.ai/api/v1.0/login_return"


def test_redirect_uri_unchanged_when_xfp_list_leftmost_http(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="http://qa.m8flow.ai/",
            forwarded_proto="http, https",
        )

    assert redirect_uri == "http://qa.m8flow.ai/api/v1.0/login_return"


def test_redirect_uri_unchanged_when_xfp_empty(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="http://qa.m8flow.ai/",
            forwarded_proto="",
        )

    assert redirect_uri == "http://qa.m8flow.ai/api/v1.0/login_return"


def test_redirect_uri_unchanged_when_no_forwarded_proto(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="http://qa.m8flow.ai/",
            forwarded_proto=None,
        )

    assert redirect_uri == "http://qa.m8flow.ai/api/v1.0/login_return"


def test_redirect_uri_unchanged_when_already_https(reset_redirect_patch):
    from flask import Flask
    from unittest.mock import patch

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    with patch("flask.url_for", return_value="/api/v1.0/login_return"):
        redirect_uri = _call_redirect_uri(
            app,
            base_url="https://qa.m8flow.ai/",
            forwarded_proto="https",
        )

    assert redirect_uri == "https://qa.m8flow.ai/api/v1.0/login_return"

