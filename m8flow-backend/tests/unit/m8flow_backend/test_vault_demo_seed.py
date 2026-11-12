from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml
import pytest


_SEED_SCRIPT = (
    Path(__file__).resolve().parents[3]
    .parent
    / "docker"
    / "vault"
    / "demo"
    / "seed_vault_demo.py"
)
_COMPOSE_FILE = _SEED_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.yml"
_VAULT_DEMO_COMPOSE_FILE = (
    _SEED_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.vault-demo.yml"
)
_VAULT_COMPOSE_FILE = _SEED_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.vault.yml"


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_vault_demo", _SEED_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_demo_seed_log_does_not_reveal_configured_file_path(
    tmp_path, monkeypatch, capsys
):
    module = _seed_module()
    missing_path = tmp_path / "private-credential-seed.yml"
    monkeypatch.setattr(module, "SECRETS", missing_path)
    monkeypatch.setattr(
        module,
        "tenant_id_from_database",
        lambda: (_ for _ in ()).throw(AssertionError("seeding should stop before database access")),
    )

    assert module.seed() == (0, 0)
    output = capsys.readouterr().out
    assert "no local seed file found" in output
    assert str(missing_path) not in output
    assert "private-credential-seed" not in output


def test_demo_seed_stores_sensitive_value_only_in_vault_and_plain_value_in_database(
    tmp_path, monkeypatch
):
    module = _seed_module()
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        """tenants:
  m8flow:
    variables:
      SMTP_HOST:
        value: smtp.example.test
        sensitive: false
      SMTP_PASSWORD:
        value: sentinel-sensitive-password
        sensitive: true
""",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "seed-token").write_text("scoped-seed-token\n", encoding="utf-8")
    monkeypatch.setattr(module, "SECRETS", secrets_file)
    monkeypatch.setattr(module, "STATE", state_dir)
    monkeypatch.setattr(module, "OVERWRITE", False)
    monkeypatch.setenv(
        "M8FLOW_BACKEND_DATABASE_URI", "postgresql+psycopg://user:pass@db/test"
    )

    database_statements = []

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Cursor:
        def execute(self, _statement, _parameters=None):
            return None

        def fetchone(self):
            return ("m8flow",)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def execute(self, statement, parameters=None):
            database_statements.append((statement, parameters))
            if statement.startswith("SELECT id, is_sensitive"):
                return Result(None)
            return Result()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(module.psycopg, "connect", lambda *_args, **_kwargs: Connection())
    vault_calls = []

    def vault_call(method, path, token, payload=None, expected=(200,)):
        assert token == "scoped-seed-token"
        vault_calls.append((method, path, payload))
        return (404 if method == "GET" else 200), {}

    monkeypatch.setattr(module, "vault_call", vault_call)

    assert module.seed() == (2, 0)

    named_value_inserts = [
        (statement, parameters)
        for statement, parameters in database_statements
        if statement.startswith("INSERT INTO m8flow_named_value")
    ]
    by_name = {parameters[2]: parameters for _, parameters in named_value_inserts}
    assert by_name["SMTP_HOST"][4] is False
    assert by_name["SMTP_HOST"][5].obj == "smtp.example.test"
    assert by_name["SMTP_HOST"][6] is None
    assert by_name["SMTP_PASSWORD"][4] is True
    assert by_name["SMTP_PASSWORD"][5] is None
    password_provider_key = by_name["SMTP_PASSWORD"][6]
    assert len(password_provider_key) == 36
    assert "sentinel-sensitive-password" not in repr(named_value_inserts)

    vault_posts = [call for call in vault_calls if call[0] == "POST"]
    assert len(vault_posts) == 1
    method, path, payload = vault_posts[0]
    assert method == "POST"
    assert path.endswith(f"configuration-variable/{password_provider_key}")
    assert payload == {"data": {"value": "sentinel-sensitive-password"}}


def test_seeder_does_not_fall_back_to_legacy_root_token(tmp_path, monkeypatch):
    module = _seed_module()
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    variables:\n      SMTP_HOST:\n"
        "        value: smtp.example.test\n        sensitive: false\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "init.json").write_text(
        json.dumps({"root_token": "must-not-be-used"}), encoding="utf-8"
    )
    monkeypatch.setattr(module, "SECRETS", secrets_file)
    monkeypatch.setattr(module, "STATE", state_dir)

    with pytest.raises(RuntimeError, match="Scoped Vault demo-seed credential is missing"):
        module.seed()


def test_compose_waits_for_vault_bootstrap_and_backend_before_seeding():
    compose = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
    vault_demo_compose = yaml.safe_load(
        _VAULT_DEMO_COMPOSE_FILE.read_text(encoding="utf-8")
    )
    services = compose["services"]
    vault_demo = services["vault-demo"]
    vault_seed = services["vault-seed"]
    backend = services["m8flow-backend"]

    assert "vault-demo" in vault_demo["profiles"]
    assert vault_demo["depends_on"]["vault"]["condition"] == "service_healthy"
    assert "vault-demo" in vault_seed["profiles"]
    assert vault_seed["depends_on"]["vault-demo"]["condition"] == (
        "service_completed_successfully"
    )
    assert vault_seed["depends_on"]["m8flow-backend"]["condition"] == "service_healthy"
    assert backend["healthcheck"]
    assert "vault-demo" not in backend["depends_on"]
    assert (
        vault_demo_compose["services"]["m8flow-backend"]["depends_on"]["vault-demo"][
            "condition"
        ]
        == "service_completed_successfully"
    )
    assert vault_seed["entrypoint"][-1].endswith("/seed_vault_demo.py")
    demo_mounts = set(vault_demo["volumes"])
    seed_mounts = set(vault_seed["volumes"])
    assert "vault-admin-state:/vault/admin" in demo_mounts
    assert "vault-demo-state:/vault/legacy-demo" in demo_mounts
    assert "vault-seed-state:/vault/demo" in demo_mounts
    assert "vault-seed-state:/vault/demo:ro" in seed_mounts
    assert not any("vault-admin-state" in mount for mount in seed_mounts)
    assert not any("vault-demo-state" in mount for mount in seed_mounts)


def test_base_compose_does_not_select_vault_but_local_vault_override_does():
    compose = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
    vault_compose = yaml.safe_load(_VAULT_COMPOSE_FILE.read_text(encoding="utf-8"))

    for service_name in (
        "m8flow-backend",
        "m8flow-celery-worker",
        "m8flow-notification-worker",
        "m8flow-nats-consumer",
    ):
        base_environment = compose["services"][service_name]["environment"]
        assert base_environment["M8FLOW_VAULT_ENABLED"] == "false"
        assert "M8FLOW_VAULT_ADDR" not in base_environment
        assert "M8FLOW_SECRET_BACKEND_KIND" not in base_environment

        vault_environment = vault_compose["services"][service_name]["environment"]
        assert vault_environment["M8FLOW_VAULT_ENABLED"] == "true"
        assert vault_environment["M8FLOW_SECRET_BACKEND_KIND"] == "vault"
        assert vault_environment["M8FLOW_VAULT_ADDR"].endswith("http://vault:8200}")
