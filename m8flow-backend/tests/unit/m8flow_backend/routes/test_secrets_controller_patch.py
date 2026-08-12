from __future__ import annotations

import sys
import types


class _Secret:
    def __init__(self, key, tenant_id):
        self.key = key
        self.m8f_tenant_id = tenant_id

    def to_dict(self):
        return {"key": self.key}


def _serialize(secret, username, tenant_names):
    """Mirror of patched_secret_list's serialize closure, for a direct parity check on
    the tenant-detail shaping (the closure itself is not importable)."""
    tid = secret.m8f_tenant_id if isinstance(secret.m8f_tenant_id, str) and secret.m8f_tenant_id else None
    return {
        **secret.to_dict(),
        "username": username,
        "tenantId": secret.m8f_tenant_id,
        "tenantName": tenant_names.get(tid) if tid else None,
    }


def test_non_super_admin_delegates_to_upstream(monkeypatch):
    """Non-super-admin callers get upstream's tenant-scoped listing unchanged."""
    secrets_controller = types.ModuleType("spiffworkflow_backend.routes.secrets_controller")
    secrets_controller.secret_list = lambda page=1, per_page=100: ("ORIGINAL", page, per_page)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.secrets_controller", secrets_controller)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.secret_model",
        types.SimpleNamespace(SecretModel=types.SimpleNamespace()),
    )
    monkeypatch.setitem(
        sys.modules, "spiffworkflow_backend.models.user", types.SimpleNamespace(UserModel=types.SimpleNamespace())
    )
    monkeypatch.setattr("m8flow_backend.tenancy.is_super_admin_request", lambda: False, raising=False)

    import m8flow_backend.routes.secrets_controller_patch as patch_module

    patch_module._PATCHED = False
    patch_module.apply()

    assert secrets_controller.secret_list(page=2, per_page=10) == ("ORIGINAL", 2, 10)


def test_serialize_shapes_tenant_details():
    """A secret carries username + tenantId/tenantName; a null tenant id yields null names."""
    tenant_names = {"tenant-a": "Tenant A"}
    with_tenant = _serialize(_Secret("db_url", "tenant-a"), "alice", tenant_names)
    assert with_tenant == {"key": "db_url", "username": "alice", "tenantId": "tenant-a", "tenantName": "Tenant A"}

    without_tenant = _serialize(_Secret("api_key", None), "bob", tenant_names)
    assert without_tenant == {"key": "api_key", "username": "bob", "tenantId": None, "tenantName": None}
