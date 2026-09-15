from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock

import pytest

from m8flow_backend.startup import process_error_guard


def test_install_process_level_error_guards_is_idempotent(monkeypatch):
    monkeypatch.setattr(process_error_guard, "_INSTALLED", False)
    original_excepthook = sys.excepthook
    original_threading_excepthook = threading.excepthook
    try:
        process_error_guard.install_process_level_error_guards()
        hook_after_first_install = sys.excepthook
        assert hook_after_first_install is not original_excepthook

        process_error_guard.install_process_level_error_guards()
        assert sys.excepthook is hook_after_first_install  # unchanged on second call
    finally:
        sys.excepthook = original_excepthook
        threading.excepthook = original_threading_excepthook
        process_error_guard._INSTALLED = False


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_uncaught_thread_exception_is_logged(monkeypatch):
    # Calling the installed hook directly (rather than via a real spawned
    # thread) makes the assertion below deterministic, but it also runs
    # inside pytest's own thread-exception detection, which would otherwise
    # (correctly, but irrelevantly to this test) warn about it too.
    monkeypatch.setattr(process_error_guard, "_INSTALLED", False)
    mock_logger = MagicMock()
    monkeypatch.setattr(process_error_guard, "LOGGER", mock_logger)
    original_threading_excepthook = threading.excepthook
    try:
        # Other tests/fixtures in this session may have already installed a
        # guard hook (create_app() does, and never uninstalls it - by design,
        # for a real process). Start from the pristine default here so this
        # install captures a no-op "default" hook to chain to, instead of
        # chaining onto - and double-logging through - a leftover one.
        threading.excepthook = threading.__excepthook__
        process_error_guard.install_process_level_error_guards()

        try:
            raise RuntimeError("boom from background thread")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Drive the installed hook directly (rather than via a real spawned
        # thread) so the assertion isn't racing real thread teardown.
        args = threading.ExceptHookArgs((exc_type, exc_value, exc_tb, threading.current_thread()))
        threading.excepthook(args)

        mock_logger.critical.assert_called_once()
        _message, *_rest = mock_logger.critical.call_args.args
        assert "Unhandled exception on thread" in _message
        assert mock_logger.critical.call_args.kwargs["exc_info"] == (exc_type, exc_value, exc_tb)
    finally:
        threading.excepthook = original_threading_excepthook
        process_error_guard._INSTALLED = False
