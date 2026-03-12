# extensions/startup/guard.py
from __future__ import annotations

import os
import sys
from enum import Enum

class BootPhase(str, Enum):
    PRE_BOOTSTRAP = "PRE_BOOTSTRAP"
    POST_BOOTSTRAP = "POST_BOOTSTRAP"
    APP_CREATED = "APP_CREATED"

_PHASE: BootPhase = BootPhase.PRE_BOOTSTRAP

_IMPORT_EVENTS: list[tuple[str, str]] = []  # (phase, module_name)

def record_import(module_name: str) -> None:
    _IMPORT_EVENTS.append((phase().value, module_name))

def import_events() -> list[tuple[str, str]]:
    return list(_IMPORT_EVENTS)

def set_phase(phase: BootPhase) -> None:
    global _PHASE
    _PHASE = phase

def phase() -> BootPhase:
    return _PHASE

def diagnostics_enabled() -> bool:
    return (os.getenv("M8FLOW_STARTUP_DIAGNOSTICS") or "").strip().lower() in {"1", "true", "yes", "on"}

def require_at_least(required: BootPhase, *, what: str) -> None:
    order = {
        BootPhase.PRE_BOOTSTRAP: 0,
        BootPhase.POST_BOOTSTRAP: 1,
        BootPhase.APP_CREATED: 2,
    }
    if order[_PHASE] < order[required]:
        msg = (
            f"Startup railguard violated for '{what}'.\n"
            f"  required phase >= {required}\n"
            f"  current phase  = {_PHASE}\n"
            "This usually means a fragile module (db/models) was imported before bootstrap() completed.\n"
            "Fix: move the import inside create_application() AFTER bootstrap(), or delay it to function scope."
        )
        raise RuntimeError(msg)

def snapshot_loaded(prefixes: tuple[str, ...] = ("spiffworkflow_backend", "m8flow_backend", "extensions")) -> list[str]:
    mods = []
    for name in sys.modules.keys():
        if name.startswith(prefixes):
            mods.append(name)
    return sorted(mods)