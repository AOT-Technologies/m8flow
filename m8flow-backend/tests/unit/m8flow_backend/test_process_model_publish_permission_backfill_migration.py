"""Regression tests for the publish / version-history grant backfill in c9d0e1f2a3b4."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_HERE = Path(__file__).resolve()
_MIGRATION_PATH = _HERE.parents[3] / "migrations" / "versions" / "c9d0e1f2a3b4_add_process_model_versions.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_backfills_publish_grants_idempotently_and_keeps_denies():
    # Same minimal core schema as the Task Review/Home backfill test.
    schema = _load(_HERE.with_name("test_task_review_home_permission_backfill_migration.py"), "_backfill_schema")._schema
    migration = _load(_MIGRATION_PATH, "process_model_publish_permission_migration")
    engine = sa.create_engine("sqlite://")
    schema(engine)

    with engine.begin() as connection:
        meta = sa.MetaData()
        groups, principals, targets, assignments, markers, tenants = (
            sa.Table(name, meta, autoload_with=connection)
            for name in (
                "group",
                "principal",
                "permission_target",
                "permission_assignment",
                "m8flow_tenant_permission_seed",
                "m8flow_tenant",
            )
        )
        connection.execute(tenants.insert(), [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}])
        connection.execute(
            groups.insert(),
            [{"id": 1, "name": "t1:editor", "identifier": "t1:editor", "authorization_key": "authorization:t1:editor"}],
        )
        connection.execute(principals.insert(), [{"id": 11, "user_id": None, "group_id": 1}])
        connection.execute(
            targets.insert(),
            [{"id": 101, "command": "create", "resource_type": "tenant", "resource_id": "/process-model-publish/%"}],
        )
        # Maker-checker: an operator removed publish from t1's editors. The backfill must not re-grant it.
        connection.execute(
            assignments.insert(),
            [{"id": 201, "principal_id": 11, "permission_target_id": 101, "grant_type": "deny", "permission": "create"}],
        )
        # t1 seeded before this PR, t2 never seeded, t3 already current.
        connection.execute(markers.insert(), [{"m8f_tenant_id": "t1", "seed_version": 3}, {"m8f_tenant_id": "t3", "seed_version": 4}])

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        grants = connection.execute(
            sa.select(groups.c.identifier, targets.c.command, targets.c.resource_id, assignments.c.grant_type).select_from(
                assignments.join(principals, principals.c.id == assignments.c.principal_id)
                .join(groups, groups.c.id == principals.c.group_id)
                .join(targets, targets.c.id == assignments.c.permission_target_id)
            )
        ).all()
        marker_rows = connection.execute(
            sa.select(markers.c.m8f_tenant_id, markers.c.seed_version).order_by(markers.c.m8f_tenant_id)
        ).all()
        target_count = connection.execute(sa.select(sa.func.count()).select_from(targets)).scalar_one()

    # Per tenant below v4: versions read x3 roles + versions update x2 + publish create x2.
    assert len(grants) == 14
    assert target_count == 3
    assert not any(row.identifier.startswith("t3:") for row in grants)
    assert ("t1:editor", "create", "/process-model-publish/%", "deny") in grants
    assert ("t2:editor", "create", "/process-model-publish/%", "permit") in grants
    assert ("t1:viewer", "read", "/process-model-versions/%", "permit") in grants
    assert not any(row.identifier.endswith(":viewer") and row.command != "read" for row in grants)
    assert marker_rows == [("t1", 4), ("t3", 4)]  # t2 stays unmarked for its full request-time seed
