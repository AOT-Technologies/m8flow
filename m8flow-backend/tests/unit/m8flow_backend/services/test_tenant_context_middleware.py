# m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_context_middleware.py
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flask import Flask, g

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_context_middleware import (
    _is_tenant_context_exempt_request,
    resolve_request_tenant,
    teardown_request_tenant_context,
)


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SECRET_KEY"] = "test-secret"

    db.init_app(app)

    from m8flow_backend.canonical_db import set_canonical_db
    set_canonical_db(db)


    # satisfy railguard for unit tests
    from m8flow_backend.startup.guard import set_phase, BootPhase
    set_phase(BootPhase.APP_CREATED)
    
    # Ensure ContextVar is reset between requests (including test_client requests).
    app.teardown_request(teardown_request_tenant_context)

    # A simple endpoint so test_request_context has a route.
    app.add_url_rule("/test", "test_endpoint", lambda: "ok")
    app.add_url_rule("/v1.0/permissions-check", "permissions_check_endpoint", lambda: "ok")
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

    now = int(datetime.now(timezone.utc).timestamp())

    db.session.add(
        M8flowTenantModel(
            id="default",
            name="Default",
            slug="default",
            created_by="test",
            modified_by="test",
            created_at_in_seconds=now,
            updated_at_in_seconds=now,
        )
    )
    db.session.add(
        M8flowTenantModel(
            id="tenant-a",
            name="Tenant A",
            slug="tenant-a",
            created_by="test",
            modified_by="test",
            created_at_in_seconds=now,
            updated_at_in_seconds=now,
        )
    )
    db.session.add(
        M8flowTenantModel(
            id="tenant-b",
            name="Tenant B",
            slug="tenant-b",
            created_by="test",
            modified_by="test",
            created_at_in_seconds=now,
            updated_at_in_seconds=now,
        )
    )
    db.session.add(
        M8flowTenantModel(
            id="tenant-it-id",
            name="Tenant IT",
            slug="it",
            created_by="test",
            modified_by="test",
            created_at_in_seconds=now,
            updated_at_in_seconds=now,
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
            resolve_request_tenant()
            assert g.m8flow_tenant_id == "tenant-b"


def test_missing_tenant_raises_by_default() -> None:
    from unittest.mock import patch
    
    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        with app.test_request_context("/test"):
            # Mock should_disable_auth_for_request to return True so that
            # the fallback to _authentication_identifier() is skipped
            with patch(
                "m8flow_backend.services.tenant_context_middleware.AuthorizationService"
            ) as mock_auth:
                mock_auth.should_disable_auth_for_request.return_value = True
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
                resolve_request_tenant()
            assert exc.value.error_code == "invalid_tenant"


def test_org_uuid_claim_maps_to_legacy_local_tenant_row() -> None:
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        now = int(datetime.now(timezone.utc).timestamp())
        db.session.add(
            M8flowTenantModel(
                id="m8flow",
                name="M8Flow Realm",
                slug="m8flow",
                created_by="test",
                modified_by="test",
                created_at_in_seconds=now,
                updated_at_in_seconds=now,
            )
        )

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="http://localhost:7002/realms/m8flow",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token(
            {
                "organization": {
                    "m8flow": {
                        "id": "370465d2-9b78-4c8b-9d82-c9a4818b747f",
                    }
                },
                "m8flow_authentication_identifier": "m8flow",
            }
        )
        db.session.commit()

        with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
            resolve_request_tenant()
            assert g.m8flow_tenant_id == "m8flow"


def test_tenant_validation_raises_503_when_db_not_bound() -> None:
    """When db session raises 'not registered with this SQLAlchemy instance', raise 503 instead of failing open."""
    from unittest.mock import MagicMock

    from m8flow_backend.canonical_db import get_canonical_db, set_canonical_db
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
        prev = get_canonical_db()
        set_canonical_db(mock_db)
        try:
            with app.test_request_context("/test", headers={"Authorization": f"Bearer {token}"}):
                with pytest.raises(ApiError) as exc:
                    resolve_request_tenant()
                assert exc.value.error_code == "service_unavailable"
                assert exc.value.status_code == 503
        finally:
            set_canonical_db(prev)


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
                resolve_request_tenant()
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
        resolve_request_tenant()
        db.session.add(TestItem(name=name))
        db.session.commit()
        return "ok"

    @app.get("/list")
    def _list() -> str:
        resolve_request_tenant()
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


def test_login_return_path_is_not_tenant_context_exempt_by_prefix_collision() -> None:
    app = _make_app()
    with app.test_request_context("/v1.0/login_return"):
        assert _is_tenant_context_exempt_request() is False


def test_global_tenant_management_path_is_tenant_context_exempt() -> None:
    app = _make_app()
    with app.test_request_context("/v1.0/m8flow/tenants/tenant-a"):
        assert _is_tenant_context_exempt_request() is True


def test_permissions_check_path_is_not_tenant_context_exempt() -> None:
    app = _make_app()
    with app.test_request_context("/v1.0/permissions-check"):
        assert _is_tenant_context_exempt_request() is False


def test_resolves_tenant_from_jwt_claim_on_permissions_check_path(monkeypatch) -> None:
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    org_tenant_id = "bb768eda-e8cb-4452-9a49-acd2115db07c"

    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: None,
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()
        now = int(datetime.now(timezone.utc).timestamp())
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
                name="Org Tenant",
                slug="org-tenant",
                created_by="test",
                modified_by="test",
                created_at_in_seconds=now,
                updated_at_in_seconds=now,
            )
        )

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": org_tenant_id})
        db.session.commit()

        with app.test_request_context(
            "/v1.0/permissions-check",
            headers={"Authorization": f"Bearer {token}"},
        ):
            resolve_request_tenant()

            assert current_tenant_id_or_none() == org_tenant_id
            assert g.m8flow_tenant_id == org_tenant_id
            assert org_tenant_id in current_tenant_identifiers(org_tenant_id)


def test_resolves_tenant_from_jwt_claim_on_status_path(monkeypatch) -> None:
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID
    from spiffworkflow_backend.models.user import UserModel

    app = _make_app()
    org_tenant_id = "bb768eda-e8cb-4452-9a49-acd2115db07c"

    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: DEFAULT_TENANT_ID,
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()
        now = int(datetime.now(timezone.utc).timestamp())
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
                name="Org Tenant",
                slug="org-tenant",
                created_by="test",
                modified_by="test",
                created_at_in_seconds=now,
                updated_at_in_seconds=now,
            )
        )

        user = UserModel(
            username="tester",
            email="tester@example.com",
            service="local",
            service_id="tester",
        )
        db.session.add(user)
        db.session.flush()

        token = user.encode_auth_token({"m8flow_tenant_id": org_tenant_id})
        db.session.commit()

        with app.test_request_context("/v1.0/status", headers={"Authorization": f"Bearer {token}"}):
            g.m8flow_tenant_id = DEFAULT_TENANT_ID
            resolve_request_tenant()

            assert current_tenant_id_or_none() == org_tenant_id
            assert g.m8flow_tenant_id == org_tenant_id
            assert org_tenant_id in current_tenant_identifiers(org_tenant_id)


def test_resolves_tenant_from_request_header_when_user_belongs(monkeypatch) -> None:
    app = _make_app()

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_jwt_claim_cached",
        lambda *, allow_decode: None,
    )
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: None,
    )
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware.AuthorizationService",
        SimpleNamespace(should_disable_auth_for_request=lambda: False),
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = SimpleNamespace(
            id=7,
            username="admin",
            service="http://localhost:7002/realms/shared-users",
            groups=[SimpleNamespace(identifier="tenant-a:tenant-admin")],
        )

        with app.test_request_context(
            "/test",
            headers={"x-m8flow-tenant-id": "tenant-a"},
        ):
            g.user = user
            resolve_request_tenant()

            assert g.m8flow_tenant_id == "tenant-a"
            assert current_tenant_id_or_none() == "tenant-a"
            assert "tenant-a" in current_tenant_identifiers(g.m8flow_tenant_id)


def test_rejects_tenant_header_when_user_not_member(monkeypatch) -> None:
    app = _make_app()

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_jwt_claim_cached",
        lambda *, allow_decode: None,
    )
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: None,
    )
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware.AuthorizationService",
        SimpleNamespace(should_disable_auth_for_request=lambda: False),
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()

        user = SimpleNamespace(
            id=7,
            username="admin",
            service="http://localhost:7002/realms/shared-users",
            groups=[SimpleNamespace(identifier="tenant-b:tenant-admin")],
        )

        with app.test_request_context(
            "/test",
            headers={"x-m8flow-tenant-id": "tenant-a"},
        ):
            g.user = user
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant()

            assert exc.value.error_code == "tenant_override_forbidden"


def test_login_return_resolves_tenant_from_shared_realm_and_cookie() -> None:
    """Shared-realm login_return resolves tenant from m8flow_selected_tenant cookie."""
    import base64
    import os

    os.environ["M8FLOW_KEYCLOAK_SHARED_REALM"] = "m8flow"

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        state_payload = {
            "final_url": "http://localhost:7000/",
            "authentication_identifier": "m8flow",
        }
        state = base64.b64encode(bytes(str(state_payload), "utf-8")).decode("utf-8")

        with app.test_request_context(
            f"/v1.0/login_return?state={state}",
            environ_base={"HTTP_COOKIE": "m8flow_selected_tenant=tenant-it-id"},
        ):
            resolve_request_tenant()
            assert g.m8flow_tenant_id == "tenant-it-id"

    os.environ.pop("M8FLOW_KEYCLOAK_SHARED_REALM", None)


def test_login_return_fails_without_selected_tenant_cookie() -> None:
    """Login return from shared realm without a selected-tenant cookie fails closed."""
    import base64
    import os

    os.environ["M8FLOW_KEYCLOAK_SHARED_REALM"] = "m8flow"

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        state_payload = {
            "final_url": "http://localhost:7000/",
            "authentication_identifier": "m8flow",
        }
        state = base64.b64encode(bytes(str(state_payload), "utf-8")).decode("utf-8")

        with app.test_request_context(f"/v1.0/login_return?state={state}"):
            with pytest.raises(ApiError) as exc:
                resolve_request_tenant()
            assert exc.value.error_code == "tenant_required"

    os.environ.pop("M8FLOW_KEYCLOAK_SHARED_REALM", None)


def test_login_return_skips_tenant_validation_for_master_auth_identifier() -> None:
    import base64

    app = _make_app()
    with app.app_context():
        db.create_all()
        _seed_tenants()

        state_payload = {
            "final_url": "http://localhost:7000/tenants",
            "authentication_identifier": "master",
        }
        state = base64.b64encode(bytes(str(state_payload), "utf-8")).decode("utf-8")

        with app.test_request_context(f"/v1.0/login_return?state={state}"):
            resolve_request_tenant()
            assert getattr(g, "m8flow_tenant_id", None) is None
