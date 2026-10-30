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


@pytest.mark.parametrize(
    ("path", "expected_instance"),
    [
        ("/process-instances/{id}/suspend", "/process-instances/{id}"),
        ("/process-instances/{id}/resume", "/process-instances/{id}"),
        ("/process-instances/{id}/terminate", "/process-instances/{id}"),
        ("/process-instances/42/suspend", "/process-instances/42"),
        ("/process-instances/42/resume", "/process-instances/42"),
        ("/process-instances/42/terminate", "/process-instances/42"),
        ("/process-instances/42/terminate/", "/process-instances/42"),
        ("/v1.0/process-instances/{id}/suspend", "/process-instances/{id}"),
        ("/v1.0/process-instances/{id}/resume", "/process-instances/{id}"),
        ("/v1.0/process-instances/{id}/terminate", "/process-instances/{id}"),
        ("/v1.0/process-instances/42/suspend", "/process-instances/42"),
        ("/v1.0/process-instances/42/resume", "/process-instances/42"),
        ("/v1.0/process-instances/42/terminate", "/process-instances/42"),
        ("/v1.0/process-instances/42/terminate/", "/process-instances/42"),
    ],
)
def test_lifecycle_route_regex_matches_versioned_and_unversioned(path, expected_instance):
    match = authorization._LIFECYCLE_ROUTE.fullmatch(path)
    assert match is not None
    assert match.group(1) == expected_instance


@pytest.mark.parametrize(
    "path",
    [
        "/process-instances",
        "/v1.0/process-instances",
        "/process-instances/",
        "/v1.0/process-instances/",
        "/process-instances/42",
        "/v1.0/process-instances/42",
        "/process-instances/for-me",
        "/v1.0/process-instances/for-me",
        "/process-instances/42/events",
        "/v1.0/process-instances/42/events",
        "/process-instances/42/unknown",
        "/process-instances/42/suspend/extra",
        "/v1.0/process-instances/42/suspend/extra",
    ],
)
def test_lifecycle_route_regex_does_not_match_other_instance_routes(path):
    assert authorization._LIFECYCLE_ROUTE.fullmatch(path) is None


@pytest.mark.parametrize(
    ("path", "expected_target"),
    [
        ("/process-instances/{id}/suspend", "/process-instances/{id}"),
        ("/process-instances/{id}/resume", "/process-instances/{id}"),
        ("/process-instances/{id}/terminate", "/process-instances/{id}"),
        ("/process-instances/42/suspend", "/process-instances/42"),
        ("/process-instances/42/resume", "/process-instances/42"),
        ("/process-instances/42/terminate", "/process-instances/42"),
        ("/process-instances/42/terminate/", "/process-instances/42"),
        ("/v1.0/process-instances/{id}/suspend", "/process-instances/{id}"),
        ("/v1.0/process-instances/{id}/resume", "/process-instances/{id}"),
        ("/v1.0/process-instances/{id}/terminate", "/process-instances/{id}"),
        ("/v1.0/process-instances/42/suspend", "/process-instances/42"),
        ("/v1.0/process-instances/42/resume", "/process-instances/42"),
        ("/v1.0/process-instances/42/terminate", "/process-instances/42"),
        ("/v1.0/process-instances/42/terminate/", "/process-instances/42"),
    ],
)
def test_allow_uri_remaps_lifecycle_post_to_execute_for_versioned_and_unversioned(
    path, expected_target, regular_user, monkeypatch
):
    seen = []

    def resource_permitted(_session, _user, action, _resource_type, resource_id, **_kwargs):
        seen.append((action, resource_id))
        return True

    monkeypatch.setattr(authorization, "_resource_permitted", resource_permitted)

    assert authorization.allow_uri(regular_user, "POST", path, session=object()) is True
    assert seen == [("execute", expected_target)]


@pytest.mark.parametrize(
    "path",
    ["/process-instances", "/v1.0/process-instances", "/process-instances/", "/v1.0/process-instances/"],
)
def test_allow_uri_does_not_remap_start_process_instance(path, regular_user, monkeypatch):
    seen = []

    def resource_permitted(_session, _user, action, _resource_type, resource_id, **_kwargs):
        seen.append((action, resource_id))
        return True

    monkeypatch.setattr(authorization, "_resource_permitted", resource_permitted)

    assert authorization.allow_uri(regular_user, "POST", path, session=object()) is True
    assert seen == [("create", "/process-instances")]



def _user_with_groups(*identifiers):
    return SimpleNamespace(
        id=7, groups=[SimpleNamespace(identifier=item) for item in identifiers], principal=None
    )


@pytest.mark.parametrize(
    "path", ["/process-instances", "/v1.0/process-instances", "/v1.0/process-instances/", "process-instances//"]
)
def test_editor_group_fallback_does_not_imply_tenant_wide_instance_read(path, monkeypatch):
    """M8F-627: editors read only instances they started, so their role-name
    fallback must not stand in for the tenant-wide instance grant."""
    monkeypatch.setattr(authorization, "current_tenant_identifiers", lambda: ())
    editor = _user_with_groups("t1:editor")

    # Any spelling of a read (HTTP verb, any case, or no action at all) stays suppressed.
    for action in ("read", "READ", "GET", "get", "Head", None):
        assert authorization._group_identifier_fallback(editor, path, action) is False, action
    assert authorization._group_identifier_fallback(_user_with_groups("t1:tenant-admin"), path, "read") is True
    # Starting an instance (create) and own-instance read are unaffected.
    assert authorization._group_identifier_fallback(editor, path, "create") is True
    assert authorization._group_identifier_fallback(editor, path, "POST") is True
    assert authorization._group_identifier_fallback(editor, "/v1.0/process-instances/for-me", "read") is True


def test_editor_without_tenant_wide_grant_is_scoped_to_own_instances(monkeypatch):
    monkeypatch.setattr(authorization, "actor_is_super_admin", lambda _user: False)
    monkeypatch.setattr(authorization, "current_tenant_identifiers", lambda: ())
    monkeypatch.setattr(authorization, "_resource_permitted", lambda *_args, **_kwargs: False)

    assert authorization.instance_initiator_scope(_user_with_groups("t1:editor"), session=object()) == 7
    assert authorization.instance_initiator_scope(_user_with_groups("t1:tenant-admin"), session=object()) is None
