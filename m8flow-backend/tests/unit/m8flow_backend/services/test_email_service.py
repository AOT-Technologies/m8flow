"""Unit tests for the minimal SMTP email sender (dev-mode fallback + real send path)."""
# ruff: noqa: E402
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import email_service


def _settings(**overrides):
    base = {
        "host": None,
        "port": 587,
        "username": None,
        "password": None,
        "from_address": "no-reply@m8flow.local",
        "use_tls": True,
    }
    base.update(overrides)
    return base


class TestSmtpIsConfigured:
    def test_false_without_host(self, monkeypatch):
        monkeypatch.setattr(email_service, "smtp_settings", lambda: _settings(host=None))
        assert email_service.smtp_is_configured() is False

    def test_true_with_host(self, monkeypatch):
        monkeypatch.setattr(email_service, "smtp_settings", lambda: _settings(host="smtp.example.com"))
        assert email_service.smtp_is_configured() is True


class TestSendEmail:
    def test_dev_mode_returns_false_and_does_not_send(self, monkeypatch):
        monkeypatch.setattr(email_service, "smtp_settings", lambda: _settings(host=None))
        # If SMTP were touched in dev mode this would explode.
        monkeypatch.setattr(
            email_service.smtplib,
            "SMTP",
            MagicMock(side_effect=AssertionError("SMTP should not be used in dev mode")),
        )
        result = email_service.send_email("user@example.com", "Subject", "<p>hi</p>", text_body="hi")
        assert result is False

    def test_smtp_path_logs_in_and_sends(self, monkeypatch):
        monkeypatch.setattr(
            email_service,
            "smtp_settings",
            lambda: _settings(
                host="smtp.example.com",
                port=587,
                username="mailer",
                password="secret",
                use_tls=True,
            ),
        )
        server = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = server
        smtp_factory = MagicMock(return_value=smtp_cm)
        monkeypatch.setattr(email_service.smtplib, "SMTP", smtp_factory)

        result = email_service.send_email(
            "user@example.com", "Subject", "<p>hi</p>", text_body="hi"
        )

        assert result is True
        smtp_factory.assert_called_once_with("smtp.example.com", 587, timeout=30)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("mailer", "secret")
        server.send_message.assert_called_once()

    def test_smtp_path_skips_tls_and_login_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            email_service,
            "smtp_settings",
            lambda: _settings(host="smtp.example.com", username=None, use_tls=False),
        )
        server = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = server
        monkeypatch.setattr(email_service.smtplib, "SMTP", MagicMock(return_value=smtp_cm))

        result = email_service.send_email("user@example.com", "Subject", "<p>hi</p>")

        assert result is True
        server.starttls.assert_not_called()
        server.login.assert_not_called()
        server.send_message.assert_called_once()

    def test_reraises_on_smtp_failure(self, monkeypatch):
        monkeypatch.setattr(
            email_service, "smtp_settings", lambda: _settings(host="smtp.example.com", use_tls=False)
        )
        server = MagicMock()
        server.send_message.side_effect = OSError("connection reset")
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = server
        monkeypatch.setattr(email_service.smtplib, "SMTP", MagicMock(return_value=smtp_cm))

        with pytest.raises(OSError):
            email_service.send_email("user@example.com", "Subject", "<p>hi</p>")
