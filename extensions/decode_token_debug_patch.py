# extensions/decode_token_debug_patch.py
# Log token decode failures to debug.log for debugging "Cannot decode token" (invalid_token).
# All changes in extensions; does not modify spiffworkflow_backend.

import json
import time

import jwt

_DEBUG_LOG_PATH = "/Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log"


def _log_decode_failure(
    exc: Exception, authentication_identifier: str, token_preview: str, token_iss: str = ""
) -> None:
    try:
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(
                json.dumps(
                    {
                        "hypothesisId": "decode_fail",
                        "location": "decode_token_debug_patch._patched_get_decoded_token",
                        "message": "Token decode failed",
                        "data": {
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc)[:300],
                            "authentication_identifier": authentication_identifier,
                            "token_iss": token_iss[:200] if token_iss else "",
                            "token_preview": token_preview[:80] if token_preview else "",
                        },
                        "timestamp": int(time.time() * 1000),
                        "sessionId": "debug-session",
                        "runId": "decode-debug",
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def _patched_get_decoded_token(token: str):
    from spiffworkflow_backend.routes import authentication_controller
    from flask import request

    auth_id = "default"
    if hasattr(request, "cookies") and request.cookies.get("authentication_identifier"):
        auth_id = request.cookies["authentication_identifier"]
    if hasattr(request, "headers") and request.headers.get("SpiffWorkflow-Authentication-Identifier"):
        auth_id = request.headers["SpiffWorkflow-Authentication-Identifier"]

    try:
        unverified = jwt.decode(token, options={"verify_signature": False}) if token else {}
        token_iss = unverified.get("iss", "")
    except Exception:
        token_iss = "<decode_failed>"

    try:
        return authentication_controller._original_get_decoded_token(token)
    except Exception as e:
        _log_decode_failure(e, auth_id, token or "", token_iss)
        raise


def apply_decode_token_debug_patch() -> None:
    import spiffworkflow_backend.routes.authentication_controller as auth_ctrl
    auth_ctrl._original_get_decoded_token = auth_ctrl._get_decoded_token
    auth_ctrl._get_decoded_token = _patched_get_decoded_token
