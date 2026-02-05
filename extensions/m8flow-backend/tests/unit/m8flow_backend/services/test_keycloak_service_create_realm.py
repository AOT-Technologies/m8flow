# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_keycloak_service_create_realm.py
import json
from unittest.mock import MagicMock, patch
import pytest

@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.requests.post")
@patch("m8flow_backend.services.keycloak_service.load_realm_template")
def test_create_realm_from_template_includes_client_scopes(mock_load, mock_post, mock_token):
    from m8flow_backend.services.keycloak_service import create_realm_from_template
    
    mock_token.return_value = "token"
    mock_load.return_value = {
        "realm": "template",
        "clientScopes": [{"name": "profile", "id": "old-id", "protocolMappers": [{"name": "groups", "id": "m-id"}]}],
        "identityProviders": [{"alias": "google", "internalId": "p-id"}],
        "defaultDefaultClientScopes": ["profile"],
        "defaultOptionalClientScopes": ["address"],
        "clients": [],
        "roles": {"realm": []},
        "groups": [],
        "users": []
    }
    
    # Mock responses for realm creation (Step 1) and partial import (Step 2)
    mock_post.side_effect = [
        MagicMock(status_code=201), # Step 1: Create realm
        MagicMock(status_code=200)  # Step 2: Partial import
    ]
    
    create_realm_from_template("new-realm", "New Realm")
    
    # Verify Step 2 call (Partial Import)
    assert mock_post.call_count == 2
    partial_import_call = mock_post.call_args_list[1]
    args, kwargs = partial_import_call
    payload = kwargs["json"]
    
    # Verify sanitization and inclusion
    assert "clientScopes" in payload
    assert payload["clientScopes"][0]["name"] == "profile"
    assert "id" not in payload["clientScopes"][0]
    assert "id" not in payload["clientScopes"][0]["protocolMappers"][0]
    
    assert "identityProviders" in payload
    assert payload["identityProviders"][0]["alias"] == "google"
    assert "internalId" not in payload["identityProviders"][0]
    
    assert payload["defaultDefaultClientScopes"] == ["profile"]
    assert payload["defaultOptionalClientScopes"] == ["address"]
