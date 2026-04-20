# extensions/startup/logging_setup.py
import logging

def _force_root_logging_for(prefixes: tuple[str, ...]) -> None:
    for name, obj in logging.root.manager.loggerDict.items():
        if not isinstance(obj, logging.Logger):
            continue
        if name.startswith(prefixes):
            obj.handlers = []
            obj.propagate = True

    for name in prefixes:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

def _strip_all_non_root_handlers() -> None:
    for _, obj in logging.root.manager.loggerDict.items():
        if isinstance(obj, logging.Logger):
            obj.handlers = []
            obj.propagate = True

def harden_logging() -> None:
    _strip_all_non_root_handlers()
    _force_root_logging_for(("spiffworkflow_backend", "spiff", "alembic"))