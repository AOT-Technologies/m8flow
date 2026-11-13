from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib import error

import pytest
import yaml


_SEED_SCRIPT = (
    Path(__file__).resolve().parents[3]
    .parent
    / "docker"
    / "vault"
    / "demo"
    / "seed_vault_demo.py"
)
_COMPOSE_FILE = _SEED_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.yml"
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
    monkeypatch.setattr(module, "wait_for_backend_health", lambda: None)
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
            if statement.startswith("SELECT id::text FROM m8flow_tenant"):
                return Result(("m8flow",))
            if statement.startswith("SELECT id, is_sensitive, provider_key"):
                return Result(None)
            return Result()

        def transaction(self):
            return self

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    connection = Connection()
    connect_calls = []

    def connect(*_args, **_kwargs):
        connect_calls.append(True)
        return connection

    monkeypatch.setattr(module.psycopg, "connect", connect)
    vault_calls = []

    def vault_call(method, path, token, payload=None, expected=(200,)):
        assert token == "scoped-seed-token"
        vault_calls.append((method, path, payload))
        return (404 if method == "GET" else 200), {}

    monkeypatch.setattr(module, "vault_call", vault_call)

    assert module.seed() == (2, 0)
    assert len(connect_calls) == 1

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


def _seed_existing_variable(
    tmp_path, monkeypatch, *, existing_sensitive, new_sensitive, overwrite
):
    module = _seed_module()
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    variables:\n      SMTP_SETTING:\n"
        f"        value: {'new-secret' if new_sensitive else 'new-public'}\n"
        f"        sensitive: {str(new_sensitive).lower()}\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "seed-token").write_text("scoped-seed-token\n", encoding="utf-8")
    monkeypatch.setattr(module, "SECRETS", secrets_file)
    monkeypatch.setattr(module, "STATE", state_dir)
    monkeypatch.setattr(module, "OVERWRITE", overwrite)
    monkeypatch.setattr(module, "wait_for_backend_health", lambda: None)
    monkeypatch.setenv(
        "M8FLOW_BACKEND_DATABASE_URI", "postgresql+psycopg://user:pass@db/test"
    )

    variable_id = "b85e1f1f-e51d-4b23-a63d-e85c64490001"
    old_provider_key = variable_id if existing_sensitive else None
    database_statements = []
    events = []

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
        def __init__(self):
            self.named_value_updated = False

        def cursor(self):
            return Cursor()

        def execute(self, statement, parameters=None):
            database_statements.append((statement, parameters))
            if statement.startswith("SELECT id::text FROM m8flow_tenant"):
                return Result(("m8flow",))
            if statement.startswith("SELECT id, is_sensitive, provider_key"):
                return Result((variable_id, existing_sensitive, old_provider_key))
            if statement.startswith("UPDATE m8flow_named_value"):
                self.named_value_updated = True
            return Result()

        def transaction(self):
            return Transaction(self)

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Transaction:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, exc_type, *_args):
            if exc_type is None and self.connection.named_value_updated:
                events.append("database_commit")
                self.connection.named_value_updated = False
            return False

    connection = Connection()
    connect_calls = []

    def connect(*_args, **_kwargs):
        connect_calls.append(True)
        return connection

    monkeypatch.setattr(module.psycopg, "connect", connect)
    vault_calls = []

    def vault_call(method, path, token, payload=None, expected=(200,)):
        assert token == "scoped-seed-token"
        vault_calls.append((method, path, payload))
        if method == "GET":
            return 404, {}
        if method == "DELETE":
            events.append("vault_delete")
        return 204, {}

    monkeypatch.setattr(module, "vault_call", vault_call)
    result = module.seed()
    assert len(connect_calls) == 1
    return result, database_statements, vault_calls, events, variable_id


def test_demo_seed_preserves_existing_values_when_overwrite_is_disabled(
    tmp_path, monkeypatch
):
    result, statements, vault_calls, _events, _variable_id = _seed_existing_variable(
        tmp_path,
        monkeypatch,
        existing_sensitive=False,
        new_sensitive=True,
        overwrite=False,
    )

    assert result == (0, 1)
    assert not any(statement.startswith("UPDATE m8flow_named_value") for statement, _ in statements)
    assert not any(method in {"POST", "DELETE"} for method, _path, _payload in vault_calls)


def test_demo_seed_overwrite_plain_value_with_sensitive_vault_value(
    tmp_path, monkeypatch
):
    result, statements, vault_calls, _events, variable_id = _seed_existing_variable(
        tmp_path,
        monkeypatch,
        existing_sensitive=False,
        new_sensitive=True,
        overwrite=True,
    )

    assert result == (1, 0)
    update = next(
        parameters
        for statement, parameters in statements
        if statement.startswith("UPDATE m8flow_named_value")
    )
    assert update[2] is True
    assert update[3] is None
    assert update[4] == variable_id
    assert ("POST", f"kv/data/m8flow/tenants/m8flow/secrets/configuration-variable/{variable_id}",
            {"data": {"value": "new-secret"}}) in vault_calls


def test_demo_seed_overwrite_sensitive_with_plain_value_deletes_vault_after_commit(
    tmp_path, monkeypatch
):
    result, statements, vault_calls, events, variable_id = _seed_existing_variable(
        tmp_path,
        monkeypatch,
        existing_sensitive=True,
        new_sensitive=False,
        overwrite=True,
    )

    assert result == (1, 0)
    update = next(
        parameters
        for statement, parameters in statements
        if statement.startswith("UPDATE m8flow_named_value")
    )
    assert update[2] is False
    assert update[3].obj == "new-public"
    assert update[4] is None
    assert vault_calls == [
        (
            "DELETE",
            f"kv/metadata/m8flow/tenants/m8flow/secrets/configuration-variable/{variable_id}",
            None,
        )
    ]
    assert events == ["database_commit", "vault_delete"]


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


def test_backend_health_wait_retries_until_healthy(monkeypatch, capsys):
    module = _seed_module()

    class HealthyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    responses = [error.URLError("not ready"), HealthyResponse()]
    calls = []

    def urlopen(url, *, timeout):
        calls.append((url, timeout))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(module.request, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_POLL_SECONDS", "0.01")

    module.wait_for_backend_health()

    assert len(calls) == 2
    assert "backend is healthy" in capsys.readouterr().out


def test_backend_health_wait_times_out_with_actionable_diagnostics(monkeypatch):
    module = _seed_module()
    monotonic_values = iter([0.0, 2.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        module.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error.URLError("offline")),
    )
    monkeypatch.setenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_POLL_SECONDS", "0.01")

    with pytest.raises(RuntimeError, match="Timed out waiting for backend health") as exc_info:
        module.wait_for_backend_health()

    assert "last check: URLError" in str(exc_info.value)
    assert "Check the m8flow-backend healthcheck and container logs" in str(exc_info.value)


def test_compose_keeps_backend_independent_and_seeds_after_health():
    compose = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
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
    assert vault_seed["depends_on"]["m8flow-backend"]["condition"] == "service_started"
    assert vault_seed["environment"]["M8FLOW_VAULT_DEMO_BACKEND_HEALTH_TIMEOUT_SECONDS"] == "600"
    assert backend["healthcheck"]
    healthcheck_command = " ".join(backend["healthcheck"]["test"])
    assert "200 <= status < 300" in healthcheck_command
    assert backend["healthcheck"]["start_period"] == "300s"
    assert backend["healthcheck"]["retries"] == 12
    assert "vault-demo" not in backend["depends_on"]
    assert vault_seed["entrypoint"][-1].endswith("/seed_vault_demo.py")
    demo_mounts = set(vault_demo["volumes"])
    seed_mounts = set(vault_seed["volumes"])
    assert "vault-admin-state:/vault/admin" in demo_mounts
    assert "vault-demo-state:/vault/legacy-demo" in demo_mounts
    assert "vault-seed-state:/vault/demo" in demo_mounts
    assert "vault-seed-state:/vault/demo:ro" in seed_mounts
    assert not any("vault-admin-state" in mount for mount in seed_mounts)
    assert not any("vault-demo-state" in mount for mount in seed_mounts)


def test_vault_uses_pinned_image_entrypoint_for_privilege_drop_and_storage():
    compose = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
    vault = compose["services"]["vault"]
    vault_config = _COMPOSE_FILE.parent / "vault" / "config" / "vault.hcl"

    assert vault["image"] == "hashicorp/vault:1.18.5"
    assert "entrypoint" not in vault
    assert vault["command"] == ["server"]
    assert not any("su-exec" in str(value) for value in vault.values())
    assert "vault-data:/vault/file" in vault["volumes"]
    assert 'path    = "/vault/file"' in vault_config.read_text(encoding="utf-8")


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
