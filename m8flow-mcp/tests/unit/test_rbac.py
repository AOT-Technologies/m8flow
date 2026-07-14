"""Unit tests for RBAC role extraction and authorization (fail-closed)."""

from __future__ import annotations

import base64
import json

import pytest

from src.auth.rbac import check_authorization, get_user_roles
from src.errors import AuthorizationError


def _make_token(claims: dict) -> str:
    """Build an unsigned JWT with the given payload (signature is not verified here)."""

    def seg(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(claims)}.signature"


def test_roles_from_realm_access():
    token = _make_token({"realm_access": {"roles": ["Admin", "designer"]}})
    assert sorted(get_user_roles(token)) == ["admin", "designer"]


def test_roles_from_client_and_groups():
    token = _make_token(
        {
            "resource_access": {"m8flow-backend": {"roles": ["Editor"]}},
            "groups": ["Reviewers"],
        }
    )
    assert sorted(get_user_roles(token)) == ["editor", "reviewers"]


def test_no_roles_yields_empty_not_viewer():
    """Fail-closed: a token without role claims grants NO roles (no default viewer)."""
    token = _make_token({"preferred_username": "someone"})
    assert get_user_roles(token) == []


def test_undecodable_token_yields_empty():
    """Fail-closed: garbage tokens grant no roles instead of allowing access."""
    assert get_user_roles("not-a-jwt") == []


def test_check_authorization_allows_matching_role():
    token = _make_token({"realm_access": {"roles": ["admin"]}})
    check_authorization(token, ["Admin", "owner"])  # should not raise


def test_check_authorization_denies_missing_role():
    token = _make_token({"realm_access": {"roles": ["viewer"]}})
    with pytest.raises(AuthorizationError):
        check_authorization(token, ["admin"])


def test_check_authorization_denies_roleless_token():
    """Fail-closed: no roles in token + roles required -> denied."""
    token = _make_token({"preferred_username": "someone"})
    with pytest.raises(AuthorizationError):
        check_authorization(token, ["viewer"])


def test_check_authorization_no_requirements_allows_all():
    check_authorization("not-a-jwt", [])  # no restrictions -> no raise
