from __future__ import annotations

from flask import make_response

from m8flow_backend.routes.health_controller_patch import _vault_status_payload


def vault_status():
    payload = _vault_status_payload()
    enabled = bool(payload.get("enabled"))
    configured = bool(payload.get("configured"))
    healthy = payload.get("healthy")

    if not enabled:
        ok = True
    elif not configured:
        ok = False
    else:
        ok = healthy is True

    status_code = 200 if ok else 503
    return make_response({"ok": ok, **payload}, status_code)
