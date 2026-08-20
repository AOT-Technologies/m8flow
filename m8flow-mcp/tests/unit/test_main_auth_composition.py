"""Unit tests for auth provider composition in :mod:`src.main`.

Focus: browser login and realm access tokens must coexist. An OIDCProxy alone rejects
the token the m8flow-backend MCP bridge forwards (a proxy only recognizes tokens it
issued itself), which surfaces as "Not authorized to reach the MCP server (HTTP 401)"
on the admin catalog page. Composing the proxy with a realm JWT verifier fixes that
without giving up browser login.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import src.main as main
from src.config import settings


class FakeProxy:
    """Stand-in for TenantSelectingOIDCProxy.

    MultiAuth inherits these three off the wrapped server when no override is passed,
    so a stand-in has to carry them.
    """

    base_url = "http://localhost:8000"
    resource_base_url = "http://localhost:8000"
    required_scopes: list[str] = []


class FakeVerifier:
    """Stand-in for JWTVerifier."""


# --------------------------------------------------------------------------- #
# _compose_auth
# --------------------------------------------------------------------------- #


def test_compose_returns_none_when_nothing_is_configured():
    """No proxy and no verifier means the transport is genuinely unauthenticated."""
    assert main._compose_auth(None, []) is None


def test_compose_returns_the_proxy_alone_when_no_verifiers():
    """Browser-login-only setups keep their previous provider exactly."""
    proxy = FakeProxy()
    assert main._compose_auth(proxy, []) is proxy


def test_compose_wraps_verifiers_alone_in_multi_auth():
    """A realm verifier with no proxy still has to gate the transport."""
    verifier = FakeVerifier()
    composed = main._compose_auth(None, [verifier])
    assert composed is not None
    assert composed is not verifier
    assert type(composed).__name__ == "MultiAuth"


def test_compose_combines_proxy_and_verifiers():
    """The case that fixes the 401: both credentials types accepted at once."""
    composed = main._compose_auth(FakeProxy(), [FakeVerifier()])
    assert type(composed).__name__ == "MultiAuth"


def test_compose_falls_back_to_the_proxy_when_multi_auth_is_unavailable():
    """An older fastmcp must degrade to browser login, not crash the server."""
    proxy = FakeProxy()
    with patch.dict("sys.modules", {"fastmcp.server.auth": None}):
        assert main._compose_auth(proxy, [FakeVerifier()]) is proxy


def test_compose_falls_back_to_none_when_multi_auth_is_unavailable_and_no_proxy():
    with patch.dict("sys.modules", {"fastmcp.server.auth": None}):
        assert main._compose_auth(None, [FakeVerifier()]) is None


# --------------------------------------------------------------------------- #
# _build_realm_token_verifiers
# --------------------------------------------------------------------------- #


def test_realm_verifiers_built_for_the_configured_realm(monkeypatch):
    monkeypatch.setattr(settings, "accept_realm_tokens", True)
    monkeypatch.setattr(settings, "accepted_token_realms", "")
    monkeypatch.setattr(settings, "keycloak_realm", "m8flow")

    verifiers = main._build_realm_token_verifiers()
    assert len(verifiers) == 1
    assert type(verifiers[0]).__name__ == "JWTVerifier"


def test_realm_verifiers_built_for_each_named_realm(monkeypatch):
    """Super-admins sign in through master, so that realm must be accepted too."""
    monkeypatch.setattr(settings, "accept_realm_tokens", True)
    monkeypatch.setattr(settings, "accepted_token_realms", "m8flow, master")

    verifiers = main._build_realm_token_verifiers()
    assert len(verifiers) == 2
    assert all(type(v).__name__ == "JWTVerifier" for v in verifiers)


def test_realm_verifiers_empty_when_disabled(monkeypatch):
    """The opt-out must actually disable realm-token acceptance."""
    monkeypatch.setattr(settings, "accept_realm_tokens", False)
    assert main._build_realm_token_verifiers() == []


def test_realm_verifiers_survive_one_bad_realm(monkeypatch):
    """A single unusable realm must not take out the others."""
    monkeypatch.setattr(settings, "accept_realm_tokens", True)
    monkeypatch.setattr(settings, "accepted_token_realms", "bad, m8flow")

    import fastmcp.server.auth.providers.jwt as jwt_module

    real_verifier = jwt_module.JWTVerifier

    def flaky(*args, **kwargs):
        if "/realms/bad/" in (kwargs.get("jwks_uri") or ""):
            raise RuntimeError("unreachable jwks")
        return real_verifier(*args, **kwargs)

    monkeypatch.setattr(jwt_module, "JWTVerifier", flaky)
    verifiers = main._build_realm_token_verifiers()
    assert len(verifiers) == 1


# --------------------------------------------------------------------------- #
# settings helpers
# --------------------------------------------------------------------------- #


def test_accepted_realms_defaults_to_the_configured_realm(monkeypatch):
    monkeypatch.setattr(settings, "accept_realm_tokens", True)
    monkeypatch.setattr(settings, "accepted_token_realms", "")
    monkeypatch.setattr(settings, "keycloak_realm", "m8flow")
    assert settings.accepted_token_realms_list == ["m8flow"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("m8flow master", ["m8flow", "master"]),
        ("m8flow,master", ["m8flow", "master"]),
        ("  m8flow ,, master  ", ["m8flow", "master"]),
    ],
)
def test_accepted_realms_parsing(monkeypatch, raw, expected):
    monkeypatch.setattr(settings, "accept_realm_tokens", True)
    monkeypatch.setattr(settings, "accepted_token_realms", raw)
    assert settings.accepted_token_realms_list == expected


def test_accepted_realms_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "accept_realm_tokens", False)
    monkeypatch.setattr(settings, "accepted_token_realms", "m8flow")
    assert settings.accepted_token_realms_list == []


def test_realm_issuer_matches_keycloaks_own_discovery_shape(monkeypatch):
    """Must equal the `iss` Keycloak stamps, or every token fails verification."""
    monkeypatch.setattr(settings, "keycloak_url", "http://localhost:6842")
    assert settings.realm_issuer("m8flow") == "http://localhost:6842/realms/m8flow"


def test_realm_issuer_tolerates_a_trailing_slash(monkeypatch):
    monkeypatch.setattr(settings, "keycloak_url", "http://localhost:6842/")
    assert settings.realm_issuer("m8flow") == "http://localhost:6842/realms/m8flow"


def test_realm_jwks_uri_is_the_keycloak_certs_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "keycloak_url", "http://localhost:6842")
    assert settings.realm_jwks_uri("m8flow") == "http://localhost:6842/realms/m8flow/protocol/openid-connect/certs"


# --------------------------------------------------------------------------- #
# transport scope enforcement
# --------------------------------------------------------------------------- #


def test_composed_provider_does_not_inherit_the_proxy_scope_list(monkeypatch):
    """The bug this fixes: inheriting the proxy's list 403s every real token.

    OIDCProxy must keep ``organization:*`` in required_scopes because it doubles as the
    scopes requested at sign-in, but an issued token carries the granted scope rather
    than that pattern, so enforcing the same list rejects legitimate callers.
    """
    monkeypatch.setattr(settings, "transport_required_scopes", "")
    proxy = FakeProxy()
    proxy.required_scopes = ["openid", "profile", "email", "organization:*"]

    composed = main._compose_auth(proxy, [FakeVerifier()])
    assert composed.required_scopes != proxy.required_scopes
    assert not composed.required_scopes


def test_transport_scopes_are_enforced_when_configured(monkeypatch):
    """An operator can still tighten enforcement explicitly."""
    monkeypatch.setattr(settings, "transport_required_scopes", "openid profile")
    composed = main._compose_auth(FakeProxy(), [FakeVerifier()])
    assert composed.required_scopes == ["openid", "profile"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("openid", ["openid"]),
        ("openid,profile", ["openid", "profile"]),
        ("  openid ,, profile ", ["openid", "profile"]),
    ],
)
def test_transport_required_scopes_parsing(monkeypatch, raw, expected):
    monkeypatch.setattr(settings, "transport_required_scopes", raw)
    assert settings.transport_required_scopes_list == expected


def test_transport_scopes_default_to_empty():
    """Default must enforce nothing: the backend is the authorization boundary."""
    from src.config.settings import Settings

    assert Settings.model_fields["transport_required_scopes"].default == ""


def test_realm_verification_is_off_by_default():
    """Default must preserve prior behaviour: no inbound auth gate added silently.

    Enabling verification makes the server reject every request without a valid realm
    token, which a static-bearer / ROPC deployment never sends -- so it has to be an
    explicit opt-in, not a default.
    """
    from src.config.settings import Settings

    assert Settings.model_fields["accept_realm_tokens"].default is False


def test_nothing_configured_yields_no_auth_provider(monkeypatch):
    """With browser login off and verification off, auth is None exactly as before."""
    monkeypatch.setattr(settings, "accept_realm_tokens", False)
    assert main._compose_auth(None, main._build_realm_token_verifiers()) is None
