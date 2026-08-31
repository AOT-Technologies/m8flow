"""Unit tests for multi-tenant selection (helpers, finalization, middleware, token forwarding)."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.auth import tenant_selection as ts


def _jwt(claims: dict) -> str:
    """Build an unsigned-looking JWT whose payload decodes to ``claims``."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


@pytest.fixture(autouse=True)
def _reset_state():
    """Keep module-level selection state and context vars from leaking between tests."""
    from src.utils import context

    ts.selection_store._by_subject.clear()
    ts.set_process_selected_session(None)
    context.clear_context()
    yield
    ts.selection_store._by_subject.clear()
    ts.set_process_selected_session(None)
    context.clear_context()


# --------------------------------------------------------------------------- #
# organization_memberships / subject_from_token
# --------------------------------------------------------------------------- #


def test_memberships_from_dict_claim():
    token = _jwt({"organization": {"acme": {"id": "t1", "name": "Acme"}, "globex": {"id": "t2"}}})
    memberships = ts.organization_memberships(token)
    assert memberships == [
        {"alias": "acme", "id": "t1", "name": "Acme"},
        {"alias": "globex", "id": "t2", "name": None},
    ]


def test_memberships_from_list_claim():
    token = _jwt({"organization": [{"alias": "acme", "id": "t1"}, "globex"]})
    memberships = ts.organization_memberships(token)
    assert memberships == [
        {"alias": "acme", "id": "t1", "name": None},
        {"alias": "globex", "id": None, "name": None},
    ]


def test_memberships_empty_when_no_claim():
    assert ts.organization_memberships(_jwt({"sub": "u"})) == []
    assert ts.organization_memberships(None) == []


def test_subject_from_token():
    assert ts.subject_from_token(_jwt({"sub": "user-123"})) == "user-123"
    assert ts.subject_from_token(_jwt({})) is None
    assert ts.subject_from_token(None) is None


# --------------------------------------------------------------------------- #
# render_selection_page
# --------------------------------------------------------------------------- #


def test_render_selection_page_lists_tenants_and_hidden_fields():
    memberships = [{"alias": "acme", "id": "t1", "name": "Acme Inc"}]
    html = ts.render_selection_page(memberships, action="/select-tenant", hidden_fields={"state": "abc"})
    assert "Acme Inc" in html
    assert 'name="tenant" value="acme"' in html
    assert 'name="state" value="abc"' in html
    assert 'action="/select-tenant"' in html
    # The CSP must not restrict form-action: POST /select-tenant redirects cross-origin to the
    # MCP client's callback, and Chrome enforces form-action across the redirect chain.
    assert "form-action" not in html
    assert "default-src 'none'" in html


# --------------------------------------------------------------------------- #
# finalize_tenant
# --------------------------------------------------------------------------- #


class _FakeCookies:
    def __init__(self, data: dict[str, str]):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeResponse:
    def __init__(self, status_code: int, cookies: dict[str, str]):
        self.status_code = status_code
        self.cookies = _FakeCookies(cookies)


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient as an async context manager."""

    def __init__(self, response=None, exc=None, **_kwargs):
        self._response = response
        self._exc = exc
        self.requested = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, cookies=None):
        self.requested = {"url": url, "params": params, "cookies": cookies}
        if self._exc:
            raise self._exc
        return self._response


def _enriched_token(exp_offset: int = 3600) -> str:
    return _jwt({"m8flow_tenant_id": "tenant-a", "sub": "svc:...", "exp": int(time.time()) + exp_offset})


async def test_finalize_tenant_success_returns_session():
    enriched = _enriched_token()
    fake = _FakeAsyncClient(
        response=_FakeResponse(302, {"m8flow_selected_tenant": "tenant-a", "access_token": enriched})
    )
    with patch.object(ts.httpx, "AsyncClient", return_value=fake):
        result = await ts.finalize_tenant("Bearer abc.def.ghi", "acme")
    assert isinstance(result, ts.FinalizedSession)
    assert result.tenant_id == "tenant-a"
    assert result.alias == "acme"
    assert result.access_token == enriched
    assert result.is_fresh
    # Drives the backend finalization endpoint with the right params + cookies.
    assert fake.requested["url"].endswith("/v1.0/login")
    assert fake.requested["params"]["tenant"] == "acme"
    assert fake.requested["params"]["tenant_finalization"] == "1"
    assert fake.requested["cookies"]["access_token"] == "abc.def.ghi"


async def test_finalize_tenant_forbidden_returns_none():
    fake = _FakeAsyncClient(response=_FakeResponse(403, {}))
    with patch.object(ts.httpx, "AsyncClient", return_value=fake):
        assert await ts.finalize_tenant("tok", "acme") is None


async def test_finalize_tenant_missing_enriched_token_returns_none():
    # Selected-tenant cookie present but no tenant-scoped access_token -> cannot fix RBAC.
    fake = _FakeAsyncClient(response=_FakeResponse(302, {"m8flow_selected_tenant": "tenant-a"}))
    with patch.object(ts.httpx, "AsyncClient", return_value=fake):
        assert await ts.finalize_tenant("tok", "acme") is None


async def test_finalize_tenant_network_error_returns_none():
    fake = _FakeAsyncClient(exc=ts.httpx.ConnectError("boom"))
    with patch.object(ts.httpx, "AsyncClient", return_value=fake):
        assert await ts.finalize_tenant("tok", "acme") is None


# --------------------------------------------------------------------------- #
# FinalizedSession freshness / refresh_if_needed
# --------------------------------------------------------------------------- #


def test_finalized_session_freshness():
    fresh = ts.FinalizedSession("acme", "t1", "tok", expires_at=time.time() + 3600)
    stale = ts.FinalizedSession("acme", "t1", "tok", expires_at=time.time() - 1)
    assert fresh.is_fresh
    assert not stale.is_fresh


async def test_refresh_if_needed_returns_fresh_session_unchanged():
    session = ts.FinalizedSession("acme", "t1", "tok", expires_at=time.time() + 3600)
    with patch.object(ts, "finalize_tenant", new=AsyncMock()) as mock_final:
        result = await ts.refresh_if_needed(session, "session-tok")
    assert result is session
    mock_final.assert_not_called()


async def test_refresh_if_needed_refinalizes_when_stale():
    stale = ts.FinalizedSession("acme", "t1", "old", expires_at=time.time() - 1)
    fresh = ts.FinalizedSession("acme", "t1", "new", expires_at=time.time() + 3600)
    with patch.object(ts, "finalize_tenant", new=AsyncMock(return_value=fresh)) as mock_final:
        result = await ts.refresh_if_needed(stale, "session-tok")
    assert result is fresh
    mock_final.assert_awaited_once_with("session-tok", "acme")


# --------------------------------------------------------------------------- #
# TenantSelectionStore
# --------------------------------------------------------------------------- #


async def test_selection_store_roundtrip():
    store = ts.TenantSelectionStore()
    assert await store.get("sub-1") is None
    session = ts.FinalizedSession("acme", "t1", "tok", expires_at=time.time() + 3600)
    await store.set("sub-1", session)
    assert await store.get("sub-1") is session
    assert await store.get(None) is None


# --------------------------------------------------------------------------- #
# TenantContextMiddleware._apply_tenant_context
# --------------------------------------------------------------------------- #


@pytest.fixture
def middleware():
    from src.middleware.tenant_context import TenantContextMiddleware

    return TenantContextMiddleware()


def _set_mode(monkeypatch, mode: str) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "server_type", mode)


async def test_apply_single_org_finalizes_and_installs_token(monkeypatch, middleware):
    from src.middleware import tenant_context as mw
    from src.utils import context

    _set_mode(monkeypatch, "stdio")
    session_token = _jwt({"organization": {"acme": {"id": "t1"}}, "sub": "u"})
    finalized = ts.FinalizedSession("acme", "t1", "enriched-tok", expires_at=time.time() + 3600)
    with patch.object(mw, "finalize_tenant", new=AsyncMock(return_value=finalized)):
        await middleware._apply_tenant_context(session_token)
    assert context._finalized_token_var.get() == "enriched-tok"
    assert context.get_tenant_id() == "t1"


async def test_apply_single_org_finalization_failure_leaves_tenant_unresolved(monkeypatch, middleware):
    """An org member whose finalization fails must NOT fall back to a default tenant."""
    from src.middleware import tenant_context as mw
    from src.utils import context

    _set_mode(monkeypatch, "stdio")
    # Single org membership AND a tenant claim: the claim must be ignored on failure.
    session_token = _jwt({"organization": {"acme": {"id": "t1"}}, "m8flow_tenant_id": "claim-tenant", "sub": "u"})
    with patch.object(mw, "finalize_tenant", new=AsyncMock(return_value=None)):
        await middleware._apply_tenant_context(session_token)
    # No finalized token, and crucially no tenant id from the claim / default fallback.
    assert context._finalized_token_var.get() is None
    assert context.get_tenant_id() is None


async def test_apply_multi_org_without_selection_installs_nothing(monkeypatch, middleware):
    from src.utils import context

    _set_mode(monkeypatch, "stdio")
    session_token = _jwt({"organization": {"acme": {"id": "t1"}, "globex": {"id": "t2"}}, "sub": "u"})
    await middleware._apply_tenant_context(session_token)
    assert context._finalized_token_var.get() is None
    assert context.get_tenant_id() is None


async def test_apply_uses_stored_selection_in_stdio(monkeypatch, middleware):
    from src.utils import context

    _set_mode(monkeypatch, "stdio")
    session_token = _jwt({"organization": {"acme": {"id": "t1"}, "globex": {"id": "t2"}}, "sub": "u"})
    stored = ts.FinalizedSession("globex", "t2", "enriched-t2", expires_at=time.time() + 3600)
    ts.set_process_selected_session(stored)
    await middleware._apply_tenant_context(session_token)
    assert context._finalized_token_var.get() == "enriched-t2"
    assert context.get_tenant_id() == "t2"


async def test_apply_uses_stored_selection_in_remote(monkeypatch, middleware):
    from src.utils import context

    _set_mode(monkeypatch, "remote")
    session_token = _jwt({"organization": {"acme": {"id": "t1"}, "globex": {"id": "t2"}}, "sub": "user-9"})
    stored = ts.FinalizedSession("globex", "t2", "enriched-t2", expires_at=time.time() + 3600)
    await ts.selection_store.set("user-9", stored)
    await middleware._apply_tenant_context(session_token)
    assert context._finalized_token_var.get() == "enriched-t2"
    assert context.get_tenant_id() == "t2"


async def test_apply_no_membership_falls_back_to_claim(monkeypatch, middleware):
    from src.utils import context

    _set_mode(monkeypatch, "stdio")
    session_token = _jwt({"m8flow_tenant_id": "claim-tenant", "sub": "u"})
    await middleware._apply_tenant_context(session_token)
    # No finalized token (no org membership), tenant from claim, session token forwarded as-is.
    assert context._finalized_token_var.get() is None
    assert context.get_tenant_id() == "claim-tenant"


# --------------------------------------------------------------------------- #
# Token forwarding: get_auth_token + api_client headers
# --------------------------------------------------------------------------- #


def test_get_auth_token_prefers_finalized(monkeypatch):
    from src.utils import context

    monkeypatch.setattr(context, "get_session_token", lambda: "session-tok")
    context.set_finalized_token(None)
    assert context.get_auth_token() == "session-tok"
    context.set_finalized_token("finalized-tok")
    assert context.get_auth_token() == "finalized-tok"


def test_build_headers_sends_only_authorization():
    from src.api_client import M8flowAPIClient

    headers = M8flowAPIClient()._build_headers("tok")
    assert headers["Authorization"] == "Bearer tok"
    assert "Cookie" not in headers
    assert "x-m8flow-tenant-id" not in headers


# --------------------------------------------------------------------------- #
# oidc_tenant_proxy helpers
# --------------------------------------------------------------------------- #


class _StubSigner:
    """Minimal stand-in providing ConsentMixin's cookie sign/verify contract."""

    def _sign_cookie(self, payload: str) -> str:
        return f"{payload}.SIG"

    def _verify_cookie(self, signed: str) -> str | None:
        return signed[:-4] if signed.endswith(".SIG") else None


def test_proxy_query_param_and_token_helpers():
    from src.auth import oidc_tenant_proxy as otp

    assert otp._query_param("https://x/cb?code=abc&state=1", "code") == "abc"
    assert otp._query_param("https://x/cb", "code") is None
    assert otp._upstream_token({"access_token": "a"}) == "a"
    assert otp._upstream_token({"id_token": "b"}) == "b"
    assert otp._upstream_token({}) is None
    assert otp._form_str("  hi ") == "hi"
    assert otp._form_str("") is None


def test_proxy_state_roundtrip_and_tamper_rejected():
    from src.auth.oidc_tenant_proxy import TenantSelectingOIDCProxy

    stub = _StubSigner()
    encoded = TenantSelectingOIDCProxy._encode_state(
        stub, client_code="code-1", client_redirect="https://client/cb?code=code-1"
    )
    decoded = TenantSelectingOIDCProxy._decode_state(stub, encoded)
    assert decoded == {"client_code": "code-1", "client_redirect": "https://client/cb?code=code-1"}
    assert TenantSelectingOIDCProxy._decode_state(stub, "garbage") is None
    assert TenantSelectingOIDCProxy._decode_state(stub, None) is None


def test_proxy_state_expires_after_ttl(monkeypatch):
    from src.auth import oidc_tenant_proxy as otp
    from src.auth.oidc_tenant_proxy import TenantSelectingOIDCProxy

    stub = _StubSigner()
    encoded = TenantSelectingOIDCProxy._encode_state(stub, client_code="code-1", client_redirect="https://client/cb")
    # Fast-forward past the TTL: a still-validly-signed state must be rejected as stale.
    real_time = otp.time.time()
    monkeypatch.setattr(otp.time, "time", lambda: real_time + otp._STATE_TTL_SECONDS + 1)
    assert TenantSelectingOIDCProxy._decode_state(stub, encoded) is None


def test_proxy_state_without_iat_rejected():
    import base64
    import json

    from src.auth.oidc_tenant_proxy import TenantSelectingOIDCProxy

    stub = _StubSigner()
    # Hand-craft a signed payload with no iat (e.g. an older state format).
    payload = base64.urlsafe_b64encode(
        json.dumps({"client_code": "c", "client_redirect": "https://client/cb"}).encode()
    ).decode()
    assert TenantSelectingOIDCProxy._decode_state(stub, stub._sign_cookie(payload)) is None


def test_validate_client_redirect_accepts_and_rejects():
    from src.auth.oidc_tenant_proxy import TenantSelectingOIDCProxy

    # No configured allowlist -> structural floor only.
    proxy = TenantSelectingOIDCProxy.__new__(TenantSelectingOIDCProxy)
    validate = TenantSelectingOIDCProxy._validate_client_redirect

    assert validate(proxy, "http://127.0.0.1:6274/oauth/callback?code=abc")
    assert validate(proxy, "https://client.example.com/cb")
    # Non-http scheme, userinfo bypass, dot-segments, and malformed URLs are rejected.
    assert not validate(proxy, "javascript:alert(1)")
    assert not validate(proxy, "http://localhost@evil.com/cb")
    assert not validate(proxy, "https://client.example.com/cb/../../steal")
    assert not validate(proxy, "/relative/only")

    # With an explicit allowlist, off-allowlist hosts are rejected even if well-formed.
    proxy._allowed_client_redirect_uris = ["http://127.0.0.1:*"]
    assert validate(proxy, "http://127.0.0.1:6274/cb")
    assert not validate(proxy, "https://client.example.com/cb")


class _FakeFormRequest:
    """Minimal POST request stand-in for _handle_select_tenant."""

    def __init__(self, form: dict[str, str]):
        self.method = "POST"
        self._form = form

    async def form(self):
        return self._form


async def test_handle_select_tenant_rejects_untrusted_redirect():
    from src.auth.oidc_tenant_proxy import TenantSelectingOIDCProxy

    proxy = TenantSelectingOIDCProxy.__new__(TenantSelectingOIDCProxy)
    # Decode returns a validly-formed state but an untrusted redirect target.
    proxy._decode_state = lambda _signed: {
        "client_code": "code-1",
        "client_redirect": "http://localhost@evil.com/cb",
    }
    request = _FakeFormRequest({"tenant": "acme", "state": "signed"})

    response = await proxy._handle_select_tenant(request)
    assert response.status_code == 400
    # Must fail before any token/finalization lookup (no _idp_tokens_for_client_code call).
