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
