# extensions/invalid_token_log_patch.py
"""Patch handle_exception so invalid_token (e.g. 'Cannot validate token') is logged briefly
without the long 'see api_error.py' message. Still no Sentry and no backtrace (api_error.py
uses logger.warning without exc_info for these)."""

_PATCHED = False


def apply_invalid_token_log_patch() -> None:
    """Wrap handle_exception: for ApiError with error_code invalid_token, use a short debug log."""
    global _PATCHED
    if _PATCHED:
        return
    from spiffworkflow_backend.exceptions import api_error as api_error_module

    original_handle_exception = api_error_module.handle_exception

    def wrapped_handle_exception(app, request, exception):
        from spiffworkflow_backend.exceptions.api_error import ApiError

        if isinstance(exception, ApiError) and getattr(exception, "error_code", None) == "invalid_token":
            orig_warning = app.logger.warning

            def quiet_warning(msg, *args, **kwargs):
                if "see api_error.py" in str(msg):
                    app.logger.debug("Invalid token (excluded from Sentry).")
                    return
                orig_warning(msg, *args, **kwargs)

            app.logger.warning = quiet_warning
            try:
                return original_handle_exception(app, request, exception)
            finally:
                app.logger.warning = orig_warning
        return original_handle_exception(app, request, exception)

    api_error_module.handle_exception = wrapped_handle_exception
    _PATCHED = True
