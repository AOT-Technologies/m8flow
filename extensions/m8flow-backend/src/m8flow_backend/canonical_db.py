# m8flow_backend/canonical_db.py
"""
Canonical SQLAlchemy instance for the Flask app.

Set by extensions/app.py after create_app(). Used by tenant resolution and other
m8flow_backend services so they share the same db reference without depending on
the extensions package.
"""
from __future__ import annotations

from typing import Any
from extensions.startup.guard import require_at_least, BootPhase

_canonical_db: Any = None


def set_canonical_db(db: Any) -> None:
    """Set the canonical SQLAlchemy instance (bound to the Flask app). Called by extensions/app.py after create_app()."""
    global _canonical_db
    _canonical_db = db


def get_canonical_db() -> Any:
    require_at_least(BootPhase.APP_CREATED, what="get_canonical_db()")
    if _canonical_db is None:
        raise RuntimeError("Canonical db is not set. set_canonical_db() must be called after create_app().")
    return _canonical_db
