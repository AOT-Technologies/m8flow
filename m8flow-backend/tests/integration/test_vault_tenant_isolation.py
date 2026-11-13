"""Opt-in live-Vault tests for tenant policy isolation and first-use races.

Set ``M8FLOW_TEST_VAULT_ADDR`` and ``M8FLOW_TEST_VAULT_TOKEN`` to an operator
credential for a disposable test Vault. Tests create uniquely prefixed
AppRoles, policies, and KV documents, then remove only those resources.
"""

from __future__ import annotations

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from m8flow_backend.secrets.http import HttpVault, VaultTransportError
from m8flow_backend.secrets.paths import secret_path, secret_root
from m8flow_backend.secrets.provisioning import (
    _tenant_policy,
    reconcile_tenant_identity,
    tenant_policy_name,
    tenant_role_name,
)


@pytest.fixture
def live_vault(monkeypatch):
    address = os.getenv("M8FLOW_TEST_VAULT_ADDR", "").strip()
    token = os.getenv("M8FLOW_TEST_VAULT_TOKEN", "").strip()
    if not address or not token:
        pytest.skip("Set M8FLOW_TEST_VAULT_ADDR and M8FLOW_TEST_VAULT_TOKEN for live Vault tests.")

    mount = os.getenv("M8FLOW_TEST_VAULT_KV_MOUNT", "kv").strip("/")
    approle_mount = os.getenv("M8FLOW_TEST_VAULT_APPROLE_MOUNT", "approle").strip("/")
    prefix = f"m8flow-it-{uuid4().hex[:12]}"
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", mount)
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow-it")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", approle_mount)
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", f"{prefix}-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", f"{prefix}-role")

    admin = HttpVault(
        addr=address,
        token=token,
        namespace=os.getenv("M8FLOW_TEST_VAULT_NAMESPACE"),
        mount=mount,
        approle_mount=approle_mount,
        verify=os.getenv("M8FLOW_TEST_VAULT_SKIP_VERIFY", "false").lower() != "true",
    )
    context = SimpleNamespace(
        admin=admin,
        mount=mount,
        approle_mount=approle_mount,
        address=address,
        token=token,
        namespace=os.getenv("M8FLOW_TEST_VAULT_NAMESPACE"),
        verify=os.getenv("M8FLOW_TEST_VAULT_SKIP_VERIFY", "false").lower() != "true",
        tenant_ids=[],
    )
    yield context

    # Test-only identities use unique prefixes; remove their documents, roles,
    # and policies even if an assertion fails.
    for tenant_id in context.tenant_ids:
        try:
            admin.delete_tree(secret_root(tenant_id))
        except Exception:
            pass
        role_name = tenant_role_name(tenant_id)
        policy_name = tenant_policy_name(tenant_id)
        for path in (
            f"auth/{approle_mount}/role/{role_name}",
            f"sys/policy/{policy_name}",
        ):
            try:
                admin._json("DELETE", f"{address.rstrip('/')}/v1/{path}", missing_ok=True)
            except Exception:
                pass


def _new_tenant(live_vault) -> str:
    tenant_id = f"tenant-{uuid4().hex}"
    live_vault.tenant_ids.append(tenant_id)
    return tenant_id


def test_live_vault_tenant_tokens_cannot_access_another_tenants_secrets(live_vault):
    admin = live_vault.admin
    tenant_a = _new_tenant(live_vault)
    tenant_b = _new_tenant(live_vault)
    reconcile_tenant_identity(tenant_a, control=admin)
    reconcile_tenant_identity(tenant_b, control=admin)
    store_a = admin.store_for_tenant(tenant_a, role_name=tenant_role_name(tenant_a))
    store_b = admin.store_for_tenant(tenant_b, role_name=tenant_role_name(tenant_b))
    path_a = secret_path(tenant_a, "isolation_probe")
    path_b = secret_path(tenant_b, "isolation_probe")

    store_a.put_document(path_a, {"value": "tenant-a-secret"})
    store_b.put_document(path_b, {"value": "tenant-b-secret"})
    assert store_a.get_document(path_a) == {"value": "tenant-a-secret"}
    assert store_b.get_document(path_b) == {"value": "tenant-b-secret"}

    for caller, target_tenant, target_path in (
        (store_a, tenant_b, path_b),
        (store_b, tenant_a, path_a),
    ):
        with pytest.raises(VaultTransportError):
            caller.get_document(target_path)
        with pytest.raises(VaultTransportError):
            caller.list_names(secret_root(target_tenant))
        with pytest.raises(VaultTransportError):
            caller.put_document(target_path, {"value": "cross-tenant-overwrite"})
        with pytest.raises(VaultTransportError):
            caller.delete_document(target_path)

    assert store_a.get_document(path_a) == {"value": "tenant-a-secret"}
    assert store_b.get_document(path_b) == {"value": "tenant-b-secret"}


def test_live_vault_concurrent_first_use_and_reconciliation_survive_client_restart(
    live_vault,
):
    admin = live_vault.admin
    approle_mount = live_vault.approle_mount
    tenant_id = _new_tenant(live_vault)

    # Model two app instances starting at once for a tenant that has never
    # accessed Vault. Each call may observe the role/policy as absent.
    with ThreadPoolExecutor(max_workers=2) as executor:
        identities = list(
            executor.map(
                lambda _index: reconcile_tenant_identity(tenant_id, control=admin),
                range(2),
            )
        )
    assert identities[0].role_id == identities[1].role_id

    role_name = tenant_role_name(tenant_id)
    policy_name = tenant_policy_name(tenant_id)
    # Use a fresh HTTP client, as after a backend process restart, to verify
    # the persisted role/policy are sufficient for the next tenant login.
    restarted_client = HttpVault(
        addr=live_vault.address,
        token=live_vault.token,
        namespace=live_vault.namespace,
        mount=live_vault.mount,
        approle_mount=approle_mount,
        verify=live_vault.verify,
    )
    identity = reconcile_tenant_identity(tenant_id, control=restarted_client)
    role = restarted_client.read_approle(role_name, mount=approle_mount)
    assert identity.role_id == identities[0].role_id
    assert restarted_client.read_policy(policy_name) == _tenant_policy(tenant_id)
    assert role["data"]["token_policies"] == [policy_name]

    tenant_store = restarted_client.store_for_tenant(tenant_id, role_name=role_name)
    probe = secret_path(tenant_id, "restart_probe")
    tenant_store.put_document(probe, {"ready": "yes"})
    assert tenant_store.get_document(probe) == {"ready": "yes"}


def test_live_vault_operator_cleanup_purges_nested_secret_versions_and_identity(
    live_vault, monkeypatch
):
    tenant_id = _new_tenant(live_vault)
    secret_tree = f"m8flow-it/tenants/{tenant_id}/secrets"
    versioned_leaf = f"{secret_tree}/configuration-variable/{uuid4()}"
    nested_leaf = f"{secret_tree}/connector-configuration/{uuid4()}/smtp_password"
    role_name = tenant_role_name(tenant_id)
    policy_name = tenant_policy_name(tenant_id)
    live_vault.admin.write_policy(policy_name, _tenant_policy(tenant_id))
    live_vault.admin.write_approle(
        role_name, mount=live_vault.approle_mount, token_policies=[policy_name]
    )
    live_vault.admin.put_document(versioned_leaf, {"value": "old-version"})
    live_vault.admin.put_document(versioned_leaf, {"value": "current-version"})
    live_vault.admin.put_document(nested_leaf, {"value": "nested-secret"})

    script_path = (
        Path(__file__).resolve().parents[3]
        / "docker"
        / "vault"
        / "scripts"
        / "delete_tenant_vault.py"
    )
    spec = importlib.util.spec_from_file_location("delete_tenant_vault_live", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setenv("M8FLOW_VAULT_ADDR", live_vault.address)
    monkeypatch.setenv("M8FLOW_VAULT_OPERATOR_TOKEN", live_vault.token)
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", live_vault.mount)
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", live_vault.approle_mount)
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow-it")
    monkeypatch.setenv(
        "M8FLOW_VAULT_TENANT_ROLE_PREFIX", os.environ["M8FLOW_VAULT_TENANT_ROLE_PREFIX"]
    )
    monkeypatch.setenv(
        "M8FLOW_VAULT_TENANT_POLICY_PREFIX", os.environ["M8FLOW_VAULT_TENANT_POLICY_PREFIX"]
    )
    if live_vault.namespace:
        monkeypatch.setenv("M8FLOW_VAULT_NAMESPACE", live_vault.namespace)

    # Keep the cleanup script's path traversal under test while using the
    # fixture's configured HTTP client (including namespace/TLS settings) for
    # real Vault IO.
    monkeypatch.setattr(
        module,
        "_api",
        lambda method, path, *, missing_ok=False: live_vault.admin._json(
            method,
            f"{live_vault.address.rstrip('/')}/v1/{path}",
            missing_ok=missing_ok,
        ),
    )
    assert module.main([str(script_path), tenant_id]) == 0

    assert live_vault.admin.get_document(versioned_leaf) is None
    assert live_vault.admin.get_document(nested_leaf) is None
    historical_version = live_vault.admin._json(
        "GET",
        f"{live_vault.address.rstrip('/')}/v1/{live_vault.mount}/data/{versioned_leaf}?version=1",
        missing_ok=True,
    )
    assert historical_version is None
    assert live_vault.admin.read_approle(role_name, mount=live_vault.approle_mount) is None
    assert live_vault.admin.read_policy(policy_name) is None
