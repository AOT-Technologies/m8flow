from __future__ import annotations

"""
Extension-local wiring for Spiff timestamp listeners.

We ensure that m8flow models which use AuditDateTimeMixin are loaded and then
call Spiff's add_listeners() so they get the created_at_in_seconds /
updated_at_in_seconds auto-population behavior, even if they were not present
when the core backend first attached its listeners.
"""

from spiffworkflow_backend.models.db import add_listeners

# Import models that rely on AuditDateTimeMixin so they are present in
# SpiffworkflowBaseDBModel._all_subclasses() before we re-run add_listeners().
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: F401
from m8flow_backend.models.template import TemplateModel  # noqa: F401


_TIMESTAMPS_WIRED = False


def apply() -> None:
    """Attach timestamp listeners for m8flow extension models.

    This is safe to call multiple times; we guard with a simple module-level
    flag to avoid repeatedly re-registering listeners.
    """
    global _TIMESTAMPS_WIRED
    if _TIMESTAMPS_WIRED:
        return

    add_listeners()
    _TIMESTAMPS_WIRED = True

