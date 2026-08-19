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
    tid = (
        secret.m8f_tenant_id
        if isinstance(secret.m8f_tenant_id, str) and secret.m8f_tenant_id
        else None
    )
    return {
        **secret.to_dict(),
        "username": username,
        "tenantId": secret.m8f_tenant_id,
        "tenantName": tenant_names.get(tid) if tid else None,
    }


def test_non_super_admin_delegates_to_upstream_with_profile_secrets_stripped(monkeypatch):
    """Non-super-admins get upstream's tenant-scoped listing (tenant scoping itself
    is applied elsewhere, by the tenant-scoping patch), but connector-profile
    secrets are still stripped out -- that filter applies to every caller."""
    from flask import Flask, jsonify, make_response

    calls: list[tuple[int, int]] = []

    def _fake_original_secret_list(page=1, per_page=100):
        calls.append((page, per_page))
        payload = {
            "results": [
                {"key": "db_url", "username": "alice"},
                {"key": "cnx/github/token", "username": "alice"},
            ],
            "pagination": {"count": 2, "total": 2, "pages": 1},
        }
        return make_response(jsonify(payload), 200)

    secrets_controller = types.ModuleType(
        "spiffworkflow_backend.routes.secrets_controller"
    )
    secrets_controller.secret_list = _fake_original_secret_list

    import spiffworkflow_backend.routes as routes_pkg

    monkeypatch.setattr(routes_pkg, "secrets_controller", secrets_controller, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.secrets_controller",
        secrets_controller,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.secret_model",
        types.SimpleNamespace(SecretModel=types.SimpleNamespace()),
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.user",
        types.SimpleNamespace(UserModel=types.SimpleNamespace()),
    )
    monkeypatch.setattr("m8flow_backend.tenancy.is_super_admin_request", lambda: False)

    import m8flow_backend.routes.secrets_controller_patch as patch_module

    monkeypatch.setattr(patch_module, "_PATCHED", False)
    patch_module.apply()

    app = Flask(__name__)
    with app.app_context():
        response = secrets_controller.secret_list(page=2, per_page=10)

    assert calls == [(2, 10)]
    payload = response.get_json()
    assert [r["key"] for r in payload["results"]] == ["db_url"]
    assert payload["pagination"]["count"] == 1


def test_serialize_shapes_tenant_details():
    """A secret carries username + tenantId/tenantName; a null tenant id yields null names."""
    tenant_names = {"tenant-a": "Tenant A"}
    with_tenant = _serialize(_Secret("db_url", "tenant-a"), "alice", tenant_names)
    assert with_tenant == {
        "key": "db_url",
        "username": "alice",
        "tenantId": "tenant-a",
        "tenantName": "Tenant A",
    }

    without_tenant = _serialize(_Secret("api_key", None), "bob", tenant_names)
    assert without_tenant == {
        "key": "api_key",
        "username": "bob",
        "tenantId": None,
        "tenantName": None,
    }


class _FakeExpr:
    """Stand-in for the SQLAlchemy expression `SecretModel.key.startswith(...)` produces."""

    def __init__(self, value) -> None:
        self.value = value

    def __invert__(self):
        return _FakeExpr(("not", self.value))

    def __eq__(self, other):
        return isinstance(other, _FakeExpr) and self.value == other.value

    def __repr__(self):
        return repr(self.value)


class _FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):
        return (self.name, other)

    def startswith(self, prefix):
        return _FakeExpr(("startswith", self.name, prefix))


# Matches SECRET_REF_PREFIX ("cnx") from m8flow_backend.connectors.base, which
# patched_secret_list always excludes from the listing regardless of caller.
_PROFILE_SECRET_FILTER = _FakeExpr(("not", ("startswith", "key", "cnx/")))


class _FakeSecretQuery:
    def __init__(self, items: list[tuple]) -> None:
        self.items = items
        self.filters: list[object] = []

    def order_by(self, *_args, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def add_columns(self, *_args, **_kwargs):
        return self

    def filter(self, expr):
        self.filters.append(expr)
        return self

    def paginate(self, page: int = 1, per_page: int = 100, error_out: bool = False):
        return types.SimpleNamespace(items=self.items, total=len(self.items), pages=1)


def _install_sa_secret_list(
    monkeypatch,
    items: list[tuple],
    *,
    is_super_admin: bool = True,
    tenants: list | None = None,
):
    query = _FakeSecretQuery(items)
    fake_secret_model = types.SimpleNamespace(
        SecretModel=types.SimpleNamespace(
            key=_FakeColumn("key"),
            m8f_tenant_id=_FakeColumn("m8f_tenant_id"),
            query=query,
        )
    )
    secrets_controller = types.ModuleType(
        "spiffworkflow_backend.routes.secrets_controller"
    )
    secrets_controller.secret_list = lambda page=1, per_page=100: (
        "ORIGINAL",
        page,
        per_page,
    )

    import spiffworkflow_backend.routes as routes_pkg

    monkeypatch.setattr(routes_pkg, "secrets_controller", secrets_controller, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.secrets_controller",
        secrets_controller,
    )
    monkeypatch.setitem(
        sys.modules, "spiffworkflow_backend.models.secret_model", fake_secret_model
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.user",
        types.SimpleNamespace(UserModel=types.SimpleNamespace(username="username")),
    )
    monkeypatch.setattr(
        "m8flow_backend.tenancy.is_super_admin_request", lambda: is_super_admin
    )

    class FakeTenantQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return tenants or []

    monkeypatch.setattr(
        "m8flow_backend.models.m8flow_tenant.M8flowTenantModel",
        types.SimpleNamespace(
            query=FakeTenantQuery(),
            id=types.SimpleNamespace(in_=lambda values: ("in", values)),
        ),
    )

    import m8flow_backend.routes.secrets_controller_patch as patch_module

    monkeypatch.setattr(patch_module, "_PATCHED", False)
    patch_module.apply()
    assert secrets_controller.secret_list.__name__ == "patched_secret_list"
    return secrets_controller, query


def test_super_admin_secret_list_injects_tenant_fields_and_filters(monkeypatch):
    from flask import Flask

    tenant_a = _Secret("db_url", "tenant-a")
    tenant_none = _Secret("orphan", None)
    secrets_controller, query = _install_sa_secret_list(
        monkeypatch,
        [(tenant_a, "alice"), (tenant_none, "bob")],
        tenants=[types.SimpleNamespace(id="tenant-a", name="Acme")],
    )

    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context("/secrets?tenantId=tenant-a"):
            response = secrets_controller.secret_list(page=1, per_page=50)

    assert query.filters == [_PROFILE_SECRET_FILTER, ("m8f_tenant_id", "tenant-a")]
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"] == {"count": 2, "total": 2, "pages": 1}
    assert payload["results"] == [
        {
            "key": "db_url",
            "username": "alice",
            "tenantId": "tenant-a",
            "tenantName": "Acme",
        },
        {"key": "orphan", "username": "bob", "tenantId": None, "tenantName": None},
    ]


def test_super_admin_secret_list_without_tenant_query_does_not_filter(monkeypatch):
    from flask import Flask

    secrets_controller, query = _install_sa_secret_list(
        monkeypatch,
        [(_Secret("db_url", "tenant-a"), "alice")],
    )

    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context("/secrets"):
            response = secrets_controller.secret_list()

    assert query.filters == [_PROFILE_SECRET_FILTER]
    assert response.get_json()["results"][0]["tenantId"] == "tenant-a"
    assert response.get_json()["results"][0]["tenantName"] is None


def test_super_admin_secret_list_accepts_tenant_id_query_alias(monkeypatch):
    from flask import Flask

    secrets_controller, query = _install_sa_secret_list(monkeypatch, [])

    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context("/secrets?tenant_id=tenant-b"):
            secrets_controller.secret_list()

    assert query.filters == [_PROFILE_SECRET_FILTER, ("m8f_tenant_id", "tenant-b")]
