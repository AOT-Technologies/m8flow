from __future__ import annotations

import importlib.util
from pathlib import Path


def test_operator_cleanup_script_targets_only_requested_tenant(monkeypatch):
    script_path = (
        Path(__file__).resolve().parents[5]
        / "docker"
        / "vault"
        / "scripts"
        / "delete_tenant_vault.py"
    )
    spec = importlib.util.spec_from_file_location("delete_tenant_vault", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls = []

    def fake_api(method, path, *, missing_ok=False):
        calls.append((method, path, missing_ok))
        return None if method == "LIST" else {}

    monkeypatch.setattr(module, "_api", fake_api)
    assert module.main([str(script_path), "org-123"]) == 0

    assert calls == [
        ("LIST", "kv/metadata/m8flow/tenants/org-123/secrets", True),
        ("DELETE", "kv/metadata/m8flow/tenants/org-123/secrets", True),
        ("DELETE", "auth/approle/role/m8flow-tenant-role-org-123", True),
        ("DELETE", "sys/policy/m8flow-tenant-policy-org-123", True),
    ]


def test_operator_cleanup_recurses_prefixes_and_permanently_deletes_leaf_metadata(
    monkeypatch,
):
    script_path = (
        Path(__file__).resolve().parents[5]
        / "docker"
        / "vault"
        / "scripts"
        / "delete_tenant_vault.py"
    )
    spec = importlib.util.spec_from_file_location("delete_tenant_vault_nested", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    listings = {
        "kv/metadata/demo/tenants/org-123/secrets": {
            "data": {"keys": ["configuration-variable/", "smtp_password"]}
        },
        "kv/metadata/demo/tenants/org-123/secrets/configuration-variable": {
            "data": {"keys": ["uuid-1", "nested/"]}
        },
        "kv/metadata/demo/tenants/org-123/secrets/configuration-variable/nested": {
            "data": {"keys": ["uuid-2"]}
        },
    }
    calls = []

    def fake_api(method, path, *, missing_ok=False):
        calls.append((method, path, missing_ok))
        if method == "LIST":
            return listings.get(path)
        return {}

    monkeypatch.setattr(module, "_api", fake_api)
    module._delete_kv_tree("kv", "demo/tenants/org-123/secrets")

    assert calls == [
        ("LIST", "kv/metadata/demo/tenants/org-123/secrets", True),
        (
            "LIST",
            "kv/metadata/demo/tenants/org-123/secrets/configuration-variable",
            True,
        ),
        (
            "DELETE",
            "kv/metadata/demo/tenants/org-123/secrets/configuration-variable/uuid-1",
            True,
        ),
        (
            "LIST",
            "kv/metadata/demo/tenants/org-123/secrets/configuration-variable/nested",
            True,
        ),
        (
            "DELETE",
            "kv/metadata/demo/tenants/org-123/secrets/configuration-variable/nested/uuid-2",
            True,
        ),
        (
            "DELETE",
            "kv/metadata/demo/tenants/org-123/secrets/smtp_password",
            True,
        ),
    ]
