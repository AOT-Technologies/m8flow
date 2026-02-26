# extensions/m8flow-backend/src/m8flow_backend/services/model_override_patch.py
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys
import types

# Mapping of spiffworkflow_backend model modules to their m8flow_backend overrides.
_OVERRIDES = {
    "spiffworkflow_backend.models.api_log_model": "m8flow_backend.models.api_log_model",
    "spiffworkflow_backend.models.bpmn_process": "m8flow_backend.models.bpmn_process",
    "spiffworkflow_backend.models.bpmn_process_definition": "m8flow_backend.models.bpmn_process_definition",
    "spiffworkflow_backend.models.bpmn_process_definition_relationship": "m8flow_backend.models.bpmn_process_definition_relationship",
    "spiffworkflow_backend.models.configuration": "m8flow_backend.models.configuration",
    "spiffworkflow_backend.models.future_task": "m8flow_backend.models.future_task",
    "spiffworkflow_backend.models.human_task": "m8flow_backend.models.human_task",
    "spiffworkflow_backend.models.human_task_user": "m8flow_backend.models.human_task_user",
    "spiffworkflow_backend.models.json_data_store": "m8flow_backend.models.json_data_store",
    "spiffworkflow_backend.models.kkv_data_store": "m8flow_backend.models.kkv_data_store",
    "spiffworkflow_backend.models.kkv_data_store_entry": "m8flow_backend.models.kkv_data_store_entry",
    "spiffworkflow_backend.models.message_instance": "m8flow_backend.models.message_instance",
    "spiffworkflow_backend.models.message_instance_correlation": "m8flow_backend.models.message_instance_correlation",
    "spiffworkflow_backend.models.message_model": "m8flow_backend.models.message_model",
    "spiffworkflow_backend.models.message_triggerable_process_model": "m8flow_backend.models.message_triggerable_process_model",
    "spiffworkflow_backend.models.process_caller": "m8flow_backend.models.process_caller",
    "spiffworkflow_backend.models.process_caller_relationship": "m8flow_backend.models.process_caller_relationship",
    "spiffworkflow_backend.models.process_instance": "m8flow_backend.models.process_instance",
    "spiffworkflow_backend.models.process_instance_error_detail": "m8flow_backend.models.process_instance_error_detail",
    "spiffworkflow_backend.models.process_instance_event": "m8flow_backend.models.process_instance_event",
    "spiffworkflow_backend.models.process_instance_file_data": "m8flow_backend.models.process_instance_file_data",
    "spiffworkflow_backend.models.process_instance_metadata": "m8flow_backend.models.process_instance_metadata",
    "spiffworkflow_backend.models.process_instance_migration_detail": "m8flow_backend.models.process_instance_migration_detail",
    "spiffworkflow_backend.models.process_instance_queue": "m8flow_backend.models.process_instance_queue",
    "spiffworkflow_backend.models.process_instance_report": "m8flow_backend.models.process_instance_report",
    "spiffworkflow_backend.models.process_model_cycle": "m8flow_backend.models.process_model_cycle",
    "spiffworkflow_backend.models.pkce_code_verifier": "m8flow_backend.models.pkce_code_verifier",
    "spiffworkflow_backend.models.reference_cache": "m8flow_backend.models.reference_cache",
    "spiffworkflow_backend.models.refresh_token": "m8flow_backend.models.refresh_token",
    "spiffworkflow_backend.models.secret_model": "m8flow_backend.models.secret_model",
    "spiffworkflow_backend.models.service_account": "m8flow_backend.models.service_account",
    "spiffworkflow_backend.models.task": "m8flow_backend.models.task",
    "spiffworkflow_backend.models.task_definition": "m8flow_backend.models.task_definition",
    "spiffworkflow_backend.models.task_draft_data": "m8flow_backend.models.task_draft_data",
    "spiffworkflow_backend.models.task_instructions_for_end_user": "m8flow_backend.models.task_instructions_for_end_user",
    "spiffworkflow_backend.models.typeahead": "m8flow_backend.models.typeahead",
}

_PATCHED = False


def _clear_spiffworkflow_modules() -> None:
    """Clear spiffworkflow_backend modules from sys.modules to allow re-import."""
    for name in list(sys.modules):
        if name == "spiffworkflow_backend" or name.startswith("spiffworkflow_backend."):
            del sys.modules[name]


def _spiffworkflow_package_path() -> Path:
    """Locate the spiffworkflow_backend package path."""
    spec = importlib.util.find_spec("spiffworkflow_backend")
    if not spec or not spec.submodule_search_locations:
        raise RuntimeError("Unable to locate spiffworkflow_backend package for model overrides.")
    return Path(next(iter(spec.submodule_search_locations)))


def _ensure_stub_package(package_path: Path) -> None:
    """Ensure spiffworkflow_backend package stubs exist in sys.modules."""
    if "spiffworkflow_backend" not in sys.modules:
        stub = types.ModuleType("spiffworkflow_backend")
        stub.__path__ = [str(package_path)]
        stub._m8flow_stub = True  # type: ignore[attr-defined]
        sys.modules["spiffworkflow_backend"] = stub

    if "spiffworkflow_backend.models" not in sys.modules:
        models_stub = types.ModuleType("spiffworkflow_backend.models")
        models_stub.__path__ = [str(package_path / "models")]
        sys.modules["spiffworkflow_backend.models"] = models_stub


def _load_db_module(package_path: Path) -> None:
    """Load spiffworkflow_backend.models.db into sys.modules if not already present."""
    if "spiffworkflow_backend.models.db" in sys.modules:
        return
    db_path = package_path / "models" / "db.py"
    spec = importlib.util.spec_from_file_location("spiffworkflow_backend.models.db", db_path)
    if not spec or not spec.loader:
        raise RuntimeError("Unable to load spiffworkflow_backend.models.db for overrides.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["spiffworkflow_backend.models.db"] = module
    spec.loader.exec_module(module)


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from m8flow_backend.services.spiff_config_patch import apply as apply_spiff_config_patch
    apply_spiff_config_patch()

    existing = sys.modules.get("spiffworkflow_backend")
    if existing and not getattr(existing, "_m8flow_stub", False):
        _clear_spiffworkflow_modules()

    # Load the db module and overlays before spiffworkflow_backend.__init__ runs.
    package_path = _spiffworkflow_package_path()
    _ensure_stub_package(package_path)
    _load_db_module(package_path)

    for target, source in _OVERRIDES.items():
        module = importlib.import_module(source)
        sys.modules[target] = module

    if getattr(sys.modules.get("spiffworkflow_backend"), "_m8flow_stub", False):
        sys.modules.pop("spiffworkflow_backend.models", None)
        sys.modules.pop("spiffworkflow_backend", None)

    _PATCHED = True
