"""Internal HTTP service for Vault tenant-identity provisioning.

This process owns the policy/role write credential. The API backend receives
only a request token and can ask it to reconcile the fixed tenant policy; it
cannot submit arbitrary Vault policy text or role settings.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from m8flow_backend.config import vault_provisioner_api_token
from m8flow_backend.secrets.http import HttpVault
from m8flow_backend.secrets.provisioning import reconcile_tenant_identity

LOGGER = logging.getLogger(__name__)
MAX_BODY_BYTES = 4096


class ProvisionerHandler(BaseHTTPRequestHandler):
    server_version = "M8FlowVaultProvisioner/1"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._respond(200, {"status": "ok"})
            return
        self._respond(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/tenant-identities/ensure":
            self._respond(404, {"error": "not_found"})
            return

        expected_token = vault_provisioner_api_token()
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if (
            not expected_token
            or not supplied.startswith(prefix)
            or not hmac.compare_digest(supplied[len(prefix) :], expected_token)
        ):
            self._respond(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._respond(413 if length > MAX_BODY_BYTES else 400, {"error": "invalid_body"})
            return
        try:
            body: Any = json.loads(self.rfile.read(length))
            tenant_id = (
                body.get("tenant_id")
                if isinstance(body, dict) and set(body) == {"tenant_id"}
                else None
            )
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                raise ValueError("tenant_id is required")
            identity = reconcile_tenant_identity(tenant_id, control=self.server.vault)  # type: ignore[attr-defined]
        except (ValueError, TypeError, json.JSONDecodeError):
            self._respond(400, {"error": "invalid_tenant_id"})
            return
        except Exception as exc:
            LOGGER.warning("Vault tenant identity provisioning failed: %s", type(exc).__name__)
            self._respond(503, {"error": "provisioning_failed"})
            return

        self._respond(
            200,
            {
                "tenant_id": identity.tenant_id,
                "role_name": identity.role_name,
                "role_id": identity.role_id,
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("Vault provisioner request: " + format, *args)

    def _respond(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


class ProvisionerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], vault: HttpVault) -> None:
        super().__init__(address, ProvisionerHandler)
        self.vault = vault


def main() -> None:
    host = os.getenv("M8FLOW_VAULT_PROVISIONER_HOST", "0.0.0.0")
    port = int(os.getenv("M8FLOW_VAULT_PROVISIONER_PORT", "8098"))
    if not vault_provisioner_api_token():
        raise RuntimeError("Vault provisioner API token is not configured.")
    server = ProvisionerHTTPServer((host, port), HttpVault.from_env())
    LOGGER.info("Vault provisioner listening on %s:%d", host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
