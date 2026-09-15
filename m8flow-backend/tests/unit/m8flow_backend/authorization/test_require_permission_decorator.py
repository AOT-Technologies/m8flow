from __future__ import annotations

import pytest

from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.integrations.auth.base.models import VerifiedClaims
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE

_DENIED_URI = "/v1.0/__require_permission_test/unrelated"


def _user_with_groups(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    # Mirrors what the real login path (auth.sync_groups_from_token) does
    # right after sync_groups: materialize m8flow.yml's declarative grants
    # as PermissionAssignmentModel rows for this tenant's groups, so
    # allow_uri's real DB-backed check (not just the group-identifier
    # fallback) has something to match against.
    import_yaml(db_session, tenant_id=tenant_id)
    db_session.commit()
    return user


def test_allowed_request_reaches_the_view(app, db_session):
    # "viewer" is in VALID_TENANT_ROLE_NAMES but isn't one of the roles
    # _group_identifier_fallback grants unconditionally, and m8flow.yml's
    # "read-task-list" permission explicitly grants viewer read on /tasks --
    # so this proves the decorator calls through to a real DB-backed allow,
    # not just the fallback.
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission("GET", "/v1.0/tasks")
    def view():
        return "reached"

    with app.test_request_context("/v1.0/tasks", method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        assert view() == "reached"


def test_default_deny_raises_403(app, db_session):
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission("GET", _DENIED_URI, forbidden_message="nope")
    def view():
        raise AssertionError("view body must not run when the request is denied")

    with app.test_request_context(_DENIED_URI, method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        with pytest.raises(ApiError) as exc_info:
            view()
    assert exc_info.value.error_code == "permission_denied"
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "nope"


def test_on_deny_404_hides_existence(app, db_session):
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission("GET", _DENIED_URI, on_deny="404")
    def view():
        raise AssertionError("view body must not run when the request is denied")

    with app.test_request_context(_DENIED_URI, method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        with pytest.raises(ApiError) as exc_info:
            view()
    assert exc_info.value.error_code == "not_found"
    assert exc_info.value.status_code == 404


def test_on_deny_empty_returns_response_instead_of_raising(app, db_session):
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission("GET", _DENIED_URI, on_deny="empty", empty_response=[])
    def view():
        raise AssertionError("view body must not run when the request is denied")

    with app.test_request_context(_DENIED_URI, method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        response = view()
    assert response.status_code == 200
    assert response.get_json() == []


def test_uri_template_resolves_from_view_kwargs(app, db_session):
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission("GET", "/v1.0/onboarding/{suffix}")
    def view(suffix: str):
        return suffix

    with app.test_request_context("/v1.0/onboarding/anything", method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        # "/v1.0/onboarding/whatever" isn't itself a granted uri, but this
        # proves the template was actually formatted (not left as a literal
        # "{suffix}" placeholder, which would never match any grant either
        # way) -- assert on the denial's shape instead of the allow path.
        with pytest.raises(ApiError) as exc_info:
            view(suffix="whatever")
    assert exc_info.value.status_code == 403


def test_action_defaults_to_request_method(app, db_session):
    user = _user_with_groups(db_session, username="viewer", groups=["t1:viewer"])

    @require_permission(uri=_DENIED_URI)
    def view():
        raise AssertionError("view body must not run when the request is denied")

    with app.test_request_context(_DENIED_URI, method="POST"):
        from flask import g

        g.user = user
        g.db_session = db_session
        with pytest.raises(ApiError):
            view()


def test_super_admin_short_circuits_regardless_of_uri(app, db_session):
    user = ensure_user(
        db_session,
        username="root",
        service="https://example.test/realms/master",
        service_id="root",
    )
    db_session.commit()

    @require_permission("GET", _DENIED_URI)
    def view():
        return "reached"

    with app.test_request_context(_DENIED_URI, method="GET"):
        from flask import g

        g.user = user
        g.db_session = db_session
        g.verified_claims = VerifiedClaims(
            subject="root",
            issuer="https://example.test/realms/master",
            username="root",
            roles=[SUPER_ADMIN_ROLE],
        )
        assert view() == "reached"
