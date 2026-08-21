from __future__ import annotations

from flask import make_response

from m8flow_backend.routes.health_controller_patch import _vault_status_payload


def vault_status():
    payload = _vault_status_payload()
    ok = not (payload.get("enabled") is True and payload.get("healthy") is False)
    status_code = 200 if ok else 503
    return make_response({"ok": ok, **payload}, status_code)
