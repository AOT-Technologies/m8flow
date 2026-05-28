from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import requests
from starlette.testclient import TestClient

extension_root = Path(__file__).resolve().parents[2]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (repo_root, extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.app import app  # noqa: E402
from m8flow_backend.config import (  # noqa: E402
    keycloak_admin_password,
    keycloak_url,
    master_client_secret,
    master_realm_name,
    spoke_client_id,
)
from m8flow_backend.services.keycloak_service import get_master_admin_token  # noqa: E402
from spiffworkflow_backend.exceptions.error import TokenExpiredError  # noqa: E402
from spiffworkflow_backend.services.authentication_service import AuthenticationService  # noqa: E402
from spiffworkflow_backend.services.authorization_service import AuthorizationService  # noqa: E402


def _flask_app():
    candidate = app
    if hasattr(candidate, "app") and not hasattr(candidate, "app_context"):
        candidate = candidate.app
    if hasattr(candidate, "app") and not hasattr(candidate, "app_context"):
        candidate = candidate.app
    return candidate


def _integration_skip_reason() -> str | None:
    if not keycloak_admin_password():
        return "KEYCLOAK_ADMIN_PASSWORD (or M8FLOW_KEYCLOAK_ADMIN_PASSWORD) is required."

    base_url = keycloak_url().rstrip("/")
    realm_name = master_realm_name()
    try:
        response = requests.get(f"{base_url}/realms/{realm_name}", timeout=5)
    except requests.RequestException as exc:
        return f"Keycloak master realm is not reachable at {base_url}: {exc}"

    if response.status_code not in (200, 401, 403, 404):
        return f"Keycloak master realm probe returned HTTP {response.status_code}."

    return None


_SKIP_REASON = _integration_skip_reason()


def _master_realm_token_url() -> str:
    return f"{keycloak_url().rstrip('/')}/realms/{master_realm_name()}/protocol/openid-connect/token"


def _admin_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_master_admin_token()}",
        "Content-Type": "application/json",
    }


def _resolve_keycloak_user_id(username: str) -> str:
    response = requests.get(
        f"{keycloak_url().rstrip('/')}/admin/realms/{master_realm_name()}/users",
        params={"username": username, "exact": "true"},
        headers=_admin_headers(),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise AssertionError(f"Could not resolve master realm user id for username={username!r}")
    user_id = payload[0].get("id")
    if not isinstance(user_id, str) or not user_id:
        raise AssertionError(f"Keycloak returned no user id for username={username!r}")
    return user_id


def _create_master_super_admin_user(username: str, password: str) -> str:
    create_response = requests.post(
        f"{keycloak_url().rstrip('/')}/admin/realms/{master_realm_name()}/users",
        headers=_admin_headers(),
        json={
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "email": f"{username}@integration.invalid",
            "credentials": [
                {
                    "type": "password",
                    "value": password,
                    "temporary": False,
                }
            ],
        },
        timeout=15,
    )
    create_response.raise_for_status()

    user_id = _resolve_keycloak_user_id(username)

    role_response = requests.get(
        f"{keycloak_url().rstrip('/')}/admin/realms/{master_realm_name()}/roles/super-admin",
        headers=_admin_headers(),
        timeout=15,
    )
    role_response.raise_for_status()

    assign_response = requests.post(
        f"{keycloak_url().rstrip('/')}/admin/realms/{master_realm_name()}/users/{user_id}/role-mappings/realm",
        headers=_admin_headers(),
        json=[role_response.json()],
        timeout=15,
    )
    assign_response.raise_for_status()
    return user_id


def _delete_master_user(user_id: str | None) -> None:
    if not user_id:
        return
    requests.delete(
        f"{keycloak_url().rstrip('/')}/admin/realms/{master_realm_name()}/users/{user_id}",
        headers=_admin_headers(),
        timeout=15,
    )


def _master_password_grant(username: str, password: str) -> dict:
    response = requests.post(
        _master_realm_token_url(),
        data={
            "grant_type": "password",
            "client_id": spoke_client_id(),
            "client_secret": master_client_secret(),
            "username": username,
            "password": password,
            "scope": "openid profile email",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "id_token" not in payload or "refresh_token" not in payload:
        raise AssertionError("Master realm password grant did not return id_token and refresh_token.")
    return payload


@pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "Keycloak not available")
def test_permissions_check_refreshes_master_realm_request_instead_of_returning_401(monkeypatch) -> None:
    username = f"itest-master-{uuid.uuid4().hex[:10]}"
    password = "IntegrationTestPassword1!"
    keycloak_user_id: str | None = None

    try:
        keycloak_user_id = _create_master_super_admin_user(username, password)
        auth_token = _master_password_grant(username, password)
        id_token = auth_token["id_token"]
        refresh_token = auth_token["refresh_token"]

        flask_app = _flask_app()

        with flask_app.app_context():
            decoded_token = AuthenticationService.parse_jwt_token(master_realm_name(), id_token)
            user_model = AuthorizationService.create_user_from_sign_in(decoded_token)
            AuthenticationService.store_refresh_token(
                user_model.id,
                refresh_token,
                tenant_id=master_realm_name(),
                decoded_token=decoded_token,
            )

        expired_iss = decoded_token["iss"]
        expired_sub = decoded_token["sub"]

        @classmethod
        def _force_expired_token_for_initial_request(cls, decoded_token_to_validate: dict, authentication_identifier: str) -> bool:
            if (
                authentication_identifier == master_realm_name()
                and decoded_token_to_validate.get("iss") == expired_iss
                and decoded_token_to_validate.get("sub") == expired_sub
            ):
                raise TokenExpiredError("expired for integration test")
            return True

        monkeypatch.setattr(
            AuthenticationService,
            "validate_decoded_token",
            classmethod(_force_expired_token_for_initial_request),
        )

        with TestClient(app) as client:
            response = client.post(
                "/v1.0/permissions-check",
                json={"requests_to_check": {"/v1.0/m8flow/tenants": ["GET"]}},
                headers={"Authorization": f"Bearer {id_token}"},
            )

        assert response.status_code == 200, response.text
        assert response.json() == {"results": {"/v1.0/m8flow/tenants": {"GET": True}}}
    finally:
        _delete_master_user(keycloak_user_id)
