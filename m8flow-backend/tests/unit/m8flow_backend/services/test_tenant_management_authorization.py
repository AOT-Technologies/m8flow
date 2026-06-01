from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask
from flask import g

from m8flow_backend.services import tenant_management_authorization
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    db.init_app(app)
    return app


def test_require_authorized_user_allows_tenant_admin_group_membership_on_global_tenant_management_route(
    monkeypatch,
) -> None:
    app = _make_app()

    with app.app_context():
        db.create_all()
        with app.test_request_context("/v1.0/m8flow/tenants/tenant-a/members"):
            g.user = SimpleNamespace(
                username="admin",
                groups=[SimpleNamespace(identifier="tenant-a:tenant-admin")],
            )
            g._m8flow_global_request = True

            monkeypatch.setattr(
                tenant_management_authorization.AuthorizationService,
                "user_has_permission",
                lambda *_args, **_kwargs: False,
            )

            user = tenant_management_authorization.require_authorized_user(
                "read",
                tenant_id="tenant-a",
                forbidden_message="forbidden",
            )

    assert user.username == "admin"


def test_require_authorized_user_rejects_tenant_admin_group_membership_for_other_tenant(
    monkeypatch,
) -> None:
    app = _make_app()

    with app.app_context():
        db.create_all()
        with app.test_request_context("/v1.0/m8flow/tenants/tenant-b/members"):
            g.user = SimpleNamespace(
                username="admin",
                groups=[SimpleNamespace(identifier="tenant-a:tenant-admin")],
            )
            g._m8flow_global_request = True

            monkeypatch.setattr(
                tenant_management_authorization.AuthorizationService,
                "user_has_permission",
                lambda *_args, **_kwargs: False,
            )

            with pytest.raises(ApiError) as exc_info:
                tenant_management_authorization.require_authorized_user(
                    "read",
                    tenant_id="tenant-b",
                    forbidden_message="forbidden",
                )

    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "forbidden"


def test_ensure_request_can_access_tenant_allows_super_admin_group_without_global_flags() -> None:
    app = _make_app()

    with app.app_context():
        db.create_all()
        with app.test_request_context("/v1.0/m8flow/tenants/tenant-b/members"):
            g.user = SimpleNamespace(
                username="super-admin-user",
                groups=[SimpleNamespace(identifier="super-admin")],
            )
            g._m8flow_super_admin_request = False
            g._m8flow_global_request = False
            g.m8flow_tenant_id = None

            tenant_management_authorization.ensure_request_can_access_tenant(
                "tenant-b",
                forbidden_message="forbidden",
            )
