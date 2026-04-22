from flask import jsonify, make_response
from functools import wraps
from spiffworkflow_backend.exceptions.api_error import ApiError

def success_response(data, status_code=200):
    """Helper to create standardized success response."""
    return make_response(jsonify(data), status_code)

def error_response(error_code, message, status_code):
    """Helper to create standardized error response."""
    return make_response(jsonify({
        "error_code": error_code,
        "message": message
    }), status_code)

def handle_api_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as e:
            status_code = getattr(e, 'status_code', 400)
            error_code = getattr(e, 'error_code', 'unknown_error')
            return error_response(error_code, e.message, status_code)
        except Exception as e:
            return error_response("internal_server_error", str(e), 500)
    return decorated_function
