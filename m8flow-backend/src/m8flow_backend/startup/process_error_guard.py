"""Process-wide safety net for exceptions Flask's error handlers never see.

``register_error_handlers`` (startup/error_handlers.py) covers every request;
it cannot cover exceptions raised outside a request — app-factory/startup
code, or any background thread a future change spawns inside this process
(the interpreter's default behavior for an uncaught thread exception is to
dump a traceback to stderr and silently end the thread, which is easy to miss
in a container's logs and impossible to alert on in Grafana).

Installing these hooks makes "unhandled error" mean "logged as an error and
surfaced to Grafana" everywhere in the process, not just inside a request.
"""
from __future__ import annotations

import logging
import sys
import threading

LOGGER = logging.getLogger(__name__)

_INSTALLED = False


def install_process_level_error_guards() -> None:
    """Route uncaught exceptions on the main thread and any other thread
    through structured logging instead of a bare stderr traceback.

    Idempotent and safe to call every time create_app() runs (e.g. once per
    test in the test suite): the hooks are only ever installed once per
    process.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    default_excepthook = sys.excepthook

    def _log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            default_excepthook(exc_type, exc_value, exc_tb)
            return
        LOGGER.critical("Unhandled exception on main thread", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _log_uncaught_exception

    default_threading_excepthook = threading.excepthook

    def _log_uncaught_thread_exception(args: threading.ExceptHookArgs) -> None:
        LOGGER.critical(
            "Unhandled exception on thread %s",
            args.thread.name if args.thread else "<unknown>",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        # Preserve default diagnostics (stderr) in addition to structured logging.
        default_threading_excepthook(args)

    threading.excepthook = _log_uncaught_thread_exception
