from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import logging
from typing import Any

from extensions.startup.guard import BootPhase, require_at_least


@dataclass(frozen=True)
class PatchSpec:
    target: str
    minimum_phase: BootPhase
    needs_flask_app: bool = False
    optional_import: bool = False
    ignore_errors: bool = False


_APPLIED_PATCH_TARGETS: set[str] = set()


def _get_app_applied_patch_targets(flask_app: Any) -> set[str]:
    targets = getattr(flask_app, "_m8flow_applied_patch_targets", None)
    if targets is None:
        targets = set()
        setattr(flask_app, "_m8flow_applied_patch_targets", targets)
    return targets


def _resolve_patch_target(target: str):
    module_name, function_name = target.split(":", 1)
    module = import_module(module_name)
    return getattr(module, function_name), module_name, function_name


def apply_patch_spec(spec: PatchSpec, *, flask_app: Any | None = None, logger: logging.Logger | None = None) -> bool:
    require_at_least(spec.minimum_phase, what=f"patch '{spec.target}'")

    target_module_name = spec.target.split(":", 1)[0]

    app_targets: set[str] | None = None
    if spec.needs_flask_app:
        if flask_app is None:
            raise RuntimeError(f"Patch '{spec.target}' requires a Flask app instance")
        app_targets = _get_app_applied_patch_targets(flask_app)
        if spec.target in app_targets:
            return False
    elif spec.target in _APPLIED_PATCH_TARGETS:
        return False

    try:
        patch_fn, _module_name, _function_name = _resolve_patch_target(spec.target)
    except ModuleNotFoundError as exc:
        # Only suppress when the target module itself is missing.
        # If a dependency inside that module is missing, propagate.
        if spec.optional_import and exc.name and (
            exc.name == target_module_name or target_module_name.startswith(f"{exc.name}.")
        ):
            return False
        raise

    try:
        if spec.needs_flask_app:
            patch_fn(flask_app)
        else:
            patch_fn()
    except Exception:
        if spec.ignore_errors:
            if logger is not None:
                logger.warning("Failed applying patch '%s'", spec.target, exc_info=True)
            return False
        raise

    if spec.needs_flask_app:
        assert app_targets is not None
        app_targets.add(spec.target)
    else:
        _APPLIED_PATCH_TARGETS.add(spec.target)
    return True


def apply_patch_specs(
    specs: tuple[PatchSpec, ...], *, flask_app: Any | None = None, logger: logging.Logger | None = None
) -> None:
    for spec in specs:
        apply_patch_spec(spec, flask_app=flask_app, logger=logger)


PRE_APP_PATCH_SPECS: tuple[PatchSpec, ...] = (
    PatchSpec(
        target="m8flow_backend.services.spiff_config_patch:apply",
        minimum_phase=BootPhase.PRE_BOOTSTRAP,
    ),
    PatchSpec(
        target="m8flow_backend.services.model_override_patch:apply",
        minimum_phase=BootPhase.PRE_BOOTSTRAP,
    ),
    PatchSpec(
        target="m8flow_backend.services.openapi_merge_patch:apply",
        minimum_phase=BootPhase.PRE_BOOTSTRAP,
    ),
)


POST_APP_CORE_PATCH_SPECS: tuple[PatchSpec, ...] = (
    PatchSpec(
        target="m8flow_backend.routes.authentication_controller_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.file_system_service_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.tenant_scoping_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.logging_service_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.authorization_service_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.authentication_service_patch:apply_openid_discovery_patch",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.services.authentication_service_patch:apply_auth_token_error_patch",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.routes.authentication_controller_patch:apply_decode_token_debug_patch",
        minimum_phase=BootPhase.APP_CREATED,
    ),
    PatchSpec(
        target="m8flow_backend.routes.authentication_controller_patch:apply_master_realm_auth_patch",
        minimum_phase=BootPhase.APP_CREATED,
    ),
)


POST_APP_EXTENSION_PATCH_SPECS: tuple[PatchSpec, ...] = (
    PatchSpec(
        target="m8flow_backend.routes.authentication_controller_patch:apply_login_tenant_patch",
        minimum_phase=BootPhase.APP_CREATED,
        needs_flask_app=True,
        optional_import=True,
    ),
    PatchSpec(
        target="m8flow_backend.services.authentication_service_patch:apply_auth_config_on_demand_patch",
        minimum_phase=BootPhase.APP_CREATED,
        optional_import=True,
    ),
    PatchSpec(
        target="m8flow_backend.services.user_service_patch:apply",
        minimum_phase=BootPhase.APP_CREATED,
        ignore_errors=True,
    ),
)


def all_patch_specs() -> tuple[PatchSpec, ...]:
    return PRE_APP_PATCH_SPECS + POST_APP_CORE_PATCH_SPECS + POST_APP_EXTENSION_PATCH_SPECS


def registered_patch_modules() -> set[str]:
    return {spec.target.split(":", 1)[0] for spec in all_patch_specs()}
