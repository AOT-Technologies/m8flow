# extensions/m8flow-backend/src/m8flow_backend/services/model_override_patch.py
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import logging
import sys
from types import ModuleType


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
LOGGER = logging.getLogger(__name__)


class _OverrideLoader(importlib.abc.Loader):
    def __init__(self, target_name: str, source_name: str):
        self.target_name = target_name
        self.source_name = source_name

    def create_module(self, spec):
        # default module creation
        return None

    def exec_module(self, module: ModuleType) -> None:
        # Load the real source module, then copy its namespace into the target module.
        src = importlib.import_module(self.source_name)
        module.__dict__.update(src.__dict__)
        module.__dict__["__name__"] = self.target_name


class _OverrideFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path, target=None):
        source = _OVERRIDES.get(fullname)
        if not source:
            return None
        return importlib.util.spec_from_loader(fullname, _OverrideLoader(fullname, source))


def _purge_preimported_override_modules() -> list[str]:
    """
    Remove already-imported spiff model modules that should be overridden.
    They will be re-imported through the override finder.
    """
    purged: list[str] = []
    for target_name in _OVERRIDES:
        if target_name not in sys.modules:
            continue

        sys.modules.pop(target_name, None)

        parent_name, _, leaf_name = target_name.rpartition(".")
        parent_module = sys.modules.get(parent_name)
        if parent_module is not None and hasattr(parent_module, leaf_name):
            try:
                delattr(parent_module, leaf_name)
            except Exception:
                pass

        purged.append(target_name)
    return purged


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    # Ensure config patch is applied early (keep this)
    from m8flow_backend.services.spiff_config_patch import apply as apply_spiff_config_patch
    apply_spiff_config_patch()

    purged = _purge_preimported_override_modules()
    if purged:
        LOGGER.warning(
            "model_override_patch: purged pre-imported spiff model modules before installing overrides: %s",
            sorted(purged),
        )

    # Install finder once, at the front so it wins
    if not any(isinstance(f, _OverrideFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _OverrideFinder())

    _PATCHED = True
