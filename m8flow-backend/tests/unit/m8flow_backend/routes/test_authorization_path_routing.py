"""Non-canonical URLs must agree across Connexion, Flask, and route RBAC."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

from flask import request
import pytest

from m8flow_core.models.process_instance import ProcessInstanceModel

from m8flow_backend import authorization, identity, workflow
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.api_versions import API_VERSION_PREFIXES


@pytest.fixture
def routing_member(client, db_session):
    tenant_id = "routing-tenant"
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username="routing-viewer",
        service="https://example.test/realms/m8flow",
        service_id="routing-viewer",
    )
    ensure_membership(db_session, user, tenant)
    # Viewer has no group fallback when the resource check denies.
    sync_groups(db_session, user=user, group_identifiers=[f"{tenant_id}:viewer"], tenant_id=tenant_id)
    db_session.add(ProcessInstanceModel(
        id=123,
        m8f_tenant_id=tenant_id,
        process_model_identifier="routing/wait",
        process_model_display_name="Routing wait",
        process_initiator_id=user.id,
        status="waiting",
    ))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user.id, tenant_id, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def versioned_grant_member(client, db_session):
    granted_tenant_id = "versioned-grant-tenant"
    denied_tenant_id = "versioned-deny-tenant"
    granted_tenant = ensure_tenant(
        db_session, tenant_id=granted_tenant_id, slug=granted_tenant_id
    )
    denied_tenant = ensure_tenant(db_session, tenant_id=denied_tenant_id, slug=denied_tenant_id)
    user = ensure_user(
        db_session,
        username="versioned-grant-viewer",
        service="https://example.test/realms/m8flow",
        service_id="versioned-grant-viewer",
    )
    ensure_membership(db_session, user, granted_tenant)
    ensure_membership(db_session, user, denied_tenant)
    sync_groups(
        db_session,
        user=user,
        # Membership in both tenants lets the cookie select either context.
        # Only the granted tenant gets a role with a real `/tasks` grant;
        # `member` exists solely to establish membership in the denied tenant.
        group_identifiers=[f"{granted_tenant_id}:viewer", f"{denied_tenant_id}:member"],
        tenant_id=granted_tenant_id,
    )
    identity.import_yaml(db_session, tenant_id=granted_tenant_id)
    identity.import_yaml(db_session, tenant_id=denied_tenant_id)
    db_session.commit()
    token = encode_auth_token(user=user)
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "granted_tenant_id": granted_tenant_id,
        "denied_tenant_id": denied_tenant_id,
    }


def test_v1_v2_flask_route_use_real_active_tenant_grants_identically(
    client, versioned_grant_member
):
    headers = versioned_grant_member["headers"]
    allowed_responses = []
    denied_responses = []

    for version_prefix in API_VERSION_PREFIXES:
        client.set_cookie(
            SELECTED_TENANT_COOKIE_NAME, versioned_grant_member["granted_tenant_id"]
        )
        allowed = client.get(f"{version_prefix}/tasks", headers=headers)
        allowed_responses.append(allowed)

        client.set_cookie(
            SELECTED_TENANT_COOKIE_NAME, versioned_grant_member["denied_tenant_id"]
        )
        denied = client.get(f"{version_prefix}/tasks", headers=headers)
        denied_responses.append(denied)

    assert [response.status_code for response in allowed_responses] == [200, 200]
    assert allowed_responses[0].get_json() == allowed_responses[1].get_json()
    assert [response.status_code for response in denied_responses] == [403, 403]
    assert denied_responses[0].get_json() == denied_responses[1].get_json()
    assert denied_responses[0].get_json()["error_code"] == "permission_denied"


def test_v1_v2_connexion_route_use_real_active_tenant_grants_identically(
    client, versioned_grant_member
):
    """Connexion dispatch must enforce the same selected-tenant grants as Flask routes."""
    granted_tenant_id = versioned_grant_member["granted_tenant_id"]
    denied_tenant_id = versioned_grant_member["denied_tenant_id"]

    headers = versioned_grant_member["headers"]
    allowed_responses = []
    denied_responses = []
    for version_prefix in API_VERSION_PREFIXES:
        client.set_cookie(SELECTED_TENANT_COOKIE_NAME, granted_tenant_id)
        allowed_responses.append(
            client.get(f"{version_prefix}/m8flow/connector-templates", headers=headers)
        )

        client.set_cookie(SELECTED_TENANT_COOKIE_NAME, denied_tenant_id)
        denied_responses.append(
            client.get(f"{version_prefix}/m8flow/connector-templates", headers=headers)
        )

    assert [response.status_code for response in allowed_responses] == [200, 200]
    assert [response.status_code for response in denied_responses] == [403, 403]
    allowed_payloads = [response.get_json() for response in allowed_responses]
    denied_payloads = [response.get_json() for response in denied_responses]
    assert allowed_payloads[0] == allowed_payloads[1]
    assert denied_payloads[0] == denied_payloads[1]
    assert allowed_payloads[0]
    # Membership in the second tenant alone does not grant access to its route.
    assert denied_payloads[0]["error_code"] == "permission_denied"


@pytest.mark.parametrize("allowed", [True, False], ids=["allowed", "denied"])
@pytest.mark.parametrize("method,canonical,operation,targets", [
    (
        "post", "/v1.0/m8flow/process-instances/123/suspend", "suspend_instance",
        [("execute", "tenant", "/process-instances/123"), ("read", "tenant", "/process-instances")],
    ),
    ("post", "/v1.0/tasks/123/complete", "complete", [("create", "tenant", "/tasks/123/complete")]),
    ("get", "/v1.0/tasks", "list_pending_tasks", [("read", "tenant", "/tasks")]),
], ids=["lifecycle-post", "task-post", "task-get"])
@pytest.mark.parametrize("separator,trailing,initial_status", [
    ("/", "", 200),
    ("//", "", 308),
    ("%2F", "", 200),
    ("%2f", "", 200),
    ("%2F/", "", 308),
    # The pinned test transport decodes these separators to the same endpoint.
    ("%252F", "", 200),
    ("/", "//", 404),
], ids=["canonical", "repeated", "encoded-upper", "encoded-lower", "encoded-repeated", "double-encoded", "trailing"])
def test_router_and_authorization_agree_on_noncanonical_paths(
    client, routing_member, monkeypatch, allowed, method, canonical, operation, targets,
    separator, trailing, initial_status,
):
    user_id, tenant_id, headers = routing_member
    permission_calls = []
    dispatches = []

    def permitted(session, user, action, resource_type, resource_id):
        assert session is not None
        assert user.id == user_id
        permission_calls.append((action, resource_type, resource_id))
        return allowed

    monkeypatch.setattr(authorization, "_resource_permitted", permitted)

    def dispatched(session, **kwargs):
        assert session is not None
        dispatches.append((request.endpoint, request.view_args, request.method, request.path, kwargs))
        if operation == "suspend_instance":
            return SimpleNamespace(id=123, status="suspended")
        if operation == "complete":
            return SimpleNamespace(process_instance_id=123, status="waiting")
        return []

    workflow_spies = {}
    for name in ("suspend_instance", "complete", "list_pending_tasks", "list_pending_tasks_for_super_admin"):
        workflow_spies[name] = Mock(side_effect=dispatched)
        monkeypatch.setattr(workflow, name, workflow_spies[name])

    payload = {"answer": "approved"}
    options = {"headers": headers, "follow_redirects": False}
    if method == "post":
        options["json"] = payload

    # Always prove the canonical control reaches this endpoint or its permission
    # gate, including for URL variants that are rejected before authorization.
    control = getattr(client, method)(canonical, **options)
    assert control.status_code == (200 if allowed else 403)
    assert permission_calls == (targets if allowed else targets[:1])
    if allowed:
        expected_kwargs = {"tenant_id": tenant_id, "user_id": user_id}
        if operation == "suspend_instance":
            expected_kwargs["process_instance_id"] = 123
        elif operation == "complete":
            expected_kwargs.update(work_item_id=123, task_payload=payload)
        assert len(dispatches) == 1
        assert dispatches[0][2:] == (method.upper(), canonical, expected_kwargs)
        workflow_spies[operation].assert_called_once()
    else:
        assert control.get_json()["error_code"] == "permission_denied"
        assert dispatches == []
    canonical_dispatches = dispatches.copy()
    canonical_permissions = permission_calls.copy()
    permission_calls.clear()
    dispatches.clear()
    for spy in workflow_spies.values():
        spy.reset_mock()

    # Pass the encoded/repeated separators to the client unchanged. A leading
    # slash stays literal so the URL cannot be interpreted as another authority.
    path = "/" + separator.join(canonical.lstrip("/").split("/")) + trailing
    # Connexion redirects trailing slashes on its API operation; the plain
    # Flask task routes reject them. These are deliberately separate outcomes.
    if trailing and operation == "suspend_instance":
        initial_status = 307
    response = getattr(client, method)(path, **options)
    expected_status = 403 if initial_status == 200 and not allowed else initial_status
    assert response.status_code == expected_status
    if initial_status == 308:
        # The host HTTPException handler renders Flask's merge-slash redirect
        # as JSON without Location. It is terminal and must not dispatch.
        assert response.headers.get("location") is None
        assert response.get_json() == {
            "error_code": "permanent_redirect", "message": f"http://testserver{canonical}",
        }
    elif initial_status == 307:
        assert permission_calls == []
        assert dispatches == []
        for spy in workflow_spies.values():
            spy.assert_not_called()
        location = urlsplit(response.headers["location"])
        assert (location.scheme, location.netloc, location.path, location.query, location.fragment) == (
            "http", "testserver", canonical, "", "",
        )
        # Follow only a method-preserving redirect, with the original POST body.
        response = getattr(client, method)(response.headers["location"], **options)
        assert response.status_code == (200 if allowed else 403)
    else:
        assert response.headers.get("location") is None

    if initial_status in {308, 404}:
        assert permission_calls == []
        assert dispatches == []
        for spy in workflow_spies.values():
            spy.assert_not_called()
    else:
        assert permission_calls == canonical_permissions
        assert dispatches == canonical_dispatches
        assert response.get_json() == control.get_json()
        for name, spy in workflow_spies.items():
            assert spy.call_count == int(allowed and name == operation)
