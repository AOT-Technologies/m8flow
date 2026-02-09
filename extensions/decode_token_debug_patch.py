# extensions/decode_token_debug_patch.py
# Patch get_decoded_token (e.g. for future decode-failure logging). No file logging by default.
# All changes in extensions; does not modify spiffworkflow_backend.


def _patched_get_decoded_token(token: str):
    from spiffworkflow_backend.routes import authentication_controller

    return authentication_controller._original_get_decoded_token(token)


def apply_decode_token_debug_patch() -> None:
    import spiffworkflow_backend.routes.authentication_controller as auth_ctrl
    auth_ctrl._original_get_decoded_token = auth_ctrl._get_decoded_token
    auth_ctrl._get_decoded_token = _patched_get_decoded_token
