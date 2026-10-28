"""The m8flow_process_model_version migration and its model must build the same table.

The migration skips `create_table` when the root revision already built the table
from the ORM metadata, so the two definitions must not drift.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from m8flow_backend.models.process_model_version import ProcessModelVersionModel

MIGRATION_PATH = (
    Path(__file__).resolve().parents[4] / "migrations" / "versions" / "c9d0e1f2a3b4_add_process_model_version.py"
)
TABLE = ProcessModelVersionModel.__tablename__


def _shape(engine: sa.Engine) -> dict:
    inspector = sa.inspect(engine)
    return {
        "columns": {(c["name"], str(c["type"]), c["nullable"]) for c in inspector.get_columns(TABLE)},
        "unique": {(u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(TABLE)},
        "indexes": {(i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(TABLE)},
    }


def test_migration_and_model_build_the_same_table(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("_process_model_version_migration", MIGRATION_PATH)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    migrated = sa.create_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    with migrated.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    modelled = sa.create_engine(f"sqlite:///{tmp_path / 'modelled.db'}")
    ProcessModelVersionModel.__table__.create(modelled)

    assert _shape(migrated) == _shape(modelled)
