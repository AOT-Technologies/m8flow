"""YAML grant boundary for tenant-admin members/groups/roles.

`_uri_permitted` is the seam (same as test_v1_permission_gaps): it reads DB
rows from m8flow.yml and never consults `_group_identifier_fallback`, which
would otherwise let tenant-admin (and editor) through on every path.
"""

from __future__ import annotations

from sqlalchemy import select

from m8flow_bpmn_core.services.authorization import (
    build_authorization_request,
    find_or_create_principal_for_group,
)
from m8flow_bpmn_core.models.permission_assignment import PermissionAssignmentModel
from m8flow_bpmn_core.models.permission_target import PermissionTargetModel
from m8flow_bpmn_core.models.principal import PrincipalModel

from m8flow_backend import identity
from m8flow_backend.authorization import HostAuthorizationPolicy, _resource_permitted
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_TENANT_ID = "t1"
_SERVICE = "https://example.test/realms/m8flow"

_MEMBER_PATHS = (
    f"/m8flow/tenants/{_TENANT_ID}/members",
    f"/m8flow/tenants/{_TENANT_ID}/members/alice",
    f"/m8flow/tenants/{_TENANT_ID}/members/alice/roles/submitter",
    f"/m8flow/tenants/{_TENANT_ID}/available-users",
    f"/m8flow/tenants/{_TENANT_ID}/groups",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers/members/alice",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers/roles/submitter",
)

_INVITATION_PATHS = (
    f"/m8flow/tenants/{_TENANT_ID}/invitations",
    f"/m8flow/tenants/{_TENANT_ID}/invitations/inv-1",
    f"/m8flow/tenants/{_TENANT_ID}/invitations/inv-1/resend",
)


def _resource_path_permitted(session, user, action: str, path: str) -> bool:
    """Exercise the canonical resource-pair authorization seam.

    The YAML grants still use route-shaped resource IDs for this legacy host
    surface, but authorization itself must go through explicit resource
    fields rather than a URI-target API.
    """
    return _resource_permitted(session, user, action, "tenant", path)


def _provision_tenant_role(db_session, *, username: str, group_name: str):
    tenant = ensure_tenant(db_session, tenant_id=_TENANT_ID, slug=_TENANT_ID)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"{_TENANT_ID}:{group_name}"], tenant_id=_TENANT_ID)
    identity.import_yaml(db_session, tenant_id=_TENANT_ID)
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _grant_resource_permission(
    db_session,
    *,
    user,
    group_name: str,
    command: str,
    resource_type: str,
    resource_id: str,
    permission: str,
):
    group = next(group for group in user.groups if group.identifier == f"{_TENANT_ID}:{group_name}")
    principal = find_or_create_principal_for_group(db_session, group_id=group.id)
    target = PermissionTargetModel(
        command=command,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db_session.add(target)
    db_session.flush()
    db_session.add(
        PermissionAssignmentModel(
            principal_id=principal.id,
            permission_target_id=target.id,
            permission=permission,
            grant_type="permit",
        )
    )
    db_session.commit()


def test_tenant_admin_yaml_grants_members_groups_and_roles(db_session):
    user = _provision_tenant_role(db_session, username="tadmin-yaml", group_name="tenant-admin")
    for path in _MEMBER_PATHS:
        for action in ("read", "create", "update", "delete"):
            if path.endswith("/available-users") and action != "read":
                continue
            assert _resource_path_permitted(db_session, user, action, path) is True, (action, path)


def test_tenant_admin_yaml_does_not_grant_invitation_management(db_session):
    """Invitation HTTP stays super-admin-only. Do not add read/create/delete
    YAML rows for invitations. `update /m8flow/tenants/*` (rename) already
    prefix-matches invitation paths; there is no PUT invitation route."""
    user = _provision_tenant_role(db_session, username="tadmin-invites", group_name="tenant-admin")
    for path in _INVITATION_PATHS:
        for action in ("read", "create", "delete"):
            assert _resource_path_permitted(db_session, user, action, path) is False, (action, path)


def test_editor_yaml_does_not_grant_members_or_groups(db_session):
    user = _provision_tenant_role(db_session, username="editor-yaml-members", group_name="editor")
    for path in _MEMBER_PATHS:
        assert _resource_path_permitted(db_session, user, "read", path) is False, path
        assert _resource_path_permitted(db_session, user, "create", path) is False, path


def test_tenant_admin_yaml_does_not_grant_tenant_registry_reads(db_session):
    """read on members/groups must not open super-admin registry GET by id."""
    user = _provision_tenant_role(db_session, username="tadmin-registry", group_name="tenant-admin")
    for path in ("/m8flow/tenants", f"/m8flow/tenants/{_TENANT_ID}", f"/m8flow/tenants/slug/{_TENANT_ID}"):
        assert _resource_path_permitted(db_session, user, "read", path) is False, path


def test_tenant_admin_can_start_concrete_process_model_from_tenant_grant(db_session):
    """The host's tenant-wide start grant must satisfy core's model target."""
    user = _provision_tenant_role(db_session, username="tadmin-start", group_name="tenant-admin")
    request = build_authorization_request(
        tenant_id=_TENANT_ID,
        actor_user_id=user.id,
        command_key="process.start",
        resource_id="Test/single-approval15",
    )

    decision = HostAuthorizationPolicy().authorize(db_session, request)

    assert decision.allowed is True


def test_seeded_yaml_allows_process_definition_import_and_process_start(db_session):
    """Typed import and start requests work against seeded YAML targets."""
    user = _provision_tenant_role(db_session, username="editor-seeded-commands", group_name="editor")
    policy = HostAuthorizationPolicy()

    import_request = build_authorization_request(
        tenant_id=_TENANT_ID,
        actor_user_id=user.id,
        command_key="process_definition.import",
        resource_id="Test/imported-model",
    )
    start_request = build_authorization_request(
        tenant_id=_TENANT_ID,
        actor_user_id=user.id,
        command_key="process.start",
        resource_id="Test/imported-model",
    )

    assert import_request.resource_type == "process_definition"
    assert policy.authorize(db_session, import_request).allowed is True
    assert start_request.resource_type == "process_model"
    assert policy.authorize(db_session, start_request).allowed is True


def test_legacy_null_resource_type_remains_tenant_scoped(db_session):
    """Legacy URI grants with no type remain usable without becoming wildcards."""
    user = _provision_tenant_role(db_session, username="legacy-target", group_name="editor")
    group = next(group for group in user.groups if group.identifier == f"{_TENANT_ID}:editor")
    principal = db_session.scalars(
        select(PrincipalModel).where(PrincipalModel.group_id == group.id)
    ).one()
    target = PermissionTargetModel(
        command="legacy-route-read",
        resource_type="tenant",
        resource_id="/legacy-resource/%",
    )
    db_session.add(target)
    db_session.flush()
    db_session.add(
        PermissionAssignmentModel(
            principal_id=principal.id,
            permission_target_id=target.id,
            permission="read",
            grant_type="permit",
        )
    )
    db_session.commit()
    # Core 0.2.1 rejects this state at the ORM/database boundary. Emulate a
    # row from before typed targets were introduced without weakening the
    # current schema constraints.
    target.__dict__["resource_type"] = None

    assert _resource_path_permitted(db_session, user, "read", "/legacy-resource/42") is True
    assert _resource_permitted(
        db_session,
        user,
        "read",
        "process_definition",
        "/legacy-resource/42",
    ) is False


def test_unknown_resource_type_does_not_fall_back_to_tenant(db_session):
    """Malformed typed targets must fail closed rather than regain URI access."""
    user = _provision_tenant_role(db_session, username="unknown-target", group_name="editor")
    group = next(group for group in user.groups if group.identifier == f"{_TENANT_ID}:editor")
    principal = db_session.scalars(
        select(PrincipalModel).where(PrincipalModel.group_id == group.id)
    ).one()
    target = PermissionTargetModel(
        command="unknown-resource-type",
        resource_type="tenant",
        resource_id="/unknown-resource/%",
    )
    db_session.add(target)
    db_session.flush()
    db_session.add(
        PermissionAssignmentModel(
            principal_id=principal.id,
            permission_target_id=target.id,
            permission="read",
            grant_type="permit",
        )
    )
    db_session.commit()
    target.__dict__["resource_type"] = "legacy-uri"

    assert _resource_path_permitted(db_session, user, "read", "/unknown-resource/42") is False


def test_submitter_can_claim_concrete_task_from_tenant_grant(db_session):
    """Task work uses the same tenant-scoped host grant as task review routes."""
    user = _provision_tenant_role(db_session, username="submitter-claim", group_name="submitter")
    request = build_authorization_request(
        tenant_id=_TENANT_ID,
        actor_user_id=user.id,
        command_key="task.claim",
        resource_id=55,
    )

    decision = HostAuthorizationPolicy().authorize(db_session, request)

    assert decision.allowed is True


def test_process_lifecycle_uses_execute_and_not_create(db_session):
    """Creating process instances must not grant lifecycle control."""
    editor = _provision_tenant_role(db_session, username="editor-lifecycle-policy", group_name="editor")
    tenant_admin = _provision_tenant_role(
        db_session, username="tenant-admin-lifecycle-policy", group_name="tenant-admin"
    )
    submitter = _provision_tenant_role(
        db_session, username="submitter-lifecycle-policy", group_name="submitter"
    )

    for command_key in (
        "process.suspend",
        "process.resume",
        "process.retry",
        "process.terminate",
    ):
        editor_request = build_authorization_request(
            tenant_id=_TENANT_ID,
            actor_user_id=editor.id,
            command_key=command_key,
            resource_id=42,
        )
        submitter_request = build_authorization_request(
            tenant_id=_TENANT_ID,
            actor_user_id=submitter.id,
            command_key=command_key,
            resource_id=42,
        )

        tenant_admin_request = build_authorization_request(
            tenant_id=_TENANT_ID,
            actor_user_id=tenant_admin.id,
            command_key=command_key,
            resource_id=42,
        )
        assert HostAuthorizationPolicy().authorize(db_session, submitter_request).allowed is False
        assert editor_request.permission == "execute"
        assert HostAuthorizationPolicy().authorize(db_session, editor_request).allowed is True
        assert HostAuthorizationPolicy().authorize(db_session, tenant_admin_request).allowed is True

    # The submitter still has the unrelated process-instance create grant.
    assert _resource_path_permitted(db_session, submitter, "create", "/process-instances/42") is True


def test_lifecycle_commands_use_direct_process_instance_resource_grants(db_session):
    """Core-style process_instance/id grants authorize every lifecycle command."""
    user = _provision_tenant_role(db_session, username="direct-lifecycle", group_name="direct-lifecycle")
    policy = HostAuthorizationPolicy()
    commands = ("process.suspend", "process.resume", "process.retry", "process.terminate")

    for command in commands:
        _grant_resource_permission(
            db_session,
            user=user,
            group_name="direct-lifecycle",
            command=command,
            resource_type="process_instance",
            resource_id="42",
            permission="execute",
        )
        request = build_authorization_request(
            tenant_id=_TENANT_ID,
            actor_user_id=user.id,
            command_key=command,
            resource_id=42,
        )

        assert request.resource_type == "process_instance"
        assert request.permission == "execute"
        assert policy.authorize(db_session, request).allowed is True


def test_lifecycle_commands_use_seeded_tenant_route_fallback(db_session):
    """Host YAML route grants authorize core's concrete lifecycle requests."""
    user = _provision_tenant_role(db_session, username="route-lifecycle", group_name="editor")
    policy = HostAuthorizationPolicy()

    for command in ("process.suspend", "process.resume", "process.retry", "process.terminate"):
        request = build_authorization_request(
            tenant_id=_TENANT_ID,
            actor_user_id=user.id,
            command_key=command,
            resource_id=42,
        )

        assert policy.authorize(db_session, request).allowed is True
        assert _resource_path_permitted(
            db_session, user, "execute", "/process-instances/42"
        ) is True
