from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

from flask import Flask
import jwt

from m8flow_backend.canonical_db import set_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.routes import authentication_controller_patch as m8_auth_controller_patch
from m8flow_backend.services import authorization_service_patch
from m8flow_backend.routes import health_controller_patch
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
PERMISSIONS_PATH = (
    Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
)


def _make_status_app(
    *,
    register_auth_hook: bool = True,
    register_tenant_resolution_hook: bool = True,
) -> Flask:
    health_controller_patch._PATCHED = False
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
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(PERMISSIONS_PATH)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)

    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)
    if register_auth_hook:
        app.before_request(authentication_controller.omni_auth)
    if register_tenant_resolution_hook:
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
    user = UserService.create_user(username=username, service="localhost", service_id=service_id)
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
        health_controller_patch.apply(app)
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
        health_controller_patch.apply(app)
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


def test_status_endpoint_keeps_jwt_tenant_for_frontend_access_regression(monkeypatch) -> None:
    app = _make_status_app(register_auth_hook=False, register_tenant_resolution_hook=False)

    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: DEFAULT_TENANT_ID,
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        health_controller_patch.apply(app)
        token = _create_user_with_frontend_access(
            username="org-admin",
            service_id="org-admin-regression",
            tenant_id=ORG_TENANT_ID,
            group_identifier=f"{ORG_TENANT_ID}:everybody",
        )

        original_user_has_permission = AuthorizationService.user_has_permission
        seen: dict[str, object] = {}

        def _record_scope_and_delegate(cls, user, permission, target_uri):
            seen["tenant_id"] = current_tenant_id_or_none()
            seen["principal_group_identifiers"] = [
                getattr(getattr(principal, "group", None), "identifier", None)
                for principal in UserService.all_principals_for_user(user)
            ]
            seen["permission_uris"] = [
                assignment.permission_target.uri for assignment in AuthorizationService.all_permission_assignments_for_user(user)
            ]
            return original_user_has_permission(user, permission, target_uri)

        monkeypatch.setattr(AuthorizationService, "user_has_permission", classmethod(_record_scope_and_delegate))

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert seen["tenant_id"] == ORG_TENANT_ID
    assert f"{ORG_TENANT_ID}:everybody" in seen["principal_group_identifiers"]
    assert "/frontend-access" in seen["permission_uris"]


def test_status_endpoint_repairs_stale_same_realm_user_and_returns_frontend_access(monkeypatch) -> None:
    app = _make_status_app(register_auth_hook=False, register_tenant_resolution_hook=False)

    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_context_middleware._tenant_from_context_var",
        lambda: DEFAULT_TENANT_ID,
    )

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        health_controller_patch.apply(app)

        stale_user = UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="legacy-subject",
        )
        stale_user_id = stale_user.id

        verified_token = {
            "iss": "http://localhost:7002/realms/m8flow",
            "sub": "new-subject",
            "preferred_username": "admin",
            "groups": ["everybody"],
            "m8flow_tenant_id": ORG_TENANT_ID,
        }

        raw_token = jwt.encode(verified_token, "status-test-secret", algorithm="HS256")

        def _verified_status_token(*_args, **_kwargs):
            return dict(verified_token)

        monkeypatch.setattr(authentication_controller, "verify_token", _verified_status_token)

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}

    with app.app_context():
        refreshed_user = UserService.get_user_by_service_and_service_id(
            "http://localhost:7002/realms/m8flow",
            "new-subject",
        )
        assert refreshed_user is not None
        assert refreshed_user.id == stale_user_id
        assert f"{ORG_TENANT_ID}:everybody" in {group.identifier for group in refreshed_user.groups}


def test_status_endpoint_uses_selected_org_for_multi_org_external_token(monkeypatch) -> None:
    app = _make_status_app(register_auth_hook=False, register_tenant_resolution_hook=False)

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        health_controller_patch._PATCHED = False
        health_controller_patch.apply(app)

        UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
        )

        verified_token = {
            "iss": "http://localhost:7002/realms/m8flow",
            "sub": "26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
            "preferred_username": "admin",
            "groups": ["tenant-admin"],
            "organization": {
                "it": {"id": ORG_TENANT_ID, "groups": ["/tenant-admin"]},
                "other-tenant": {"id": OTHER_TENANT_ID, "groups": ["/viewer"]},
            },
        }
        raw_token = jwt.encode(verified_token, "status-test-secret", algorithm="HS256")

        def _verified_status_token(*_args, **_kwargs):
            from flask import g

            g.user = UserService.get_user_by_service_and_service_id(
                "http://localhost:7002/realms/m8flow",
                "26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
            )
            return dict(verified_token)

        monkeypatch.setattr(authentication_controller, "verify_token", _verified_status_token)

        original_user_has_permission = AuthorizationService.user_has_permission
        seen: dict[str, object] = {}

        def _record_scope_and_delegate(cls, user, permission, target_uri):
            seen["tenant_id"] = current_tenant_id_or_none()
            seen["principal_group_identifiers"] = [
                getattr(getattr(principal, "group", None), "identifier", None)
                for principal in UserService.all_principals_for_user(user)
            ]
            return original_user_has_permission(user, permission, target_uri)

        monkeypatch.setattr(AuthorizationService, "user_has_permission", classmethod(_record_scope_and_delegate))

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie("m8flow_selected_tenant", ORG_TENANT_ID)
    response = client.get("/v1.0/status", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert seen["tenant_id"] == ORG_TENANT_ID
    assert f"{ORG_TENANT_ID}:everybody" in seen["principal_group_identifiers"]
    assert f"{OTHER_TENANT_ID}:everybody" not in seen["principal_group_identifiers"]


def test_status_endpoint_does_not_clear_auth_cookies_when_verified_external_token_succeeds(
    monkeypatch,
) -> None:
    app = _make_status_app(register_auth_hook=False, register_tenant_resolution_hook=False)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    with app.app_context():
        db.create_all()
        _seed_tenants()
        m8_auth_controller_patch._PATCHED = False
        m8_auth_controller_patch._COOKIE_DOMAIN_PATCHED = False
        m8_auth_controller_patch._PUBLIC_GROUP_PATCHED = False
        m8_auth_controller_patch.apply()
        authorization_service_patch.apply()
        health_controller_patch._PATCHED = False
        health_controller_patch.apply(app)

        UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
        )

        verified_token = {
            "iss": "http://localhost:7002/realms/m8flow",
            "sub": "26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
            "preferred_username": "admin",
            "groups": ["tenant-admin"],
            "organization": {
                "it": {"id": ORG_TENANT_ID, "groups": ["/tenant-admin"]},
                "other-tenant": {"id": OTHER_TENANT_ID, "groups": ["/viewer"]},
            },
        }
        raw_token = jwt.encode(verified_token, "status-test-secret", algorithm="HS256")

        verify_called = {"value": False}

        def _verified_status_token(*_args, **_kwargs):
            from flask import g

            verify_called["value"] = True
            g.user = UserService.get_user_by_service_and_service_id(
                "http://localhost:7002/realms/m8flow",
                "26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
            )
            return dict(verified_token)

        monkeypatch.setattr(authentication_controller, "verify_token", _verified_status_token)

        app.after_request(authentication_controller._set_new_access_token_in_cookie)

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie("m8flow_selected_tenant", ORG_TENANT_ID)
    app.config["THREAD_LOCAL_DATA"].user_has_logged_out = True
    response = client.get("/v1.0/status", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert verify_called["value"] is True
    set_cookie_headers = response.headers.getlist("Set-Cookie")
    assert not any(header.startswith("access_token=;") for header in set_cookie_headers)
    assert not any(header.startswith("id_token=;") for header in set_cookie_headers)
    assert not any(header.startswith("authentication_identifier=;") for header in set_cookie_headers)
    assert not hasattr(app.config["THREAD_LOCAL_DATA"], "user_has_logged_out")


def test_status_endpoint_does_not_sync_or_grant_access_from_unverified_external_token(monkeypatch) -> None:
    app = _make_status_app(register_auth_hook=False, register_tenant_resolution_hook=False)

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        health_controller_patch._PATCHED = False
        health_controller_patch.apply(app)

        raw_token = jwt.encode(
            {
                "iss": "http://localhost:7002/realms/m8flow",
                "sub": "forged-subject",
                "preferred_username": "forged-admin",
                "groups": ["everybody"],
                "m8flow_tenant_id": ORG_TENANT_ID,
            },
            "status-test-secret",
            algorithm="HS256",
        )

        def _fail_verify_token(*_args, **_kwargs):
            raise RuntimeError("status verify_token rejected external token")

        monkeypatch.setattr(authentication_controller, "verify_token", _fail_verify_token)

    response = app.test_client().get("/v1.0/status", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": False}

    with app.app_context():
        assert UserService.get_user_by_service_and_service_id(
            "http://localhost:7002/realms/m8flow",
            "forged-subject",
        ) is None


def test_status_endpoint_denies_frontend_access_for_other_tenant_group() -> None:
    app = _make_status_app()

    with app.app_context():
        db.create_all()
        _seed_tenants()
        authorization_service_patch.apply()
        health_controller_patch.apply(app)
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
        health_controller_patch.apply(app)

    response = app.test_client().get("/v1.0/status")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
