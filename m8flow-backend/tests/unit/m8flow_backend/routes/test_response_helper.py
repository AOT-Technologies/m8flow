"""handle_api_errors: unexpected errors are logged server-side, never echoed to the client."""

from __future__ import annotations

from flask import Flask

from m8flow_backend.helpers.response_helper import handle_api_errors


def test_unhandled_exception_text_is_not_returned_to_the_client(caplog):
    @handle_api_errors
    def boom():
        raise RuntimeError("db password is hunter2")

    with Flask(__name__).app_context():
        response = boom()

    assert response.status_code == 500
    assert response.get_json() == {"error_code": "internal_server_error", "message": "An unexpected error occurred."}
    assert "hunter2" in caplog.text  # still diagnosable from the server log
