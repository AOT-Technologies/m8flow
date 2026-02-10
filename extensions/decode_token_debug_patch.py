# extensions/decode_token_debug_patch.py
"""Patches _get_decoded_token in spiffworkflow_backend.routes.authentication_controller."""

_PATCHED = False


def _patched_get_decoded_token(token: str):
    from spiffworkflow_backend.routes import authentication_controller

    return authentication_controller._original_get_decoded_token(token)


def apply_decode_token_debug_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return
    import spiffworkflow_backend.routes.authentication_controller as auth_ctrl
    auth_ctrl._original_get_decoded_token = auth_ctrl._get_decoded_token
    auth_ctrl._get_decoded_token = _patched_get_decoded_token
    _PATCHED = True