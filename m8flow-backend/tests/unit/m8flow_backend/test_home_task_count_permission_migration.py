"""Regression tests for revoking editor access to Home task counts."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import sqlalchemy as sa
import pytest
from sqlalchemy.dialects import postgresql
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "f6a7b8c9d0e1_revoke_editor_home_task_count.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("home_task_count_permission_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        "group", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("identifier", sa.String)
    )
    sa.Table(
        "principal", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("group_id", sa.Integer)
    )
    sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("command", sa.String),
        sa.Column("resource_type", sa.String),
        sa.Column("resource_id", sa.String),
    )
    sa.Table(
        "permission_assignment",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("principal_id", sa.Integer),
        sa.Column("permission_target_id", sa.Integer),
        sa.Column("grant_type", sa.String),
        sa.Column("permission", sa.String),
    )
    sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String, primary_key=True))
    metadata.create_all(engine)


def test_upgrade_removes_only_editor_home_task_count_read_grants_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.table("group", sa.column("id"), sa.column("identifier")).insert(),
            [
                {"id": 1, "identifier": "tenant-a:editor"},
                {"id": 2, "identifier": "tenant-a:reviewer"},
                {"id": 3, "identifier": "custom:editor"},
                {"id": 4, "identifier": "tenant-a:custom:editor"},
                {"id": 5, "identifier": "editor"},
            ],
        )
        connection.execute(
            sa.table("m8flow_tenant", sa.column("id")).insert(),
            [{"id": "tenant-a"}],
        )
        connection.execute(
            sa.table("principal", sa.column("id"), sa.column("group_id")).insert(),
            [
                {"id": 11, "group_id": 1},
                {"id": 22, "group_id": 2},
                {"id": 33, "group_id": 3},
                {"id": 44, "group_id": 4},
                {"id": 55, "group_id": 5},
            ],
        )
        connection.execute(
            sa.table(
                "permission_target",
                sa.column("id"),
                sa.column("command"),
                sa.column("resource_type"),
                sa.column("resource_id"),
            ).insert(),
            [
                {
                    "id": 101,
                    "command": "read",
                    "resource_type": "tenant",
                    "resource_id": "/m8flow/home-task-count",
                },
                {
                    "id": 102,
                    "command": "read",
                    "resource_type": "tenant",
                    "resource_id": "/m8flow/other-read",
                },
            ],
        )
        connection.execute(
            sa.table(
                "permission_assignment",
                sa.column("id"),
                sa.column("principal_id"),
                sa.column("permission_target_id"),
                sa.column("grant_type"),
                sa.column("permission"),
            ).insert(),
            [
                {
                    "id": 1,
                    "principal_id": 11,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 2,
                    "principal_id": 22,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 3,
                    "principal_id": 11,
                    "permission_target_id": 102,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 4,
                    "principal_id": 33,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 5,
                    "principal_id": 44,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 6,
                    "principal_id": 55,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
            ],
        )

        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        remaining = connection.execute(
            sa.text("SELECT id FROM permission_assignment ORDER BY id")
        ).scalars().all()

    assert remaining == [2, 3, 4, 5]


def test_editor_group_query_quotes_reserved_group_identifier_for_postgresql():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    _schema(engine)

    with engine.connect() as connection:
        sql = str(
            migration._editor_principals_query(connection).compile(
                dialect=postgresql.dialect()
            )
        )

    assert 'JOIN "group"' in sql
    assert 'CAST(m8flow_tenant.id AS VARCHAR) ||' in sql


def test_upgrade_fails_loudly_when_required_authorization_tables_are_missing(caplog):
    engine = sa.create_engine("sqlite://")
    migration = _migration_module()

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with caplog.at_level(logging.ERROR, logger="alembic.runtime.migration"):
                with pytest.raises(RuntimeError, match="required authorization tables are missing"):
                    migration.upgrade()

    assert "m8flow_tenant" in caplog.text
    assert "permission_assignment" in caplog.text
