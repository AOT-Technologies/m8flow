from __future__ import annotations

from datetime import datetime
from datetime import timezone

from flask import Flask

from m8flow_backend.canonical_db import set_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services import authorization_service_patch
from m8flow_backend.startup.flask_hooks import register_request_active_hooks
from m8flow_backend.startup.flask_hooks import register_request_tenant_context_hooks
from m8flow_backend.startup.guard import BootPhase
from m8flow_backend.startup.guard import set_phase
from m8flow_backend.startup.tenant_resolution import register_tenant_resolution_after_auth
from m8flow_backend.tenancy import DEFAULT_TENANT_ID
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.routes import authentication_controller
from spiffworkflow_backend.routes.health_controller import status as health_status
from spiffworkflow_backend.services.authorization_service import AuthorizationService
from spiffworkflow_backend.services.user_service import UserService


ORG_TENANT_ID = "bb768eda-e8cb-4452-9a49-acd2115db07c"
OTHER_TENANT_ID = "f45b7d1f-7f3d-4f8a-9a56-7d4f2d8a7d32"
BACKEND_URL = "http://localhost"


def _make_status_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = BACKEND_URL
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://frontend.local"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SECRET_KEY"] = "test-secret"

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)

    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)
    app.before_request(authentication_controller.omni_auth)
    register_tenant_resolution_after_auth(app)

    app.add_url_rule("/v1.0/status", "status", health_status, methods=["GET"])
    return app


def _seed_tenants() -> None:
    now = int(datetime.now(timezone.utc).timestamp())

    for tenant_id, name, slug in [
        (DEFAULT_TENANT_ID, "Default", DEFAULT_TENANT_ID),
        (ORG_TENANT_ID, "Org Tenant", "org-tenant"),
        (OTHER_TENANT_ID, "Other Tenant", "other-tenant"),
    ]:
        db.session.add(
            M8flowTenantModel(
                id=tenant_id,
                name=name,
                slug=slug,
                created_by="test",
                modified_by="test",
                created_at_in_seconds=now,
                updated_at_in_seconds=now,
            )
        )

    db.session.commit()


def _create_user_with_frontend_access(
    *,
    username: str,
    service_id: str,
    tenant_id: str,
    group_identifier: str,
) -> str:
    user = UserService.create_user(username=username, service=BACKEND_URL, service_id=service_id)
    group = UserService.find_or_create_group(group_identifier)
    UserService.add_user_to_group(user, group)
    AuthorizationService.add_permission_from_uri_or_macro(group.identifier, "read", "/frontend-access")
    return user.encode_auth_token({"m8flow_tenant_id": tenant_id})


def test_status_endpoint_allows_frontend_access_for_active_tenant_everybody() -> None:
    app = _make_status_app()

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        token = _create_user_with_frontend_access(
            username="org-admin",
            service_id="org-admin",
            tenant_id=ORG_TENANT_ID,
            group_identifier=f"{ORG_TENANT_ID}:everybody",
        )

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}


def test_status_endpoint_prefers_jwt_tenant_over_default(monkeypatch) -> None:
    app = _make_status_app()

    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: DEFAULT_TENANT_ID,
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        token = _create_user_with_frontend_access(
            username="org-admin",
            service_id="org-admin-default",
            tenant_id=ORG_TENANT_ID,
            group_identifier=f"{ORG_TENANT_ID}:everybody",
        )

        original_user_has_permission = AuthorizationService.user_has_permission
        seen: dict[str, str | None] = {}

        def _record_tenant_and_delegate(cls, user, permission, target_uri):
            seen["tenant_id"] = current_tenant_id_or_none()
            return original_user_has_permission(user, permission, target_uri)

        monkeypatch.setattr(AuthorizationService, "user_has_permission", classmethod(_record_tenant_and_delegate))

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert seen["tenant_id"] == ORG_TENANT_ID


def test_status_endpoint_denies_frontend_access_for_other_tenant_group() -> None:
    app = _make_status_app()

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        token = _create_user_with_frontend_access(
            username="other-admin",
            service_id="other-admin",
            tenant_id=ORG_TENANT_ID,
            group_identifier=f"{OTHER_TENANT_ID}:everybody",
        )

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": False}


def test_status_endpoint_anonymous_behavior_remains_unchanged() -> None:
    app = _make_status_app()

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()

    response = app.test_client().get("/v1.0/status")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
