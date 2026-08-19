"""Unit tests for notification_smtp_controller.

Tests cover:
- GET /notification-smtp-status returns 200 with SMTP configuration status dictionary.
- ApiError mapping through handle_api_errors.
"""
from unittest.mock import patch
import pytest
from flask import Flask

from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.routes import notification_smtp_controller


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


class TestNotificationSmtpStatus:
    def test_returns_status_with_200(self, app):
        expected = {
            "configured": True,
            "required_keys": ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"],
            "optional_keys": ["NATS_SMTP_PORT", "NATS_SMTP_USERNAME", "NATS_SMTP_PASSWORD", "NATS_SMTP_STARTTLS", "NATS_SMTP_SSL"],
            "keys_present": {
                "NATS_SMTP_HOST": True,
                "NATS_SMTP_FROM_EMAIL": True,
                "NATS_SMTP_PORT": True,
            },
        }
        with patch(
            "m8flow_backend.services.external_form_notification_service."
            "ExternalFormNotificationService.check_smtp_configured",
            return_value=expected,
        ), app.test_request_context("/m8flow/notification-smtp-status"):
            response = notification_smtp_controller.notification_smtp_status()

        assert response.status_code == 200
        assert response.get_json() == expected

    def test_handles_api_error_gracefully(self, app):
        with patch(
            "m8flow_backend.services.external_form_notification_service."
            "ExternalFormNotificationService.check_smtp_configured",
            side_effect=ApiError(error_code="internal_error", message="Failed", status_code=500),
        ), app.test_request_context("/m8flow/notification-smtp-status"):
            response = notification_smtp_controller.notification_smtp_status()

        assert response.status_code == 500


class TestNotificationSmtpPermissions:
    def test_permission_registered_for_everybody_in_m8flow_yml(self):
        from pathlib import Path
        import yaml

        permissions_path = (
            Path(__file__).resolve().parents[4]
            / "src"
            / "m8flow_backend"
            / "config"
            / "permissions"
            / "m8flow.yml"
        )
        with open(permissions_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        permissions = config["permissions"]

        assert "read-notification-smtp-status" in permissions
        grant = permissions["read-notification-smtp-status"]
        assert grant["uri"] == "/m8flow/notification-smtp-status"
        assert grant["actions"] == ["read"]
        assert "everybody" in grant["groups"]

