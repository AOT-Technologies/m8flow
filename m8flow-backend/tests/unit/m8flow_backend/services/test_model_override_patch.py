from __future__ import annotations

import sys
from types import ModuleType

from m8flow_backend.services import model_override_patch


def test_purge_preimported_override_modules_removes_preimported_targets(monkeypatch) -> None:
    target_name = "spiffworkflow_backend.models.fake_model"

    preimported_target = ModuleType(target_name)
    parent_models_module = ModuleType("spiffworkflow_backend.models")
    setattr(parent_models_module, "fake_model", preimported_target)

    monkeypatch.setitem(sys.modules, target_name, preimported_target)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models", parent_models_module)
    monkeypatch.setattr(model_override_patch, "_OVERRIDES", {target_name: "m8flow_backend.models.fake_model"}, raising=False)

    purged = model_override_patch._purge_preimported_override_modules()

    assert purged == [target_name]
    assert target_name not in sys.modules
    assert not hasattr(parent_models_module, "fake_model")
