from __future__ import annotations

import logging

from m8flow_backend.errors import ApiError


def test_unknown_route_returns_structured_json_404(client):
    """Flask/Werkzeug routing 404s must not leak the default HTML error page."""
    response = client.get("/v1.0/this-route-does-not-exist")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload is not None
    assert payload["error_code"] == "not_found"
    assert "message" in payload


def test_method_not_allowed_returns_structured_json_405(client):
    response = client.post("/v1.0/status")
    assert response.status_code == 405
    payload = response.get_json()
    assert payload["error_code"] == "method_not_allowed"


def test_unhandled_exception_returns_generic_500_and_is_logged(app, caplog):
    """The catch-all handler must:
    - never let an unhandled exception reach the WSGI layer (server keeps running),
    - never leak internal exception details to the client,
    - always log the underlying error.
    """

    @app.get("/__test_only_boom")
    def _boom():
        raise RuntimeError("kaboom - should never reach the client")

    # Flask's TESTING mode normally re-raises unhandled exceptions instead of
    # invoking error handlers; force the real request-time behavior so this
    # test exercises the same code path production traffic hits.
    app.config["PROPAGATE_EXCEPTIONS"] = False
    client = app.test_client()

    with caplog.at_level(logging.ERROR, logger="m8flow_backend.startup.error_handlers"):
        response = client.get("/__test_only_boom")

    assert response.status_code == 500
    payload = response.get_json()
    assert payload == {"error_code": "internal_error", "message": "An unexpected error occurred."}
    assert "kaboom" not in response.get_data(as_text=True)
    assert any("kaboom" in record.getMessage() for record in caplog.records)


def test_api_error_handler_still_works_for_expected_errors(app):
    @app.get("/__test_only_api_error")
    def _api_error():
        raise ApiError("test_error", "expected failure", 409)

    client = app.test_client()
    response = client.get("/__test_only_api_error")
    assert response.status_code == 409
    assert response.get_json() == {"error_code": "test_error", "message": "expected failure"}


def test_api_error_log_carries_error_code_and_http_fields(app, caplog):
    @app.get("/__test_only_api_error_fields")
    def _api_error():
        raise ApiError("permission_denied", "nope", 403)

    client = app.test_client()
    with caplog.at_level(logging.WARNING, logger="m8flow_backend.startup.error_handlers"):
        response = client.get("/__test_only_api_error_fields")

    assert response.status_code == 403
    records = [r for r in caplog.records if getattr(r, "error_code", None)]
    assert records
    record = records[-1]
    assert record.error_code == "permission_denied"
    assert record.http_status == 403
    assert record.http_method == "GET"
    assert record.http_path == "/__test_only_api_error_fields"


def test_unhandled_exception_log_uses_internal_error_code(app, caplog):
    @app.get("/__test_only_boom_fields")
    def _boom():
        raise RuntimeError("kaboom")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    client = app.test_client()
    with caplog.at_level(logging.ERROR, logger="m8flow_backend.startup.error_handlers"):
        client.get("/__test_only_boom_fields")

    records = [r for r in caplog.records if getattr(r, "error_code", None) == "internal_error"]
    assert records
    assert records[-1].http_status == 500
