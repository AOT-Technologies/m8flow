from __future__ import annotations

from types import SimpleNamespace

import pytest

import m8flow_backend.authorization as authorization


@pytest.fixture
def regular_user(monkeypatch):
    user = SimpleNamespace(groups=[], principal=None)
    monkeypatch.setattr(authorization, "actor_is_super_admin", lambda _user: False)
    return user


@pytest.mark.parametrize("path", ["/onboarding", "/v1.0/onboarding"])
def test_allow_uri_normalizes_standard_granted_route(path, regular_user, monkeypatch):
    seen = []

    def resource_permitted(_session, _user, _action, _resource_type, resource_id, **_kwargs):
        seen.append(resource_id)
        return resource_id == "/onboarding"

    monkeypatch.setattr(authorization, "_resource_permitted", resource_permitted)

    assert authorization.allow_uri(regular_user, "GET", path, session=object()) is True
    assert seen == ["/onboarding"]


@pytest.mark.parametrize(
    "path", ["/secrets", "/secrets/", "/v1.0/secrets", "/v1.0/secrets/"]
)
def test_allow_uri_normalizes_no_group_fallback_route(path, regular_user, monkeypatch):
    fallback_calls = []
    monkeypatch.setattr(authorization, "_resource_permitted", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        authorization,
        "_group_identifier_fallback",
        lambda _user, candidate: fallback_calls.append(candidate) or True,
    )

    assert authorization.allow_uri(regular_user, "GET", path, session=object()) is False
    assert fallback_calls == []


@pytest.mark.parametrize("path", ["/m8flow/home-task-count", "/v1.0/m8flow/home-task-count"])
@pytest.mark.parametrize("has_explicit_grant", [False, True])
def test_allow_uri_normalizes_home_task_count_and_requires_explicit_grant(
    path, has_explicit_grant, monkeypatch
):
    user = SimpleNamespace(groups=[], principal=None)
    # Even super-admins do not get the implicit global shortcut for a personal
    # task queue, but a materialized target grant remains honored.
    monkeypatch.setattr(authorization, "actor_is_super_admin", lambda _user: True)
    seen = []

    def resource_permitted(_session, _user, _action, _resource_type, resource_id, **_kwargs):
        seen.append(resource_id)
        return has_explicit_grant

    monkeypatch.setattr(authorization, "_resource_permitted", resource_permitted)

    assert authorization.allow_uri(user, "GET", path, session=object()) is has_explicit_grant
    assert seen == ["/m8flow/home-task-count"]


def test_home_task_count_permission_fails_closed_and_logs_without_flask_context(caplog):
    user = SimpleNamespace(groups=[], principal=None)

    assert authorization.allow_uri(user, "GET", "/m8flow/home-task-count") is False
    assert "no database session is available" in caplog.text


def test_home_task_count_permission_fails_closed_without_request_session(app):
    user = SimpleNamespace(groups=[], principal=None)

    with app.test_request_context("/v1.0/permissions-check"):
        assert authorization.allow_uri(user, "GET", "/m8flow/home-task-count") is False


@pytest.mark.parametrize(
    "path",
    [
        "/m8flow/task-review/{id}/submit",
        "/m8flow/task-review-access/{id}/submit",
        "/m8flow/task-review/123/submit/",
        "/v1.0/m8flow/task-review/{id}/submit/",
        "/v1.0/m8flow/task-review-access/123/submit/",
    ],
)
def test_super_admin_cannot_submit_task_review_for_all_uri_shapes(path, monkeypatch):
    user = SimpleNamespace(groups=[], principal=None)
    monkeypatch.setattr(authorization, "actor_is_super_admin", lambda _user: True)

    assert authorization.allow_uri(user, "POST", path, session=object()) is False


@pytest.mark.parametrize(
    ("path", "expected_target"),
    [
        (
            "/m8flow/task-review/{id}/submit",
            "/m8flow/task-review-access/{id}/submit",
        ),
        (
            "/m8flow/task-review-access/{id}/submit/",
            "/m8flow/task-review-access/{id}/submit",
        ),
        (
            "/v1.0/m8flow/task-review/123/submit/",
            "/m8flow/task-review-access/123/submit",
        ),
        (
            "/v1.0/m8flow/task-review-access/123/submit",
            "/m8flow/task-review-access/123/submit",
        ),
    ],
)
def test_task_review_submit_shapes_use_canonical_target_and_no_group_fallback(
    path, expected_target, regular_user, monkeypatch
):
    targets = []
    fallback_calls = []
    monkeypatch.setattr(
        authorization,
        "_resource_permitted",
        lambda _session, _user, _action, _resource_type, resource_id, **_kwargs: (
            targets.append(resource_id) or False
        ),
    )
    monkeypatch.setattr(
        authorization,
        "_group_identifier_fallback",
        lambda _user, candidate: fallback_calls.append(candidate) or True,
    )

    assert authorization.allow_uri(regular_user, "POST", path, session=object()) is False
    assert targets == [expected_target]
    assert fallback_calls == []
