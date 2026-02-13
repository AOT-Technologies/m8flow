# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_context_middleware.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import Flask, g

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from m8flow_backend.services.tenant_context_middleware import (
    resolve_request_tenant,
    teardown_request_tenant_context,
)


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

    # Ensure ContextVar is reset between requests (including test_client requests).
    app.teardown_request(teardown_request_tenant_context)

    # A simple endpoint so test_request_context has a route.
    app.add_url_rule("/test", "test_endpoint", lambda: "ok")
    return app


@pytest.fixture(autouse=True)
def _clean_env():
    """
    Prevent env leakage between tests, since tenant resolution behavior
    is controlled by M8FLOW_ALLOW_MISSING_TENANT_CONTEXT.
    """
    import os

    old = os.environ.get("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT")
    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    yield
    if old is None:
        os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    else:
        os.environ["M8FLOW_ALLOW_MISSING_TENANT_CONTEXT"] = old


def _seed_tenants() -> None:
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    db.session.add(
        M8flowTenantModel(
            id="default",
            name="Default",
            slug="default",
            created_by="test",
            modified_by="test",
        )
    )
    db.session.add(
        M8flowTenantModel(
            id="tenant-a",
            name="Tenant A",
            slug="tenant-a",
            created_by="test",
            modified_by="test",
        )
    )
    db.session.add(
        M8flowTenantModel(
            id="tenant-b",
            name="Tenant B",
            slug="tenant-b",
            created_by="test",
            modified_by="test",
        )
    )
    db.session.commit()



def test_resolves_tenant_from_jwt_claim() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-b"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            resolve_request_tenant(db)
            assert g.m8flow_tenant_id == "tenant-b"


def test_missing_tenant_raises_by_default() -> None:
    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        with app.test_request_context("/test"):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant(db)
            assert exc.value.error_code == "tenant_required"


def test_missing_tenant_defaults_when_allowed() -> None:
    import os

    os.environ["M8FLOW_ALLOW_MISSING_TENANT_CONTEXT"] = "true"

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        with app.test_request_context("/test"):
            resolve_request_tenant(db)
            assert g.m8flow_tenant_id == "default"


def test_invalid_tenant_raises() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-missing"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant(db)
            assert exc.value.error_code == "invalid_tenant"


def test_tenant_validation_raises_503_when_db_not_bound() -> None:
    """When db session raises 'not registered with this SQLAlchemy instance', raise 503 instead of failing open."""
    from unittest.mock import MagicMock

    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()
        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-a"})
        db.session.commit()

        runtime_error = RuntimeError(
            "M8flowTenantModel is not registered with this 'SQLAlchemy' instance."
        )
        mock_db = MagicMock()
        mock_db.session.query.return_value.filter.return_value.one_or_none.side_effect = (
            runtime_error
        )
        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant(mock_db)
            assert exc.value.error_code == "service_unavailable"
            assert exc.value.status_code == 503


def test_tenant_override_forbidden() -> None:
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": "tenant-b"})
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            g.m8flow_tenant_id = "tenant-a"
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant(db)
            assert exc.value.error_code == "tenant_override_forbidden"


def test_tenant_context_propagates_to_queries() -> None:
    from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped
    from m8flow_backend.services import tenant_scoping_patch

    tenant_scoping_patch.apply()

    class TestItem(M8fTenantScopedMixin, TenantScoped, db.Model):
        __tablename__ = "m8f_test_item"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)

    app = _make_app()

    # Exercise the real lifecycle (including teardown_request reset of ContextVar)
    @app.get("/add/<name>")
    def _add(name: str) -> str:
        resolve_request_tenant(db)
        db.session.add(TestItem(name=name))
        db.session.commit()
        return "ok"

    @app.get("/list")
    def _list() -> str:
        resolve_request_tenant(db)
        rows = TestItem.query.order_by(TestItem.name).all()
        return ",".join([r.name for r in rows])

    with app.app_context():
        from spiffworkflow_backend.models.user import UserModel

        db.drop_all()
        db.create_all()
        _seed_tenants()

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token_tenant_a = user.encode_auth_token({"m8flow_tenant_id": "tenant-a"})
        token_tenant_b = user.encode_auth_token({"m8flow_tenant_id": "tenant-b"})
        db.session.commit()

    client = app.test_client()

    client.get("/add/A", headers={"Authorization": f"Bearer {token_tenant_a}"})
    client.get("/add/B", headers={"Authorization": f"Bearer {token_tenant_b}"})

    resp = client.get("/list", headers={"Authorization": f"Bearer {token_tenant_a}"})
    assert resp.get_data(as_text=True) == "A"
