# extensions/bootstrap.py
from extensions.startup.patch_registry import (
    PRE_APP_PATCH_SPECS,
    POST_APP_CORE_PATCH_SPECS,
    apply_patch_specs,
)


def bootstrap() -> None:
    # ONLY safe-to-run pre-app hooks here.
    # No model imports. No patches that import m8flow_backend.models.*
    apply_patch_specs(PRE_APP_PATCH_SPECS)


def bootstrap_after_app(flask_app) -> None:
    """
    Patches that are allowed to import models or rely on an app/db being created.
    This runs after spiffworkflow_backend.create_app().
    """
    apply_patch_specs(POST_APP_CORE_PATCH_SPECS, flask_app=flask_app)


def ensure_m8flow_audit_timestamps() -> None:
    """Ensure m8flow models that use AuditDateTimeMixin participate in Spiff's timestamp listeners."""
    from m8flow_backend.models._timestamps_bootstrap import apply as apply_m8flow_timestamp_listeners
    apply_m8flow_timestamp_listeners()
