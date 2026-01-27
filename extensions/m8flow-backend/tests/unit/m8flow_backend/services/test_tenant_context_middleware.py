# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_context_middleware.py
import pytest
from flask import Flask, g

from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SECRET_KEY"] = "test-secret"
    db.init_app(app)
    app.add_url_rule("/test", "test_endpoint", lambda: "ok")
    return app


def _seed_tenants() -> None:
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    db.session.add(M8flowTenantModel(id="default", name="Default"))
    db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
    db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
    db.session.commit()


def test_resolves_tenant_from_jwt_claim() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-b"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            resolve_request_tenant()
            assert g.m8flow_tenant_id == "tenant-b"


def test_missing_tenant_raises_by_default() -> None:
    import os

    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        with app.test_request_context("/test"):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant()
            assert exc.value.error_code == "tenant_required"


def test_missing_tenant_defaults_when_allowed() -> None:
    import os

    os.environ["M8FLOW_ALLOW_MISSING_TENANT_CONTEXT"] = "true"

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        with app.test_request_context("/test"):
            resolve_request_tenant()
            assert g.m8flow_tenant_id == "default"

    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)



def test_invalid_tenant_raises() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-missing"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant()
            assert exc.value.error_code == "invalid_tenant"


def test_tenant_override_forbidden() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-b"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            g.m8flow_tenant_id = "tenant-a"
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant()
            assert exc.value.error_code == "tenant_override_forbidden"


def test_tenant_context_propagates_to_queries(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")

    # Import tenant_scoping_patch so its SQLAlchemy event listeners register.
    from m8flow_backend.services import tenant_scoping_patch  # noqa: F401
    from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped
    from m8flow_backend.tenancy import reset_context_tenant_id, set_context_tenant_id
    tenant_scoping_patch.apply()
    
    class TestItem(M8fTenantScopedMixin, TenantScoped, db.Model):
        __tablename__ = "m8f_test_item"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)

    app = _make_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        _seed_tenants()
        
        token_a = set_context_tenant_id("tenant-a")
        try:
            with app.test_request_context("/test"):
                resolve_request_tenant()
                db.session.add(TestItem(name="A"))
                db.session.commit()
        finally:
            reset_context_tenant_id(token_a)

        token_b = set_context_tenant_id("tenant-b")
        try:
            with app.test_request_context("/test"):
                resolve_request_tenant()
                db.session.add(TestItem(name="B"))
                db.session.commit()
        finally:
            reset_context_tenant_id(token_b)

        token_a2 = set_context_tenant_id("tenant-a")
        try:
            with app.test_request_context("/test"):
                resolve_request_tenant()
                rows = TestItem.query.order_by(TestItem.name).all()
                assert [r.name for r in rows] == ["A"]
        finally:
            reset_context_tenant_id(token_a2)
