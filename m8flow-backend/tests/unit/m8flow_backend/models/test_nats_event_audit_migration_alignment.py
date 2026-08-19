"""Assert the m8flow_nats_event_audit migration and the SQLAlchemy model agree.

The model and the DDL are written by hand in two places, so nothing but a test stops them
drifting. Drift here is quiet and nasty: a column the model declares NOT NULL but the table
allows NULL (or vice versa) surfaces as an insert failure in production rather than at
import, and a type mismatch on ``stream_seq`` would truncate JetStream sequences, which are
uint64.

The timestamp columns get particular attention because they arrive from ``AuditDateTimeMixin``
rather than from the model body, which makes them the easiest pair to forget when either side
is edited. They carry no server default on purpose: values come from Spiff's before_insert /
before_update listeners, wired in ``m8flow_backend.models._timestamps_bootstrap``.

Rather than re-listing the expected schema (which would just be a third copy to drift), this
executes the migration's ``upgrade()`` against a recorder standing in for ``alembic.op`` and
compares what it would create against the model's mapped metadata.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.nats_event_audit import NatsEventAuditModel  # noqa: E402

MIGRATION_PATH = (
    extension_root / "migrations" / "versions" / "q0j1k2l3m4n5_add_nats_event_audit.py"
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
    def f(name):
        """Alembic's naming-convention helper; identity is right for explicit names."""
        return name

    @staticmethod
    def get_bind():
        raise AssertionError("the migration must not touch a database in this test")


@pytest.fixture(scope="module")
def migration():
    """Load the migration module and capture what ``upgrade()`` would create."""
    spec = importlib.util.spec_from_file_location("_nats_audit_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    recorder = _OpRecorder()
    module.op = recorder
    # The real guard inspects the live database; here the table is always absent.
    module._table_exists = lambda _table_name: False
    module.upgrade()

    assert recorder.table_name is not None, "upgrade() created no table"
    return recorder


@pytest.fixture(scope="module")
def migration_columns(migration) -> dict[str, sa.Column]:
    return {column.name: column for column in migration.columns}


@pytest.fixture(scope="module")
def model_columns() -> dict[str, sa.Column]:
    return {column.name: column for column in NatsEventAuditModel.__table__.columns}


def test_the_migration_targets_the_models_table(migration) -> None:
    assert migration.table_name == NatsEventAuditModel.__tablename__


def test_neither_side_has_a_column_the_other_lacks(migration_columns, model_columns) -> None:
    assert set(migration_columns) == set(model_columns)


def test_column_types_match(migration_columns, model_columns) -> None:
    """Compared by compiled SQL type, so Integer vs BigInteger cannot slip through."""
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
    """Only ``duplicate_count`` carries one; a stray default elsewhere is drift."""

    def rendered(column: sa.Column) -> str | None:
        default = column.server_default
        return None if default is None else str(default.arg)

    mismatched = {
        name: (rendered(migration_columns[name]), rendered(column))
        for name, column in model_columns.items()
        if rendered(migration_columns[name]) != rendered(column)
    }
    assert not mismatched, f"server-default drift (migration, model): {mismatched}"


@pytest.mark.parametrize("name", ["created_at_in_seconds", "updated_at_in_seconds"])
def test_audit_timestamps_are_not_null_integers_with_no_server_default(
    name, migration_columns, model_columns
) -> None:
    """The mixin-supplied pair, called out because it is the easiest to overlook.

    NOT NULL with no server default is load-bearing: it means a row inserted without the
    listeners attached fails loudly instead of persisting an unattributable timestamp.
    """
    for source, columns in (("migration", migration_columns), ("model", model_columns)):
        column = columns[name]
        assert isinstance(column.type, sa.Integer), f"{source}: {name} is not an Integer"
        assert column.nullable is False, f"{source}: {name} should be NOT NULL"
        assert column.server_default is None, f"{source}: {name} should have no server default"


def _constraint_column_names(constraint) -> tuple[str, ...]:
    """Column names for a constraint, bound to a table or not.

    The migration builds its constraints from bare strings and never attaches them to a
    Table, so ``.columns`` is empty there and the names are still sitting in
    ``_pending_colargs``; the model's are fully bound.
    """
    if len(constraint.columns) > 0:
        return tuple(column.name for column in constraint.columns)
    pending = getattr(constraint, "_pending_colargs", ())
    return tuple(col if isinstance(col, str) else col.name for col in pending)


def test_the_unique_constraint_matches(migration) -> None:
    migration_uniques = {
        (constraint.name, _constraint_column_names(constraint))
        for constraint in migration.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    model_uniques = {
        (constraint.name, _constraint_column_names(constraint))
        for constraint in NatsEventAuditModel.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert migration_uniques == model_uniques
    assert model_uniques, "the unique constraint disappeared from both sides"


def test_every_model_index_is_created_by_the_migration(migration) -> None:
    """Indexes declared via ``index=True`` land in the model's metadata too, so this covers
    the single-column ones (tenant_id, outcome) as well as the composites."""
    migration_indexes = {(name, tuple(columns)) for name, columns, _ in migration.indexes}
    model_indexes = {
        (index.name, tuple(column.name for column in index.columns))
        for index in NatsEventAuditModel.__table__.indexes
    }
    assert model_indexes == migration_indexes


def test_no_migration_index_is_accidentally_unique(migration) -> None:
    """Uniqueness belongs to the named constraint; a unique index would be a silent change."""
    unique_indexes = [name for name, _, unique in migration.indexes if unique]
    assert not unique_indexes
