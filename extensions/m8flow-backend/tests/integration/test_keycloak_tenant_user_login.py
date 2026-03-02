"""
Full integration test: create tenant realm, create user in tenant, fetch access token for that user.

Requires:
- Keycloak running (e.g. extensions/m8flow-backend/keycloak/start_keycloak.sh)
- KEYCLOAK_URL (or M8FLOW_KEYCLOAK_URL), default http://localhost:7002
- KEYCLOAK_ADMIN_PASSWORD (or M8FLOW_KEYCLOAK_ADMIN_PASSWORD)
- M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 pointing to extensions/m8flow-backend/keystore.p12
- M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD

Skips if Keycloak is not configured or unreachable.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

# Ensure m8flow_backend is importable (run from repo root with PYTHONPATH or from test dir)
extension_root = Path(__file__).resolve().parents[2]  # m8flow-backend
extension_src = extension_root / "src"
for path in (extension_src,):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.config import (  # noqa: E402
    keycloak_admin_password,
    keycloak_url,
    realm_template_path,
    spoke_keystore_password,
    spoke_keystore_p12_path,
)
from m8flow_backend.services.keycloak_service import (  # noqa: E402
    create_realm_from_template,
    create_user_in_realm,
    tenant_login,
)


def _keycloak_skip_reason() -> str | None:
    """
    Return None if Keycloak is configured and reachable, else a string reason to skip.
    Keycloak API is on KEYCLOAK_URL (default http://localhost:7002); health may be on another port.
    """
    if not keycloak_admin_password():
        return (
            "Set KEYCLOAK_ADMIN_PASSWORD (or M8FLOW_KEYCLOAK_ADMIN_PASSWORD), e.g. export KEYCLOAK_ADMIN_PASSWORD=admin"
        )
    path = spoke_keystore_p12_path()
    if not path:
        return (
            "Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 to extensions/m8flow-backend/keystore.p12 (run from repo root)"
        )
    if not Path(path).exists():
        return f"Keystore not found at {path}. Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 or run from repo root."
    if not spoke_keystore_password():
        return "Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD for the keystore."
    template_path = realm_template_path()
    if not Path(template_path).exists():
        return f"Realm template not found at {template_path}. Run from repo root or set M8FLOW_KEYCLOAK_REALM_TEMPLATE_PATH."
    base = keycloak_url()
    try:
        # Keycloak API port (7002); health/ready may be on another port (7009), so check API reachability
        r = requests.get(f"{base}/realms/master", timeout=5)
        # 200 = realm exists, 401/403 = auth required, 404 = no realm yet; all mean server is up
        if r.status_code in (200, 401, 403, 404):
            return None
        return f"Keycloak at {base} returned HTTP {r.status_code}. Is it running?"
    except requests.RequestException as e:
        return f"Keycloak not reachable at {base}: {e}. Start Keycloak (e.g. extensions/m8flow-backend/keycloak/start_keycloak.sh)."


def _keycloak_available() -> bool:
    return _keycloak_skip_reason() is None


_KEYCLOAK_SKIP_REASON = _keycloak_skip_reason()


@pytest.mark.skipif(
    not _keycloak_available(),
    reason=_KEYCLOAK_SKIP_REASON or "Keycloak not available",
)
def test_create_tenant_create_user_fetch_access_token() -> None:
    """
    Full flow: create a spoke realm from template, create a user in that realm,
    then obtain an access token for that user via tenant-login.
    """
    realm_id = f"tenant-it-{uuid.uuid4().hex[:12]}"
    username = f"ituser-{uuid.uuid4().hex[:8]}"
    password = "IntegrationTestPassword1!"
    display_name = f"Integration Test Tenant {realm_id}"

    # 1. Create tenant realm from template
    result = create_realm_from_template(realm_id=realm_id, display_name=display_name)
    assert result["realm"] == realm_id
    assert result.get("displayName") == display_name

    # Keycloak may need a moment to fully provision the realm
    time.sleep(2)

    # 2. Create user in the new tenant
    user_id = create_user_in_realm(
        realm=realm_id,
        username=username,
        password=password,
        email=f"{username}@integration-test.example.com",
    )
    assert user_id
    assert len(user_id) == 36  # UUID format

    # 3. Fetch access token for the new user in the registered tenant
    token_response = tenant_login(realm=realm_id, username=username, password=password)
    assert "access_token" in token_response
    access_token = token_response["access_token"]
    assert isinstance(access_token, str)
    assert len(access_token) > 0
    assert token_response.get("token_type", "").lower() in ("bearer", "")
    if "expires_in" in token_response:
        assert token_response["expires_in"] > 0
