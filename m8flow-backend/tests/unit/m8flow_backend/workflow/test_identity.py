from __future__ import annotations

import m8flow_bpmn_core.api  # noqa: F401  (prime core import order; avoids a
# circular import when import_yaml -> ensure_v1_role pulls core's authorization
# service in isolation, outside the app bootstrap the other tests rely on)

from m8flow_backend import identity


def test_ensure_membership_replaces_fields(db_session):
    tenant_a = identity.ensure_tenant(db_session, tenant_id="aaa", slug="alpha")
    tenant_b = identity.ensure_tenant(db_session, tenant_id="bbb", slug="beta")
    user = identity.ensure_user(
        db_session, username="editor", service="https://kc/realms/m8flow", service_id="e1"
    )
    identity.ensure_membership(db_session, user, tenant_a)
    assert user.tenant_specific_field_1 == "aaa"
    assert user.tenant_specific_field_2 == "alpha"
    identity.ensure_membership(db_session, user, tenant_b)
    assert user.tenant_specific_field_1 == "bbb"
    assert user.tenant_specific_field_2 == "beta"


def test_unprefixed_groups_except_super_admin_are_ignored(db_session):
    tenant = identity.ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = identity.ensure_user(
        db_session, username="editor", service="https://kc/realms/m8flow", service_id="e1"
    )
    identity.ensure_membership(db_session, user, tenant)
    identity.sync_groups(
        db_session,
        user=user,
        group_identifiers=["editor", "super-admin", "t1:editor"],
        tenant_id="t1",
    )
    db_session.flush()
    db_session.refresh(user)
    identifiers = {group.identifier for group in user.groups}
    assert "super-admin" in identifiers
    assert "t1:editor" in identifiers
    assert "editor" not in identifiers


def _start_grant_permissions(db_session, tenant_id: str, group_suffix: str) -> set[str]:
    from m8flow_bpmn_core.models.group import GroupModel
    from m8flow_bpmn_core.models.permission_assignment import PermissionAssignmentModel
    from m8flow_bpmn_core.models.permission_target import PermissionTargetModel
    from m8flow_bpmn_core.models.principal import PrincipalModel
    from sqlalchemy import select

    rows = db_session.execute(
        select(PermissionAssignmentModel.permission)
        .join(PrincipalModel, PrincipalModel.id == PermissionAssignmentModel.principal_id)
        .join(GroupModel, GroupModel.id == PrincipalModel.group_id)
        .join(
            PermissionTargetModel,
            PermissionTargetModel.id == PermissionAssignmentModel.permission_target_id,
        )
        .where(
            GroupModel.identifier == f"{tenant_id}:{group_suffix}",
            PermissionTargetModel.uri == "/process-models/%",
            PermissionTargetModel.command == "process.start",
        )
    ).all()
    return {r[0] for r in rows}


def test_import_yaml_is_idempotent_and_expands_macros(db_session):
    """Re-running import_yaml must not raise (the (uri, command) unique
    constraint bug) and must seed the PM:ALL macro as /process-models/% with
    the `start` action for run-all-process-models."""
    identity.ensure_tenant(db_session, tenant_id="t1", slug="t1")

    identity.import_yaml(db_session, tenant_id="t1")
    db_session.flush()
    first = _start_grant_permissions(db_session, "t1", "editor")
    assert "start" in first, f"expected a start grant, got {first}"

    # Second run is a no-op re-sync — previously raised UniqueViolation.
    identity.import_yaml(db_session, tenant_id="t1")
    db_session.flush()
    assert _start_grant_permissions(db_session, "t1", "editor") == first


def test_import_yaml_does_not_lookup_permission_target_per_grant(db_session):
    """Second import_yaml must reuse a cached target list, not SELECT by uri."""
    from sqlalchemy import event

    identity.ensure_tenant(db_session, tenant_id="t1", slug="t1")
    identity.import_yaml(db_session, tenant_id="t1")
    db_session.flush()

    statements: list[str] = []
    engine = db_session.get_bind()

    def _before(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", _before)
    try:
        identity.import_yaml(db_session, tenant_id="t1")
        db_session.flush()
    finally:
        event.remove(engine, "before_cursor_execute", _before)

    by_uri = [
        sql
        for sql in statements
        if "permission_target.uri =" in sql.replace('"', "")
    ]
    # Leftover lookups are core `ensure_v1_role`, not per-YAML-grant `grant()`.
    assert len(by_uri) < 20, (len(by_uri), by_uri[:2])


def test_import_yaml_does_not_repeat_group_lookups_within_a_pass(db_session):
    """Each YAML role used to be SELECTed once per permission spec (~400
    group/principal round-trips). Memoize per pass so a re-import stays
    bounded.
    """
    from sqlalchemy import event

    identity.ensure_tenant(db_session, tenant_id="t1", slug="t1")
    identity.import_yaml(db_session, tenant_id="t1")
    db_session.flush()

    statements: list[str] = []
    engine = db_session.get_bind()

    def _before(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", _before)
    try:
        identity.import_yaml(db_session, tenant_id="t1")
        db_session.flush()
    finally:
        event.remove(engine, "before_cursor_execute", _before)

    compacted = [sql.replace('"', "").lower() for sql in statements]
    group_by_identifier = [
        sql for sql in compacted if "from group" in sql and "identifier" in sql
    ]
    principal_by_group = [
        sql for sql in compacted if "from principal" in sql and "group_id" in sql
    ]
    assert len(statements) < 80, len(statements)
    assert len(group_by_identifier) < 20, (len(group_by_identifier), group_by_identifier[:2])
    assert len(principal_by_group) < 20, (len(principal_by_group), principal_by_group[:2])


def test_tenant_yaml_grants_present_after_import(db_session):
    identity.ensure_tenant(db_session, tenant_id="t1", slug="t1")
    assert identity.tenant_yaml_grants_present(db_session, tenant_id="t1") is False
    identity.import_yaml(db_session, tenant_id="t1")
    db_session.flush()
    assert identity.tenant_yaml_grants_present(db_session, tenant_id="t1") is True
    assert identity.tenant_yaml_grants_present(db_session, tenant_id="other") is False
