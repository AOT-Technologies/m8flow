"""Unit tests for m8flow_backend.services.authentication_service_patch (on-demand auth config)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure extensions is importable when tests run from workspace root
_workspace_root = Path(__file__).resolve().parents[4]
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


@pytest.fixture
def reset_patched_flag():
    """Allow the patch to be applied in tests."""
    from m8flow_backend.services.authentication_service_patch import (
        reset_auth_config_on_demand_patch,
    )

    reset_auth_config_on_demand_patch()
    yield
    reset_auth_config_on_demand_patch()


def test_on_demand_adds_config_when_realm_exists(reset_patched_flag):
    """When identifier is missing and realm_exists returns True, ensure_tenant_auth_config runs and retry returns config."""
    from flask import Flask

    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default", "label": "default"}
    ]
    tenant_config = {"identifier": "tenant-realm", "uri": "http://keycloak/realms/tenant-realm", "label": "tenant-realm"}

    def ensure_adds_config(flask_app, tenant):
        configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
        if not any(c.get("identifier") == tenant for c in configs):
            configs.append(tenant_config.copy())

    with (
        patch(
            "m8flow_backend.services.keycloak_service.realm_exists",
            return_value=True,
        ),
        patch(
            "m8flow_backend.services.auth_config_service.ensure_tenant_auth_config",
            side_effect=ensure_adds_config,
        ),
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch

        with app.app_context():
            apply_auth_config_on_demand_patch()
            result = __import__(
                "spiffworkflow_backend.services.authentication_service",
                fromlist=["AuthenticationService"],
            ).AuthenticationService.authentication_option_for_identifier("tenant-realm")
            assert result["identifier"] == "tenant-realm"
            assert result["uri"] == "http://keycloak/realms/tenant-realm"


def test_re_raises_when_realm_does_not_exist(reset_patched_flag):
    """When identifier is missing and realm_exists returns False, original exception is re-raised."""
    from flask import Flask

    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default"}
    ]

    with patch(
        "m8flow_backend.services.keycloak_service.realm_exists",
        return_value=False,
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch
        from spiffworkflow_backend.services.authentication_service import (
            AuthenticationOptionNotFoundError,
            AuthenticationService,
        )

        with app.app_context():
            apply_auth_config_on_demand_patch()
            with pytest.raises(AuthenticationOptionNotFoundError) as exc_info:
                AuthenticationService.authentication_option_for_identifier("unknown-realm")
            assert "unknown-realm" in str(exc_info.value)
