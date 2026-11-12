from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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


def test_bootstrap_mints_scoped_seed_token_and_keeps_root_state_private(
    tmp_path, monkeypatch
):
    module = _bootstrap_module()
    admin_state = tmp_path / "admin"
    legacy_state = tmp_path / "legacy"
    seed_state = tmp_path / "seed"
    runtime = tmp_path / "runtime"
    for directory in (admin_state, legacy_state):
        directory.mkdir()
    init_data = {"root_token": "root-only-token", "keys_base64": ["unseal-key"]}
    (legacy_state / "init.json").write_text(json.dumps(init_data), encoding="utf-8")

    monkeypatch.setattr(module, "ADMIN_STATE", admin_state)
    monkeypatch.setattr(module, "LEGACY_STATE", legacy_state)
    monkeypatch.setattr(module, "SEED_STATE", seed_state)
    monkeypatch.setattr(module, "RUNTIME", runtime)
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

    def fake_call(method, path, *, token=None, payload=None, expected=(200,)):
        calls.append((method, path, token, payload))
        if method == "GET" and path == "sys/auth":
            return 200, {"approle/": {}}
        if method == "GET" and path.endswith("/role-id"):
            return 200, {"data": {"role_id": "broker-role-id"}}
        if method == "POST" and path.endswith("/secret-id"):
            return 200, {"data": {"secret_id": "broker-secret-id"}}
        if method == "POST" and path == "auth/token/create-orphan":
            return 200, {"auth": {"client_token": "scoped-seed-token"}}
        return 204, {}

    monkeypatch.setattr(module, "call", fake_call)

    assert module.main() == 0
    # Re-running against the same Vault and volumes should repair/refresh the
    # runtime credentials without relying on the now-removed legacy init file.
    assert module.main() == 0

    assert json.loads((admin_state / "init.json").read_text(encoding="utf-8")) == init_data
    assert not (legacy_state / "init.json").exists()
    assert (seed_state / "seed-token").read_text(encoding="utf-8").strip() == (
        "scoped-seed-token"
    )
    assert {path.name for path in seed_state.iterdir()} == {"seed-token"}
    assert all(token == "root-only-token" for _method, _path, token, _payload in calls)
    assert (runtime / "m8flow-role-id").read_text(encoding="utf-8").strip() == (
        "broker-role-id"
    )
    assert (runtime / "m8flow-secret-id").read_text(encoding="utf-8").strip() == (
        "broker-secret-id"
    )
    assert len(chown_calls) == 4

    policy_call = next(
        call for call in calls if call[1] == "sys/policies/acl/m8flow-demo-seed"
    )
    assert policy_call[3]["policy"] == (
        'path "kv/data/m8flow/tenants/m8flow/secrets/configuration-variable/*" '
        '{ capabilities = ["create", "read", "update"] }\n'
        'path "kv/metadata/m8flow/tenants/m8flow/secrets/configuration-variable/*" '
        '{ capabilities = ["delete"] }\n'
    )
    token_request = next(call for call in calls if call[1] == "auth/token/create-orphan")[3]
    assert token_request == {
        "policies": ["m8flow-demo-seed"],
        "no_default_policy": True,
        "renewable": False,
        "ttl": "15m",
    }
