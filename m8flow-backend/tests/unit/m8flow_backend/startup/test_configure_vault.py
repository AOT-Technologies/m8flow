from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path

import pytest
from flask import Flask

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (repo_root, extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services.vault_client import VaultOperationError
from m8flow_backend.startup.config import configure_vault


def test_configure_vault_defaults_to_legacy_when_disabled(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.delenv("M8FLOW_VAULT_ENABLED", raising=False)

    configure_vault(app)

    assert app.config["M8FLOW_VAULT_ENABLED"] is False
    assert app.config["M8FLOW_SECRET_BACKEND_KIND"] == "legacy"
    assert app.config["M8FLOW_VAULT_AVAILABLE"] is False


def test_configure_vault_raises_when_enabled_but_missing_required_config(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.delenv("M8FLOW_VAULT_ADDR", raising=False)
    monkeypatch.delenv("M8FLOW_VAULT_TOKEN", raising=False)
    monkeypatch.delenv("M8FLOW_VAULT_ROLE_ID", raising=False)
    monkeypatch.delenv("M8FLOW_VAULT_SECRET_ID", raising=False)

    with pytest.raises(RuntimeError, match="not fully configured"):
        configure_vault(app)


def test_configure_vault_raises_when_enabled_and_vault_is_not_ready(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("M8FLOW_VAULT_TOKEN", "token")
    monkeypatch.setattr(
        "m8flow_backend.services.vault_client.VaultClient.assert_startup_ready",
        lambda self: (_ for _ in ()).throw(VaultOperationError("Vault is sealed.")),
    )

    with pytest.raises(VaultOperationError, match="sealed"):
        configure_vault(app)


def test_configure_vault_enables_vault_backend_when_ready(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("M8FLOW_VAULT_TOKEN", "token")
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setattr(
        "m8flow_backend.services.vault_client.VaultClient.assert_startup_ready",
        lambda self: None,
    )

    configure_vault(app)

    assert app.config["M8FLOW_VAULT_ENABLED"] is True
    assert app.config["M8FLOW_SECRET_BACKEND_KIND"] == "vault"
    assert app.config["M8FLOW_VAULT_AVAILABLE"] is True


def test_configure_vault_enables_vault_backend_with_approle(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.example.com")
    monkeypatch.delenv("M8FLOW_VAULT_TOKEN", raising=False)
    monkeypatch.setenv("M8FLOW_VAULT_ROLE_ID", "role-123")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_ID", "secret-456")
    monkeypatch.setattr(
        "m8flow_backend.services.vault_client.VaultClient.assert_startup_ready",
        lambda self: None,
    )

    configure_vault(app)

    assert app.config["M8FLOW_VAULT_ENABLED"] is True
    assert app.config["M8FLOW_SECRET_BACKEND_KIND"] == "vault"
    assert app.config["M8FLOW_VAULT_AVAILABLE"] is True
