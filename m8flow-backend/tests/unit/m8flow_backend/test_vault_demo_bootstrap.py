from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml


_BOOTSTRAP_SCRIPT = (
    Path(__file__).resolve().parents[3].parent
    / "docker"
    / "vault"
    / "demo"
    / "bootstrap_vault_demo.py"
)


def _bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap_vault_demo", _BOOTSTRAP_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vault_demo_runtime_volume_is_writable_for_bootstrap():
    compose_path = _BOOTSTRAP_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    mounts = compose["services"]["vault-demo"]["volumes"]

    assert "vault-runtime:/vault/runtime" in mounts
    assert "vault-runtime:/vault/runtime:ro" not in mounts


def test_vault_runtime_compose_ignores_legacy_token_environment():
    compose_path = _BOOTSTRAP_SCRIPT.parents[3] / "docker" / "m8flow-docker-compose.vault.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    runtime_services = (
        "m8flow-backend",
        "m8flow-celery-worker",
        "m8flow-notification-worker",
        "m8flow-nats-consumer",
    )
    token_environment = (
        "M8FLOW_VAULT_TOKEN",
        "VAULT_TOKEN",
        "M8FLOW_VAULT_TOKEN_FILE",
        "VAULT_TOKEN_FILE",
        "M8FLOW_VAULT_ROLE_ID",
        "VAULT_ROLE_ID",
        "M8FLOW_VAULT_SECRET_ID",
        "VAULT_SECRET_ID",
    )

    for service_name in runtime_services:
        environment = compose["services"][service_name]["environment"]
        assert all(environment.get(name) == "" for name in token_environment)


@pytest.mark.parametrize(
    ("environment_variable", "value"),
    [
        ("M8FLOW_VAULT_POLICY_NAME", "m8flow\" { capabilities = [\"root\"] }"),
        ("M8FLOW_VAULT_APPROLE_NAME", "../admin"),
        ("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "tenant/*"),
        ("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "tenant role"),
        ("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle/../system"),
        ("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle//nested"),
    ],
)
def test_bootstrap_rejects_unsafe_policy_identifiers_before_side_effects(
    tmp_path, monkeypatch, environment_variable, value
):
    monkeypatch.setenv(environment_variable, value)
    module = _bootstrap_module()
    state_dir = tmp_path / "admin"
    monkeypatch.setattr(module, "ADMIN_STATE", state_dir)
    monkeypatch.setattr(
        module,
        "wait_status",
        lambda: pytest.fail("Vault should not be contacted for invalid configuration"),
    )

    with pytest.raises(RuntimeError, match="Vault demo"):
        module.main()

    assert not state_dir.exists()


def test_runtime_credential_chown_failure_has_actionable_diagnostic(
    tmp_path, monkeypatch
):
    module = _bootstrap_module()
    credential_file = tmp_path / "m8flow-role-id"

    def fail_chown(*_args):
        raise PermissionError("operation not permitted")

    monkeypatch.setattr(module.os, "chown", fail_chown, raising=False)

    with pytest.raises(RuntimeError, match="UID/GID 1000") as exc_info:
        module._set_runtime_file_owner(credential_file)

    assert str(credential_file) in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_bootstrap_mints_scoped_seed_token_and_keeps_root_state_private(
    tmp_path, monkeypatch
):
    module = _bootstrap_module()
    admin_state = tmp_path / "admin"
    legacy_state = tmp_path / "legacy"
    seed_state = tmp_path / "seed"
    runtime = tmp_path / "runtime"
    provisioner = tmp_path / "provisioner"
    runtime.mkdir()
    (runtime / "runtime.env").write_text(
        "M8FLOW_VAULT_TOKEN=legacy-broker-token\n", encoding="utf-8"
    )
    (runtime / "m8flow-role-id").write_text("legacy-role-id\n", encoding="utf-8")
    (runtime / "m8flow-secret-id").write_text("provisioner-secret-id\n", encoding="utf-8")
    for directory in (admin_state, legacy_state):
        directory.mkdir()
    init_data = {"root_token": "root-only-token", "keys_base64": ["unseal-key"]}
    (legacy_state / "init.json").write_text(json.dumps(init_data), encoding="utf-8")

    monkeypatch.setattr(module, "ADMIN_STATE", admin_state)
    monkeypatch.setattr(module, "LEGACY_STATE", legacy_state)
    monkeypatch.setattr(module, "SEED_STATE", seed_state)
    monkeypatch.setattr(module, "RUNTIME", runtime)
    monkeypatch.setattr(module, "PROVISIONER", provisioner)
    monkeypatch.setattr(module, "wait_status", lambda: {"initialized": True, "sealed": False})
    monkeypatch.setattr(
        module,
        "wait_for_admin_api",
        lambda token, _path: {"kv/": {}} if token == "root-only-token" else {},
    )
    chown_calls = []
    monkeypatch.setattr(
        module.os,
        "chown",
        lambda *args: chown_calls.append(args),
        raising=False,
    )

    calls = []
    active_secret_ids = {"provisioner-secret-id"}
    minted_secret_id_calls = []

    def fake_call(method, path, *, token=None, payload=None, expected=(200,)):
        calls.append((method, path, token, payload))
        if method == "GET" and path == "sys/auth":
            return 200, {"approle/": {}}
        if method == "GET" and path.endswith("/role-id"):
            role_id = "runtime-role-id" if module.RUNTIME_ROLE in path else "provisioner-role-id"
            return 200, {"data": {"role_id": role_id}}
        if method == "POST" and path.endswith("/secret-id/lookup"):
            if payload["secret_id"] in active_secret_ids:
                return 200, {"data": {"secret_id_accessor": "active-accessor"}}
            return 400, {"errors": ["invalid secret id"]}
        if method == "POST" and path.endswith("/secret-id"):
            secret_id = "runtime-secret-id" if module.RUNTIME_ROLE in path else "provisioner-secret-id"
            active_secret_ids.add(secret_id)
            minted_secret_id_calls.append(path)
            return 200, {"data": {"secret_id": secret_id}}
        if method == "POST" and path == "auth/token/create-orphan":
            return 200, {"auth": {"client_token": "scoped-seed-token"}}
        return 204, {}

    monkeypatch.setattr(module, "call", fake_call)

    assert module.main() == 0
    # Re-running against the same Vault and volumes should repair/refresh the
    # runtime credentials without relying on the now-removed legacy init file.
    assert module.main() == 0
    assert len(minted_secret_id_calls) == 1

    assert json.loads((admin_state / "init.json").read_text(encoding="utf-8")) == init_data
    assert not (legacy_state / "init.json").exists()
    assert (seed_state / "seed-token").read_text(encoding="utf-8").strip() == (
        "scoped-seed-token"
    )
    assert {path.name for path in seed_state.iterdir()} == {"seed-token"}
    assert all(token == "root-only-token" for _method, _path, token, _payload in calls)
    assert (runtime / "runtime-role-id").read_text(encoding="utf-8").strip() == (
        "runtime-role-id"
    )
    assert not (runtime / "runtime.env").exists()
    assert not (runtime / "m8flow-role-id").exists()
    assert not (runtime / "m8flow-secret-id").exists()
    assert (runtime / "runtime-secret-id").read_text(encoding="utf-8").strip() == (
        "runtime-secret-id"
    )
    assert (provisioner / "provisioner-role-id").read_text(encoding="utf-8").strip() == (
        "provisioner-role-id"
    )
    assert (provisioner / "provisioner-secret-id").read_text(encoding="utf-8").strip() == (
        "provisioner-secret-id"
    )
    assert (runtime / "provisioner-api-token").read_text(encoding="utf-8").strip() == (
        (provisioner / "provisioner-api-token").read_text(encoding="utf-8").strip()
    )
    assert len(chown_calls) == 12

    policy_call = next(
        call for call in calls if call[1] == "sys/policies/acl/m8flow-demo-seed"
    )
    assert policy_call[3]["policy"] == (
        'path "kv/data/m8flow/tenants/m8flow/secrets/configuration-variable/*" '
        '{ capabilities = ["create", "read", "update"] }\n'
        'path "kv/metadata/m8flow/tenants/m8flow/secrets/configuration-variable/*" '
        '{ capabilities = ["delete"] }\n'
    )
    provisioner_policy_call = next(
        call for call in calls if call[1] == f"sys/policies/acl/{module.POLICY}"
    )
    assert f'sys/policy/{module.POLICY_PREFIX}-*' in provisioner_policy_call[3]["policy"]
    assert "/secret-id" not in provisioner_policy_call[3]["policy"]
    runtime_policy_call = next(
        call for call in calls if call[1] == f"sys/policies/acl/{module.RUNTIME_POLICY}"
    )
    assert f'auth/{module.APPROLE}/role/{module.ROLE_PREFIX}-*/secret-id"' in (
        runtime_policy_call[3]["policy"]
    )
    assert (
        f'path "auth/{module.APPROLE}/role/{module.ROLE_PREFIX}-*/'
        'secret-id-accessor/destroy" { capabilities = ["update"] }'
    ) in runtime_policy_call[3]["policy"]
    assert "sys/policies/acl/" not in runtime_policy_call[3]["policy"]
    token_request = next(call for call in calls if call[1] == "auth/token/create-orphan")[3]
    assert token_request == {
        "policies": ["m8flow-demo-seed"],
        "no_default_policy": True,
        "renewable": False,
        "ttl": "15m",
    }
