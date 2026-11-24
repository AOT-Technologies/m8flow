"""Move the core migration marker out of Alembic's generic version table.

The 0.2.1 handoff originally used ``alembic_version`` for the core marker,
while M8Flow's Alembic environment owns ``alembic_version_m8flow``. Keep the
legacy table untouched and copy only an unambiguous sole core marker into the
dedicated table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from m8flow_backend.migration_compatibility import compatible_core_revision, core_revision


revision = "d6e7f8a9b0c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

CORE_VERSION_TABLE = "m8flow_core_alembic_version"
LEGACY_CORE_VERSION_TABLE = "alembic_version"
REQUIRED_CORE_MIGRATION = "k2l3m4n5o6p7"
# Host migration replay can encounter the additive message schema already installed.
# core_message_schema normalizes these markers after installing that schema.
COMPATIBLE_CORE_REVISIONS = (REQUIRED_CORE_MIGRATION, "message_correlation")


def _bind():
    return op.get_bind()


def _has_table(name: str) -> bool:
    return name in sa.inspect(_bind()).get_table_names()


def _table(name: str, *columns: str) -> sa.TableClause:
    """Build a SQLAlchemy Core table clause for migration-only SQL."""
    return sa.table(name, *(sa.column(column) for column in columns))


def _ensure_core_version_table() -> None:
    if _has_table(CORE_VERSION_TABLE):
        return
    op.create_table(
        CORE_VERSION_TABLE,
        sa.Column("version_num", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("version_num"),
    )


def _record_core_head() -> None:
    _ensure_core_version_table()
    core_version = _table(CORE_VERSION_TABLE, "version_num")
    recorded = _bind().scalars(sa.select(core_version.c.version_num)).all()
    if not any(compatible_core_revision(_bind(), value) in COMPATIBLE_CORE_REVISIONS for value in recorded):
        _bind().execute(
            sa.insert(core_version).values(version_num=REQUIRED_CORE_MIGRATION)
        )


def upgrade() -> None:
    if _has_table(LEGACY_CORE_VERSION_TABLE):
        legacy_version = _table(LEGACY_CORE_VERSION_TABLE, "version_num")
        legacy_revisions = list(
            _bind().execute(sa.select(legacy_version.c.version_num)).scalars().all()
        )
        normalized = [core_revision(value) for value in legacy_revisions]
        if set(normalized).intersection(COMPATIBLE_CORE_REVISIONS) and len(legacy_revisions) != 1:
            raise RuntimeError(
                "Legacy alembic_version contains mixed host/core revisions; "
                f"move the core marker to {CORE_VERSION_TABLE} before upgrading: "
                f"found {legacy_revisions!r}"
            )
        for value in legacy_revisions:
            compatible_core_revision(_bind(), value)
    _record_core_head()


def downgrade() -> None:
    if not _has_table(CORE_VERSION_TABLE):
        return
    core_version = _table(CORE_VERSION_TABLE, "version_num")
    _bind().execute(
        sa.delete(core_version).where(core_version.c.version_num == REQUIRED_CORE_MIGRATION)
    )
    if _bind().execute(sa.select(core_version.c.version_num).limit(1)).scalar() is None:
        op.drop_table(CORE_VERSION_TABLE)
