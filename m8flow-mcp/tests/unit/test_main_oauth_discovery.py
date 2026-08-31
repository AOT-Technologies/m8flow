"""Unit tests for HTTP route registration in :mod:`src.main` (remote mode).

Focus: the RFC 9728 OAuth discovery documents must be advertised only when an auth
provider actually exists. Advertising them with ``_auth is None`` points clients at
/authorize, /token and /register endpoints that nothing serves, so a spec-compliant
client (Claude Desktop, Cursor) fails on dynamic client registration instead of
falling back to the bearer-token path that does work.
"""

from __future__ import annotations

from unittest.mock import patch

import src.main as main

HEALTH_ROUTES = {"/health", "/mcp/health"}
DISCOVERY_ROUTES = {
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp-protocol",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp-protocol",
}


class RecordingServer:
    """Minimal stand-in for the streamable-HTTP app, capturing add_route calls."""

    def __init__(self) -> None:
        self.routes: dict[str, object] = {}

    def add_route(self, path: str, handler: object, methods: list[str] | None = None) -> None:
        self.routes[path] = handler


def _register(proxy: object | None) -> RecordingServer:
    """Register routes with ``_oidc_proxy`` patched to ``proxy``.

    The discovery gate is the OAuth *server*, not the composed provider: a bare realm
    token verifier authenticates requests but serves no /authorize or /register, so it
    must not cause an authorization server to be advertised.
    """
    server = RecordingServer()
    with patch.object(main, "_oidc_proxy", proxy):
        main._register_http_routes(server)
    return server


# --------------------------------------------------------------------------- #
# _register_http_routes
# --------------------------------------------------------------------------- #


def test_health_routes_are_registered_without_an_oauth_server():
    """Health must never depend on authentication being configured."""
    assert set(_register(None).routes) >= HEALTH_ROUTES


def test_health_routes_are_registered_with_an_oauth_server():
    assert set(_register(object()).routes) >= HEALTH_ROUTES


def test_discovery_documents_are_omitted_without_an_oauth_server():
    """The regression under test: do not advertise an authorization server that
    does not exist."""
    registered = set(_register(None).routes)
    assert DISCOVERY_ROUTES.isdisjoint(registered)


def test_only_health_routes_are_registered_without_an_oauth_server():
    """Nothing beyond health should be exposed when browser login is off."""
    assert set(_register(None).routes) == HEALTH_ROUTES


def test_discovery_documents_are_registered_with_an_oauth_server():
    """When OIDCProxy is active the documents are needed and must be present."""
    assert set(_register(object()).routes) >= DISCOVERY_ROUTES


def test_discovery_aliases_share_the_handler_of_their_root_path():
    """The /mcp-protocol aliases exist for Cursor/Claude and must serve the same doc."""
    routes = _register(object()).routes
    for root in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"):
        assert routes[root] is routes[f"{root}/mcp-protocol"]


# --------------------------------------------------------------------------- #
# discovery document contents
# --------------------------------------------------------------------------- #


def test_advertised_endpoints_have_no_path_prefix_beyond_the_configured_base(monkeypatch):
    """A base URL carrying the /mcp endpoint path would 404 every advertised endpoint.

    Guards the misconfiguration this fix accompanied: MCP_OIDC_BASE_URL must be the
    server's root origin, so the endpoints derived from it sit at the app root.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "mcp_oidc_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings, "mcp_oidc_issuer_url", None)

    doc = main._oauth_authorization_server_document()
    assert doc["issuer"] == "http://localhost:8000"
    assert doc["authorization_endpoint"] == "http://localhost:8000/authorize"
    assert doc["token_endpoint"] == "http://localhost:8000/token"
    assert doc["registration_endpoint"] == "http://localhost:8000/register"
    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        assert "/mcp/" not in doc[key]


def test_protected_resource_document_points_at_the_issuer(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "mcp_oidc_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings, "mcp_oidc_issuer_url", None)

    doc = main._oauth_protected_resource_document()
    assert doc["resource"] == "http://localhost:8000"
    assert doc["authorization_servers"] == ["http://localhost:8000"]
    assert doc["bearer_methods_supported"] == ["header"]
