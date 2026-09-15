"""Top-level Flask exception -> JSON response mapping.

This is the last line of defense for every request: whatever a route, a host
module, or m8flow-bpmn-core raises, the request must still end in a
structured JSON response and a logged record — never a raw Flask/Werkzeug
HTML error page, and never an exception that reaches the WSGI server
unhandled (which would otherwise surface as a bare 500 with no application
logging, or in the worst case take the worker down).

Registration order does not matter: Flask dispatches by the most specific
registered exception class in the raised exception's MRO, so ApiError,
HTTPException (Flask/Werkzeug's own 404/405/etc.), and the catch-all
Exception handler below all coexist correctly.
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from m8flow_backend.errors import ApiError

LOGGER = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(error: ApiError):
        _log_error(
            status_code=error.status_code,
            error_code=error.error_code,
            summary=f"ApiError {error.error_code}: {error.message}",
        )
        return jsonify({"error_code": error.error_code, "message": error.message}), error.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_exception(error: HTTPException):
        status_code = error.code or 500
        error_code = (error.name or "http_error").lower().replace(" ", "_")
        message = error.description or error.name or "HTTP error"
        _log_error(
            status_code=status_code,
            error_code=error_code,
            summary=f"HTTPException {status_code}: {message}",
        )
        return jsonify({"error_code": error_code, "message": message}), status_code

    @app.errorhandler(Exception)
    def _handle_unexpected_exception(error: Exception):
        # Anything reaching here is a bug (or an unmapped m8flow-bpmn-core
        # error) rather than an expected client-facing condition, so it is
        # always logged at ERROR with a full traceback regardless of status.
        _log_error(
            status_code=500,
            error_code="internal_error",
            summary=f"Unhandled {type(error).__name__}: {error}",
            exc_info=True,
        )
        return jsonify({"error_code": "internal_error", "message": "An unexpected error occurred."}), 500


def register_connexion_error_handlers(connexion_app) -> None:
    """Map Connexion's ASGI-layer problem responses to the app's JSON shape.

    Connexion routes + validates the request before Flask sees it, so its
    validation/routing errors (ProblemException -> problem+json) never reach the
    Flask error handlers above. Without this, a validation failure returns
    Connexion's ``{type,title,detail,status}`` instead of the ``{error_code,
    message}`` shape the rest of the API (and the Flask handlers) use. This
    handler renders every ProblemException in that shape so error output is
    consistent no matter which layer rejects the request.
    """
    import json

    from connexion.exceptions import ProblemException
    from connexion.lifecycle import ConnexionResponse

    def _handle_problem(request, error: ProblemException) -> ConnexionResponse:
        status_code = getattr(error, "status", None) or getattr(error, "status_code", None) or 500
        title = (getattr(error, "title", None) or "error").strip()
        error_code = title.lower().replace(" ", "_") or "error"
        message = getattr(error, "detail", None) or title
        method = getattr(request, "method", "?")
        url = getattr(request, "url", None)
        path = getattr(url, "path", None) or getattr(request, "path", "?")
        level = logging.ERROR if status_code >= 500 else logging.WARNING
        LOGGER.log(
            level,
            "%s %s -> %s: ProblemException %s: %s",
            method,
            path,
            status_code,
            error_code,
            message,
            exc_info=status_code >= 500,
            extra={
                "error_code": error_code,
                "http_status": status_code,
                "http_method": method,
                "http_path": path,
            },
        )
        return ConnexionResponse(
            status_code=status_code,
            mimetype="application/json",
            body=json.dumps({"error_code": error_code, "message": message}),
        )

    connexion_app.add_error_handler(ProblemException, _handle_problem)


def _log_error(*, status_code: int, summary: str, error_code: str | None = None, exc_info: bool = False) -> None:
    level = logging.ERROR if status_code >= 500 else logging.WARNING
    extra: dict[str, object] = {
        "http_status": status_code,
        "http_method": request.method,
        "http_path": request.path,
    }
    if error_code:
        extra["error_code"] = error_code
    LOGGER.log(
        level,
        "%s %s -> %s: %s",
        request.method,
        request.path,
        status_code,
        summary,
        exc_info=exc_info or status_code >= 500,
        extra=extra,
    )
