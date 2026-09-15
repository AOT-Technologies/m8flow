from __future__ import annotations

import pytest

from m8flow_backend.secrets import crypto


def test_fernet_uses_configured_key(monkeypatch):
    monkeypatch.setenv("FLASK_SESSION_SECRET_KEY", "configured-session-secret")
    monkeypatch.delenv("M8FLOW_SECRETS_ENCRYPTION_KEY", raising=False)
    encrypted = crypto.encrypt_secret_value("hello")
    assert crypto.decrypt_secret_value(encrypted) == "hello"


def test_fernet_requires_key_outside_unit_testing(monkeypatch):
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "production")
    monkeypatch.delenv("FLASK_SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("M8FLOW_SECRETS_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="must be set"):
        crypto.encrypt_secret_value("hello")
