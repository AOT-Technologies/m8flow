from __future__ import annotations


def apply() -> None:
    """Ensure SpiffWorkflow config contains ServiceTask for upstream compatibility."""
    try:
        from SpiffWorkflow.spiff.serializer.config import SPIFF_CONFIG  # type: ignore
        from SpiffWorkflow.spiff.specs.defaults import ServiceTask  # type: ignore
    except Exception:
        return

    # Some SpiffWorkflow versions omit this key; upstream expects it to exist.
    SPIFF_CONFIG.setdefault(ServiceTask, None)
