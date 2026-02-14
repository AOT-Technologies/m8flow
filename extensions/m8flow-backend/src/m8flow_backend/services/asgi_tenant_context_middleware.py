# extensions/m8flow-backend/src/m8flow_backend/services/asgi_tenant_context_middleware.py
from __future__ import annotations

import base64
import json
from http.cookies import SimpleCookie
from typing import Callable, Optional

from m8flow_backend.tenancy import (
    PUBLIC_PATH_PREFIXES,
    TENANT_CLAIM,
    reset_context_tenant_id,
    set_context_tenant_id,
)


def _get_header(scope, name: bytes) -> Optional[str]:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            try:
                return v.decode("latin-1")
            except Exception:
                return None
    return None


def _jwt_payload(token: str) -> Optional[dict]:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        return json.loads(payload_json)
    except Exception:
        return None


def _tenant_from_token(token: str) -> Optional[str]:
    payload = _jwt_payload(token)
    if not payload:
        return None
    tenant = payload.get(TENANT_CLAIM)
    if isinstance(tenant, str) and tenant:
        return tenant
    return None


def _extract_access_token_from_cookie(scope) -> Optional[str]:
    cookie_header = _get_header(scope, b"cookie")
    if not cookie_header:
        return None
    c = SimpleCookie()
    try:
        c.load(cookie_header)
    except Exception:
        return None
    morsel = c.get("access_token")
    return morsel.value if morsel and morsel.value else None


def _extract_tenant(scope) -> Optional[str]:
    auth = _get_header(scope, b"authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[len("Bearer ") :].strip()
        return _tenant_from_token(token)

    cookie_token = _extract_access_token_from_cookie(scope)
    if cookie_token:
        return _tenant_from_token(cookie_token)

    return None


def _is_public_path(scope) -> bool:
    path = scope.get("path") or ""
    return any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


class AsgiTenantContextMiddleware:
    """
    ASGI middleware to set tenant context based on request.
    Inspects Authorization header and access_token cookie for JWT tokens
    """
    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and _is_public_path(scope):
            token = set_context_tenant_id("public")
            try:
                return await self.app(scope, receive, send)
            finally:
                reset_context_tenant_id(token)

        token = None
        try:
            tenant_id = _extract_tenant(scope)
            if tenant_id:
                token = set_context_tenant_id(tenant_id)
            return await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_context_tenant_id(token)
