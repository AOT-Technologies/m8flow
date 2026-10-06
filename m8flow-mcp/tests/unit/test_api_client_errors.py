"""Tests for M8flowAPIClient error mapping, focused on tenant-error normalization."""

from __future__ import annotations

import pytest

from src.api_client import M8flowAPIClient
from src.errors import AuthenticationError, AuthorizationError, NotFoundError, TenantError


class _FakeResponse:
    """Minimal httpx.Response stand-in for _handle_response."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.content = b"{}"
        self.text = str(body)

    def json(self):
        return self._body


@pytest.fixture
def client():
    return M8flowAPIClient()


@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_tenant_required_maps_to_tenant_error_across_4xx(client, status_code):
    """A tenant error_code must yield guided TenantError regardless of the 4xx status."""
    resp = _FakeResponse(status_code, {"error_code": "tenant_required", "message": "nope"})
    with pytest.raises(TenantError) as excinfo:
        await client._handle_response(resp)
    assert "choose the tenant" in str(excinfo.value).lower()


async def test_generic_tenant_code_maps_to_tenant_error(client):
    resp = _FakeResponse(403, {"error_code": "tenant_mismatch", "message": "bad tenant"})
    with pytest.raises(TenantError):
        await client._handle_response(resp)


async def test_non_tenant_401_still_authentication_error(client):
    resp = _FakeResponse(401, {"error_code": "token_expired", "message": "expired"})
    with pytest.raises(AuthenticationError):
        await client._handle_response(resp)


async def test_non_tenant_403_still_authorization_error(client):
    resp = _FakeResponse(403, {"message": "forbidden"})
    with pytest.raises(AuthorizationError):
        await client._handle_response(resp)


async def test_404_still_not_found(client):
    resp = _FakeResponse(404, {"message": "missing"})
    with pytest.raises(NotFoundError):
        await client._handle_response(resp)


async def test_requests_carry_selected_tenant_cookie(client):
    """The next-gen backend resolves the tenant from m8flow_selected_tenant, not the token alone."""
    from src.utils.context import set_tenant_id

    set_tenant_id("tenant-a")
    try:
        headers = client._build_headers("tok")
    finally:
        set_tenant_id(None)
    assert headers["Cookie"] == "m8flow_selected_tenant=tenant-a"
    assert headers["Authorization"] == "Bearer tok"


async def test_put_str_sends_raw_octet_stream_body(client):
    from unittest.mock import AsyncMock, MagicMock, patch

    http = MagicMock()
    http.put = AsyncMock(return_value=_FakeResponse(200, {"name": "a.bpmn"}))
    with patch("src.api_client.get_http_client", return_value=http):
        await client.put("/v1.0/m8flow/process-models/g:m/files/a.bpmn", "tok", data="<bpmn/>")
    kwargs = http.put.await_args.kwargs
    assert kwargs["content"] == b"<bpmn/>"
    assert kwargs["headers"]["Content-Type"] == "application/octet-stream"


def test_build_headers_bearer_and_tenant_cookie(client, monkeypatch):
    monkeypatch.setattr("src.api_client.get_tenant_id", lambda: "t1")
    assert client._build_headers("abc")["Authorization"] == "Bearer abc"
    headers = client._build_headers("Bearer abc")
    assert headers["Authorization"] == "Bearer abc"
    assert headers["Cookie"] == "m8flow_selected_tenant=t1"


def test_build_headers_no_tenant_no_cookie(client, monkeypatch):
    monkeypatch.setattr("src.api_client.get_tenant_id", lambda: None)
    assert "Cookie" not in client._build_headers("abc")


def test_build_headers_merges_caller_cookie_and_keeps_tenant(client, monkeypatch):
    monkeypatch.setattr("src.api_client.get_tenant_id", lambda: "t1")
    headers = client._build_headers("abc", {"Cookie": "a=1; m8flow_selected_tenant=evil", "X-Template-Key": "k"})
    assert headers["Cookie"] == "a=1; m8flow_selected_tenant=t1"
    assert headers["X-Template-Key"] == "k"


async def test_tenant_cookie_reaches_backend_and_shared_client_keeps_no_jar(monkeypatch):
    """End-to-end through the real shared httpx client: our tenant cookie arrives, and a
    Set-Cookie from the backend is never persisted and replayed on a later request."""
    import httpx

    from src.client import http_client

    seen: list[str | None] = []

    def backend(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, headers={"set-cookie": "m8flow_selected_tenant=other; Path=/"}, json={})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(backend), trust_env=False, **kw),
    )
    monkeypatch.setattr(http_client, "_http_client", None)
    monkeypatch.setattr("src.api_client.get_tenant_id", lambda: "t1")
    api = M8flowAPIClient(base_url="http://backend")
    try:
        await api.get("/a", "tok")
        await api.get("/b", "tok")
        monkeypatch.setattr("src.api_client.get_tenant_id", lambda: None)
        await api.get("/c", "tok")
    finally:
        await http_client.shutdown_http_client()
    assert seen == ["m8flow_selected_tenant=t1", "m8flow_selected_tenant=t1", None]


@pytest.mark.parametrize(("pending", "expected"), [("", "browser page"), ("http://127.0.0.1:9/", "127.0.0.1:9")])
async def test_tenant_required_while_stdio_selection_pending(client, monkeypatch, pending, expected):
    """A call that lands before the background stdio picker finishes gets a clear
    "selection in progress" error, not the generic re-authenticate message."""
    monkeypatch.setattr("src.api_client.get_process_selection_pending", lambda: pending)
    with pytest.raises(TenantError) as excinfo:
        await client._handle_response(_FakeResponse(403, {"error_code": "tenant_required"}))
    assert "still in progress" in str(excinfo.value)
    assert expected in str(excinfo.value)
