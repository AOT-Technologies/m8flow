"""Assert the m8flow_celery_task migration and the SQLAlchemy model agree.

The model and the migration DDL are written in two places, so nothing but a test
stops them from drifting.

This executes the migration's ``upgrade()`` against an ``_OpRecorder`` (capturing
what DDL would be emitted) as well as against a real SQLite engine, and compares
the created table, columns, types, nullability, constraints, and indexes against
the model's mapped metadata.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from m8flow_backend.models.celery_task import INDEXED_COLUMNS as MODEL_INDEXED_COLUMNS, CeleryTaskModel

MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "migrations"
    / "versions"
    / "a8c1e2f3b4d5_add_celery_task_history.py"
)


class _OpRecorder:
    """Stands in for ``alembic.op``: records the DDL instead of emitting it."""

    def __init__(self) -> None:
        self.table_name: str | None = None
        self.columns: list[sa.Column] = []
        self.constraints: list = []
        self.indexes: list[tuple[str, list[str], bool]] = []

    def create_table(self, table_name, *args, **kwargs):
        self.table_name = table_name
        for arg in args:
            if isinstance(arg, sa.Column):
                self.columns.append(arg)
            else:
                self.constraints.append(arg)

    def create_index(self, index_name, table_name, columns, unique=False, **kwargs):
        self.indexes.append((index_name, list(columns), unique))

    @staticmethod
    def get_bind():
        raise AssertionError("the migration must not touch a database in recorder mode")


@pytest.fixture(scope="module")
def migration_module():
    spec = importlib.util.spec_from_file_location("_celery_task_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration_recorder(migration_module):
    """Load the migration module and capture what ``upgrade()`` would create."""
    recorder = _OpRecorder()
    migration_module.op = recorder
    migration_module._table_exists = lambda: False
    migration_module.upgrade()

    assert recorder.table_name is not None, "upgrade() created no table"
    return recorder


@pytest.fixture(scope="module")
def migration_columns(migration_recorder) -> dict[str, sa.Column]:
    return {column.name: column for column in migration_recorder.columns}


@pytest.fixture(scope="module")
def model_columns() -> dict[str, sa.Column]:
    return {column.name: column for column in CeleryTaskModel.__table__.columns}


def test_migration_targets_model_table(migration_recorder) -> None:
    assert migration_recorder.table_name == CeleryTaskModel.__tablename__ == "m8flow_celery_task"


def test_column_names_match_exactly(migration_columns, model_columns) -> None:
    assert set(migration_columns) == set(model_columns)


def test_column_types_match(migration_columns, model_columns) -> None:
    """Compared by compiled SQL type string so type drift cannot slip through."""
    mismatched = {
        name: (str(migration_columns[name].type), str(column.type))
        for name, column in model_columns.items()
        if str(migration_columns[name].type) != str(column.type)
    }
    assert not mismatched, f"type drift (migration, model): {mismatched}"


def test_column_nullability_matches(migration_columns, model_columns) -> None:
    mismatched = {
        name: (migration_columns[name].nullable, column.nullable)
        for name, column in model_columns.items()
        if migration_columns[name].nullable != column.nullable
    }
    assert not mismatched, f"nullability drift (migration, model): {mismatched}"


def test_server_defaults_match(migration_columns, model_columns) -> None:
    """A database default in one and not the other is drift too (updated_at has one)."""
    mismatched = {
        name: (migration_columns[name].server_default is not None, column.server_default is not None)
        for name, column in model_columns.items()
        if (migration_columns[name].server_default is None) != (column.server_default is None)
    }
    assert not mismatched, f"server default drift (migration, model): {mismatched}"
    assert model_columns["updated_at"].server_default is not None


def test_primary_key_constraint_matches(migration_recorder) -> None:
    pk_constraints = [
        c for c in migration_recorder.constraints if isinstance(c, sa.PrimaryKeyConstraint)
    ]
    assert len(pk_constraints) == 1
    pk = pk_constraints[0]
    expected_pk_name = f"pk_host_{CeleryTaskModel.__tablename__}"
    assert pk.name == expected_pk_name
    model_pk_cols = [c.name for c in CeleryTaskModel.__table__.primary_key.columns]
    assert model_pk_cols == ["task_id"]


def test_model_indexed_columns_match_migration_contract(migration_module, migration_recorder) -> None:
    """The migration's INDEXED_COLUMNS tuple, the model's INDEXED_COLUMNS contract,
    the model's index=True columns, and the migration's op.create_index calls must all agree.
    """
    model_columns_with_index = {
        col.name for col in CeleryTaskModel.__table__.columns if col.index
    }
    model_table_index_columns = {
        tuple(col.name for col in index.columns) for index in CeleryTaskModel.__table__.indexes
    }

    # Model declarations internal consistency
    assert set(MODEL_INDEXED_COLUMNS) == model_columns_with_index
    assert set(CeleryTaskModel.INDEXED_COLUMNS) == model_columns_with_index
    assert model_table_index_columns == {(c,) for c in MODEL_INDEXED_COLUMNS}

    # Migration vs Model contract
    assert set(migration_module.INDEXED_COLUMNS) == model_columns_with_index

    # op.create_index recordings
    recorded_indexed_cols = {tuple(cols) for _, cols, _ in migration_recorder.indexes}
    assert recorded_indexed_cols == model_table_index_columns


def test_index_names_match_host_base_naming_convention(migration_recorder) -> None:
    """HostBase uses ix_host_%(column_0_label)s which compiles to ix_host_<table_name>_<col>."""
    model_indexes = {
        (index.name, tuple(col.name for col in index.columns))
        for index in CeleryTaskModel.__table__.indexes
    }
    migration_indexes = {
        (name, tuple(cols)) for name, cols, _ in migration_recorder.indexes
    }
    assert model_indexes == migration_indexes
    expected_names = {
        f"ix_host_m8flow_celery_task_{col}" for col in MODEL_INDEXED_COLUMNS
    }
    assert {name for name, _ in model_indexes} == expected_names


def test_no_migration_index_is_unique(migration_recorder) -> None:
    unique_indexes = [name for name, _, unique in migration_recorder.indexes if unique]
    assert not unique_indexes, f"indexes should not be unique: {unique_indexes}"


def test_live_engine_upgrade_and_downgrade(tmp_path, migration_module) -> None:
    """Run upgrade() and downgrade() against a real SQLite database to verify DDL execution."""
    db_path = tmp_path / "celery_contract.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    # Fresh DB: table does not exist
    inspector = sa.inspect(engine)
    assert "m8flow_celery_task" not in inspector.get_table_names()

    # Apply upgrade
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration_module.op = Operations(context)
            migration_module._table_exists = lambda: sa.inspect(connection).has_table(
                "m8flow_celery_task"
            )
            migration_module.upgrade()

    # Verify table and indexes on live database
    inspector = sa.inspect(engine)
    assert "m8flow_celery_task" in inspector.get_table_names()

    db_columns = {col["name"]: col for col in inspector.get_columns("m8flow_celery_task")}
    assert set(db_columns.keys()) == {col.name for col in CeleryTaskModel.__table__.columns}

    db_indexes = inspector.get_indexes("m8flow_celery_task")
    db_index_map = {idx["name"]: tuple(idx["column_names"]) for idx in db_indexes}
    expected_index_map = {
        f"ix_host_m8flow_celery_task_{col}": (col,) for col in MODEL_INDEXED_COLUMNS
    }
    assert db_index_map == expected_index_map

    # Test idempotency (calling upgrade again does not fail)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration_module.op = Operations(context)
            migration_module._table_exists = lambda: sa.inspect(connection).has_table(
                "m8flow_celery_task"
            )
            migration_module.upgrade()

    assert "m8flow_celery_task" in sa.inspect(engine).get_table_names()

    # Test downgrade
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration_module.op = Operations(context)
            migration_module._table_exists = lambda: sa.inspect(connection).has_table(
                "m8flow_celery_task"
            )
            migration_module.downgrade()

    assert "m8flow_celery_task" not in sa.inspect(engine).get_table_names()
