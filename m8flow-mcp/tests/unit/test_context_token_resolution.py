"""Unit tests for token resolution in :mod:`src.utils.context`.

Focus: the per-request forwarded ``Authorization`` bearer token. The m8flow-backend
MCP catalog bridge authenticates by forwarding the calling user's own token in that
header, so a tool that cannot see it fails with "No authentication token available"
even though the caller was fully authenticated (M8F-404).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.utils import context


@pytest.fixture(autouse=True)
def _reset_context():
    """Keep context vars from leaking between tests."""
    context.clear_context()
    yield
    context.clear_context()


def _with_headers(headers: dict[str, str] | None):
    """Patch fastmcp's ``get_http_headers`` fallback as ``_forwarded_bearer_token`` sees it.

    ``get_http_request`` is left unpatched here, so it raises (no active request) and
    resolution falls through to this accessor -- which is the path older fastmcp
    versions take. ``headers is None`` simulates this accessor being unavailable too.
    """

    def fake_get_http_headers(include_all: bool = False, include: set[str] | None = None):
        if headers is None:
            raise RuntimeError("no active HTTP request")
        # Mirror fastmcp: 'authorization' is excluded unless explicitly opted in.
        opted_in = include is not None and "authorization" in include
        return {k: v for k, v in headers.items() if k != "authorization" or include_all or opted_in}

    return patch("fastmcp.server.dependencies.get_http_headers", fake_get_http_headers)


def _with_request(headers: dict[str, str]):
    """Patch fastmcp's ``get_http_request`` -- the primary accessor.

    Unlike ``get_http_headers`` the raw Starlette request does not filter
    ``authorization``, so the headers are returned verbatim. Starlette header lookup
    is case-insensitive; the mapping is lower-cased here to match.
    """
    lowered = {k.lower(): v for k, v in headers.items()}
    request = SimpleNamespace(headers=lowered)
    return patch("fastmcp.server.dependencies.get_http_request", lambda: request)


@pytest.fixture
def no_ropc(monkeypatch):
    """Disable the ROPC strategy so resolution stops at the token being tested.

    ``has_ropc_credentials`` is a derived property, so the credentials it reads are
    what get cleared (same instance-attribute approach the other suites use).
    """
    from src.config import settings

    monkeypatch.setattr(settings, "keycloak_username", None)
    monkeypatch.setattr(settings, "keycloak_password", None)
    assert settings.has_ropc_credentials is False


@pytest.fixture
def with_ropc(monkeypatch):
    """Enable the ROPC strategy and stub the token it would fetch."""
    from src.config import settings

    monkeypatch.setattr(settings, "keycloak_username", "svc-user")
    monkeypatch.setattr(settings, "keycloak_password", "svc-pass")
    assert settings.has_ropc_credentials is True


# --------------------------------------------------------------------------- #
# _forwarded_bearer_token
# --------------------------------------------------------------------------- #


def test_forwarded_bearer_token_reads_the_authorization_header():
    """The header fastmcp strips by default must still be readable here."""
    with _with_headers({"authorization": "Bearer abc.def.ghi"}):
        assert context._forwarded_bearer_token() == "abc.def.ghi"


def test_forwarded_bearer_token_is_scheme_case_insensitive():
    """RFC 7235 auth schemes are case-insensitive."""
    with _with_headers({"authorization": "bearer abc.def.ghi"}):
        assert context._forwarded_bearer_token() == "abc.def.ghi"


def test_forwarded_bearer_token_strips_the_bearer_prefix():
    """Callers get the raw credential; api_client re-adds the scheme itself."""
    with _with_headers({"authorization": "Bearer   padded.token.value  "}):
        assert context._forwarded_bearer_token() == "padded.token.value"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "abc.def.ghi"],
)
def test_forwarded_bearer_token_rejects_non_bearer_and_empty_headers(header):
    """Anything that is not a non-empty Bearer credential resolves to None."""
    with _with_headers({"authorization": header}):
        assert context._forwarded_bearer_token() is None


def test_forwarded_bearer_token_is_none_without_an_http_request():
    """stdio mode has no HTTP request; this must degrade quietly, not raise."""
    with _with_headers(None):
        assert context._forwarded_bearer_token() is None


def test_forwarded_bearer_token_is_none_when_no_auth_header_was_sent():
    with _with_headers({"content-type": "application/json"}):
        assert context._forwarded_bearer_token() is None


def test_forwarded_bearer_token_reads_the_raw_starlette_request():
    """Primary path: the unfiltered request headers, no ``include`` opt-in needed."""
    with _with_request({"Authorization": "Bearer abc.def.ghi"}):
        assert context._forwarded_bearer_token() == "abc.def.ghi"


def test_forwarded_bearer_token_is_none_when_the_request_has_no_auth_header():
    with _with_request({"content-type": "application/json"}):
        assert context._forwarded_bearer_token() is None


def test_get_auth_token_uses_the_raw_starlette_request(no_ropc):
    """End-to-end resolution through the primary accessor."""
    with _with_request({"Authorization": "Bearer caller.own.token"}):
        assert context.get_auth_token() == "caller.own.token"


def test_request_accessor_is_preferred_over_the_headers_fallback(no_ropc):
    """When both accessors work, the raw request wins."""
    with (
        _with_request({"Authorization": "Bearer from.request"}),
        _with_headers({"authorization": "Bearer from.headers"}),
    ):
        assert context.get_session_token() == "from.request"


# --------------------------------------------------------------------------- #
# get_session_token / get_auth_token resolution order
# --------------------------------------------------------------------------- #


def test_get_session_token_uses_the_forwarded_header(no_ropc):
    """The regression under test: a forwarded token must resolve to a usable token."""
    with _with_headers({"authorization": "Bearer caller.own.token"}):
        assert context.get_session_token() == "caller.own.token"


def test_get_auth_token_uses_the_forwarded_header(no_ropc):
    """Tools call get_auth_token; it must not return None for an authenticated caller."""
    with _with_headers({"authorization": "Bearer caller.own.token"}):
        assert context.get_auth_token() == "caller.own.token"


def test_forwarded_header_outranks_the_static_service_token(no_ropc):
    """Tenant isolation: a caller's own token must win over a shared service identity.

    Serving a caller's request with the process-wide M8FLOW_BEARER_TOKEN would run
    their tools under that service account's tenant and permissions.
    """
    context.set_auth_token("Bearer static.service.token")
    with _with_headers({"authorization": "Bearer caller.own.token"}):
        assert context.get_session_token() == "caller.own.token"


def test_static_service_token_still_used_when_no_header_is_forwarded(no_ropc):
    """Existing static-bearer deployments keep working unchanged."""
    context.set_auth_token("Bearer static.service.token")
    with _with_headers({"content-type": "application/json"}):
        assert context.get_session_token() == "Bearer static.service.token"


def test_oidc_session_token_outranks_the_forwarded_header(no_ropc):
    """A verified auth-provider session stays authoritative over a raw header."""
    with (
        patch("src.utils.context._oidc_session_token", return_value="verified.session.token"),
        _with_headers({"authorization": "Bearer caller.own.token"}),
    ):
        assert context.get_session_token() == "verified.session.token"


def test_forwarded_header_outranks_ropc_auto_login(with_ropc):
    """A per-caller identity must win over ROPC's shared service login."""
    with (
        _with_headers({"authorization": "Bearer caller.own.token"}),
        patch("src.auth.token_service.token_service.get_token_sync", return_value="ropc.token"),
    ):
        assert context.get_session_token() == "caller.own.token"


def test_ropc_still_used_when_no_header_is_forwarded(with_ropc):
    """The ROPC fallback keeps working for clients that send no Authorization header."""
    with (
        _with_headers({}),
        patch("src.auth.token_service.token_service.get_token_sync", return_value="ropc.token"),
    ):
        assert context.get_session_token() == "ropc.token"


def test_finalized_tenant_token_still_outranks_the_forwarded_header(no_ropc):
    """TenantContextMiddleware's tenant-scoped token remains what tools forward."""
    context.set_finalized_token("finalized.tenant.token")
    with _with_headers({"authorization": "Bearer caller.own.token"}):
        assert context.get_auth_token() == "finalized.tenant.token"


def test_get_session_token_is_none_when_nothing_is_configured(no_ropc):
    """No header, no static token, no ROPC -> genuinely unauthenticated."""
    with _with_headers({}):
        assert context.get_session_token() is None
