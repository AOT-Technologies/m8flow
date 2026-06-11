from __future__ import annotations

import os
from typing import Any, Dict

from flask import current_app, g, has_request_context

from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.tenancy import get_context_tenant_id, is_concrete_tenant_id

_ORIGINALS: Dict[str, Any] = {}
_PATCHED = False

# Reserved subdirectory used as the BPMN root for global requests (master-realm
# super-admins, login_return, public/exempt requests). Cannot collide with a
# real tenant id because the leading and trailing double-underscore characters
# are not allowed in tenant ids. When the directory does not exist on disk the
# downstream filesystem walker just returns no process models, which is the
# correct behavior for global admins who do not work with tenant content.
_GLOBAL_BPMN_SUBDIR = "__m8flow_global__"


def _is_global_request() -> bool:
    """Return True when the current request is intentionally tenant-less.

    A request is treated as global when:
      - the tenant resolver explicitly marked it via ``g._m8flow_global_request``
        (master-realm tokens, /login_return, tenant-context-exempt paths), OR
      - the request was otherwise tagged as super-admin or tenant-context-exempt, OR
      - the bearer token in the request was issued by the configured master
        realm. This last check is a fallback when the resolver did not run or
        did not populate ``g._m8flow_decoded_token``.
    """
    if not has_request_context():
        return False
    if bool(getattr(g, "_m8flow_global_request", False)):
        return True
    if bool(getattr(g, "_m8flow_super_admin_request", False)):
        return True
    if bool(getattr(g, "_m8flow_tenant_context_exempt_request", False)):
        return True

    # Fallback: detect master-realm tokens directly. Importing here avoids a
    # circular import at module load.
    try:
        from m8flow_backend.config import master_realm_name
        from m8flow_backend.services.tenant_identity_helpers import (
            authentication_identifier_from_payload,
            extract_realm_from_issuer,
        )
    except Exception:
        return False

    decoded_token = getattr(g, "_m8flow_decoded_token", None)
    if not isinstance(decoded_token, dict):
        try:
            from flask import request

            import jwt

            token: str | None = (
                getattr(g, "token", None)
                if isinstance(getattr(g, "token", None), str)
                else None
            )
            if not token:
                auth_header = (request.headers.get("Authorization") or "").strip()
                if auth_header.startswith("Bearer ") and len(auth_header) > 7:
                    token = auth_header[7:].strip() or None
            if not token:
                token = request.cookies.get("access_token")
            if token:
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_exp": False},
                )
                if isinstance(payload, dict):
                    decoded_token = payload
                    g._m8flow_decoded_token = payload
        except Exception:
            decoded_token = None

    if not isinstance(decoded_token, dict):
        return False

    master_realm = master_realm_name()
    auth_identifier = authentication_identifier_from_payload(decoded_token)
    issuer_realm = extract_realm_from_issuer(decoded_token.get("iss"))
    return auth_identifier == master_realm or issuer_realm == master_realm


def _get_tenant_id() -> str:
    """Get the current concrete tenant id from request or background context."""
    tenant_id = current_tenant_id_or_none()
    if tenant_id:
        return tenant_id

    if has_request_context():
        raise RuntimeError("Missing concrete tenant id in request context.")

    raise RuntimeError("Missing concrete tenant id in non-request context.")


def _explicit_concrete_tenant_id() -> str | None:
    """Return a concrete tenant id explicitly set on the current request/context.

    Unlike ``current_tenant_id_or_none()``, this helper deliberately does not
    short-circuit on global requests. Super-admin cross-tenant iteration keeps
    the request marked global while temporarily pinning a concrete tenant for
    filesystem reads.
    """
    if has_request_context():
        request_tenant = getattr(g, "m8flow_tenant_id", None)
        if isinstance(request_tenant, str):
            normalized = request_tenant.strip()
            if is_concrete_tenant_id(normalized):
                return normalized

    context_tenant = get_context_tenant_id()
    if isinstance(context_tenant, str):
        normalized_context_tenant = context_tenant.strip()
        if is_concrete_tenant_id(normalized_context_tenant):
            return normalized_context_tenant

    return None


def _unsafe_tenant_id(tenant_id: str) -> bool:
    return (
        not tenant_id
        or ".." in tenant_id
        or "/" in tenant_id
        or "\\" in tenant_id
    )


def _tenant_bpmn_root(base_dir: str) -> str:
    """Get tenant-specific BPMN root directory.

    Precedence:
      1. A concrete tenant id explicitly set on the request/context.
      2. Otherwise, intentionally tenant-less requests go to the reserved
         empty global subdirectory.
      3. Otherwise, resolve the tenant id from the current request/context.
    """
    normalized = os.path.abspath(os.path.normpath(base_dir))

    concrete_tenant_id = _explicit_concrete_tenant_id()
    if concrete_tenant_id:
        if _unsafe_tenant_id(concrete_tenant_id):
            raise RuntimeError("Unsafe tenant id")
        if os.path.basename(normalized) == concrete_tenant_id:
            return normalized
        return os.path.join(normalized, concrete_tenant_id)

    if _is_global_request():
        return os.path.join(normalized, _GLOBAL_BPMN_SUBDIR)

    tenant_id = current_tenant_id_or_none()
    if not tenant_id:
        tenant_id = _get_tenant_id()

    if _unsafe_tenant_id(tenant_id):
        raise RuntimeError("Unsafe tenant id")

    if os.path.basename(normalized) == tenant_id:
        return normalized
    return os.path.join(normalized, tenant_id)


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.file_system_service import FileSystemService

    _ORIGINALS["root_path"] = FileSystemService.root_path

    def patched_root_path() -> str:
        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        return _tenant_bpmn_root(base_dir)

    FileSystemService.root_path = staticmethod(patched_root_path)  # type: ignore[assignment]
    _PATCHED = True
