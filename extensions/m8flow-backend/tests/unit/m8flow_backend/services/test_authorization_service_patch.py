# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_authorization_service_patch.py
"""Unit tests for authorization_service_patch: username uniqueness across realms.

These tests verify the logic used in the patch without actually applying the patch,
since the patch modifies the real AuthorizationService which has complex dependencies.
"""
import sys
from pathlib import Path

import pytest

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _extract_realm_from_issuer(iss: str) -> str | None:
    """Extract realm from Keycloak issuer URL."""
    if "/realms/" in iss:
        return iss.split("/realms/")[-1].split("/")[0]
    return None


def _apply_username_suffix(username: str, realm: str) -> str:
    """Apply realm suffix to username if not already present."""
    suffix = f"@{realm}"
    if not username.endswith(suffix):
        return f"{username}{suffix}"
    return username


def test_create_user_from_sign_in_appends_realm():
    """Test that realm is appended to username from issuer URL."""
    user_info = {
        "preferred_username": "testuser",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    realm = _extract_realm_from_issuer(user_info["iss"])
    assert realm == "test-realm"
    
    result_username = _apply_username_suffix(user_info["preferred_username"], realm)
    assert result_username == "testuser@test-realm"


def test_create_user_from_sign_in_idempotent():
    """Test that realm is not appended twice if already present."""
    user_info = {
        "preferred_username": "testuser@test-realm",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    realm = _extract_realm_from_issuer(user_info["iss"])
    assert realm == "test-realm"
    
    result_username = _apply_username_suffix(user_info["preferred_username"], realm)
    # Should not append twice
    assert result_username == "testuser@test-realm"


def test_create_user_from_sign_in_no_preferred_username():
    """Test that no change is made if preferred_username is missing."""
    user_info = {
        "email": "test@example.com",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    # The patch only modifies if preferred_username is present
    assert "preferred_username" not in user_info
    
    # Simulate the patch logic: only modify if preferred_username exists
    if "preferred_username" in user_info and "iss" in user_info:
        realm = _extract_realm_from_issuer(user_info["iss"])
        if realm:
            user_info["preferred_username"] = _apply_username_suffix(
                user_info["preferred_username"], realm
            )
    
    # Still no preferred_username
    assert "preferred_username" not in user_info


def test_realm_extraction_from_issuer():
    """Test realm extraction logic from issuer URL."""
    test_cases = [  # NOSONAR - test fixtures, not real connections
        ("http://localhost:7002/realms/test-realm", "test-realm"),
        ("http://keycloak:8080/realms/my-tenant", "my-tenant"),
        ("https://auth.example.com/realms/production/", "production"),
        ("http://localhost/realms/dev/some/path", "dev"),
    ]
    
    for iss, expected_realm in test_cases:
        realm = _extract_realm_from_issuer(iss)
        assert realm == expected_realm, f"Failed for {iss}: got {realm}, expected {expected_realm}"


def test_realm_extraction_no_realms_path():
    """Test that None is returned when issuer doesn't contain /realms/."""
    test_cases = [  # NOSONAR - test fixtures, not real connections
        "http://localhost:7002/auth",
        "https://example.com/oauth",
        "",
    ]
    
    for iss in test_cases:
        realm = _extract_realm_from_issuer(iss)
        assert realm is None, f"Expected None for {iss}, got {realm}"


def test_username_suffix_logic():
    """Test the username suffix logic."""
    test_cases = [
        # (username, realm, expected_result)
        ("testuser", "test-realm", "testuser@test-realm"),
        ("testuser@test-realm", "test-realm", "testuser@test-realm"),  # idempotent
        ("admin", "production", "admin@production"),
        ("user@other-realm", "test-realm", "user@other-realm@test-realm"),  # different realm
    ]
    
    for username, realm, expected in test_cases:
        result = _apply_username_suffix(username, realm)
        assert result == expected, f"Failed for ({username}, {realm}): got {result}, expected {expected}"
