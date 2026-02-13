# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_authorization_service_patch.py
import pytest
from unittest.mock import MagicMock, patch
from m8flow_backend.services.authorization_service_patch import apply as apply_patch

@pytest.fixture
def test_setup():
    """Setup a fake class that mimics AuthorizationService."""
    class FakeAuthService:
        @classmethod
        def create_user_from_sign_in(cls, user_info):
            return user_info # Return what we received to verify changes
            
    original_method = FakeAuthService.create_user_from_sign_in
    
    # We'll use the logic from our patch's patched_create_user_from_sign_in
    # but since it's a closure, we'll recreate the logic here or import it 
    # if it was a separate function.
    # For now, let's just use the real apply_patch on our Fake class by mocking the import.
    
    from m8flow_backend.services.authorization_service_patch import apply as apply_patch
    
    with patch("spiffworkflow_backend.services.authorization_service.AuthorizationService", FakeAuthService):
        with patch("m8flow_backend.services.authorization_service_patch._PATCHED", False):
            apply_patch()
            
    return FakeAuthService, original_method

def test_create_user_from_sign_in_appends_realm(test_setup):
    fake_class, original_method = test_setup
    user_info = {
        "preferred_username": "testuser",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    # Call the patched method
    result_user_info = fake_class.create_user_from_sign_in(user_info)
    
    assert result_user_info["preferred_username"] == "testuser@test-realm"

def test_create_user_from_sign_in_idempotent(test_setup):
    fake_class, original_method = test_setup
    user_info = {
        "preferred_username": "testuser@test-realm",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    result_user_info = fake_class.create_user_from_sign_in(user_info)
    
    # Should not append twice
    assert result_user_info["preferred_username"] == "testuser@test-realm"

def test_create_user_from_sign_in_no_preferred_username(test_setup):
    fake_class, original_method = test_setup
    user_info = {
        "email": "test@example.com",
        "iss": "http://localhost:7002/realms/test-realm",
        "sub": "12345"
    }
    
    result_user_info = fake_class.create_user_from_sign_in(user_info)
    
    # No change if preferred_username is missing
    assert "preferred_username" not in result_user_info
