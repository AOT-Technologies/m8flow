from __future__ import annotations

from flask import jsonify, make_response

from m8flow_backend.errors import ApiError


def success_response(data, status_code=200):
    return make_response(jsonify(data), status_code)


def error_response(error_code, message, status_code):
    return make_response(jsonify({"error_code": error_code, "message": message}), status_code)


def handle_api_errors(f):
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as e:
            return error_response(e.error_code, e.message, e.status_code)
        except Exception as e:
            return error_response("internal_server_error", str(e), 500)

    return decorated_function
