from __future__ import annotations

"""
Extension-local wiring for Spiff timestamp listeners.

We attach timestamp listeners only to mapped models that have created_at_in_seconds
and/or updated_at_in_seconds. Idempotency is ensured by the _PATCHED flag and
event.contains() to avoid duplicate listener registration when using a patching approach.
"""

from sqlalchemy import event

from spiffworkflow_backend.models.db import (
    SpiffworkflowBaseDBModel,
    update_created_modified_on_create_listener,
    update_modified_on_update_listener,
)

# Import models that rely on AuditDateTimeMixin so they are present in
# SpiffworkflowBaseDBModel._all_subclasses() when apply() runs.
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: F401
from m8flow_backend.models.template import TemplateModel  # noqa: F401


_PATCHED = False


def apply() -> None:
    """Attach timestamp listeners for any mapped model that has *_at_in_seconds.

    Idempotent via:
    - _PATCHED flag (extension convention)
    - event.contains(...) (prevents duplicate listener registration)
    """
    global _PATCHED
    if _PATCHED:
        return

    for cls in SpiffworkflowBaseDBModel._all_subclasses():
        mapper = getattr(cls, "__mapper__", None)
        if mapper is None:
            continue  # not mapped yet

        cols = mapper.columns.keys()
        has_created = "created_at_in_seconds" in cols
        has_updated = "updated_at_in_seconds" in cols
        if not (has_created or has_updated):
            continue

        if not event.contains(cls, "before_insert", update_created_modified_on_create_listener):
            event.listen(cls, "before_insert", update_created_modified_on_create_listener)

        if not event.contains(cls, "before_update", update_modified_on_update_listener):
            event.listen(cls, "before_update", update_modified_on_update_listener)

    _PATCHED = True