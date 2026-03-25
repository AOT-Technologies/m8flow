from __future__ import annotations

import spiffworkflow_backend.models.user as user_module
import spiffworkflow_backend.services.authentication_service as authentication_service_module

from m8flow_backend.services import generated_jwt_audience_patch


def test_apply_sets_m8flow_generated_jwt_audience(monkeypatch) -> None:
    monkeypatch.setattr(generated_jwt_audience_patch, "_PATCHED", False)
    monkeypatch.setattr(user_module, "SPIFF_GENERATED_JWT_AUDIENCE", "spiffworkflow-backend", raising=False)
    monkeypatch.setattr(
        authentication_service_module,
        "SPIFF_GENERATED_JWT_AUDIENCE",
        "spiffworkflow-backend",
        raising=False,
    )

    generated_jwt_audience_patch.apply()

    assert user_module.SPIFF_GENERATED_JWT_AUDIENCE == "m8flow-backend"
    assert authentication_service_module.SPIFF_GENERATED_JWT_AUDIENCE == "m8flow-backend"
