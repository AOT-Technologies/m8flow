"""Move the core migration marker out of Alembic's generic version table.

The 0.2.1 handoff originally used ``alembic_version`` for the core marker,
while M8Flow's Alembic environment owns ``alembic_version_m8flow``. Keep the
legacy table untouched and copy only an unambiguous sole core marker into the
dedicated table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "d6e7f8a9b0c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

CORE_VERSION_TABLE = "m8flow_core_alembic_version"
LEGACY_CORE_VERSION_TABLE = "alembic_version"
REQUIRED_CORE_MIGRATION = "k2l3m4n5o6p7"


def _bind():
    return op.get_bind()


def _has_table(name: str) -> bool:
    return name in sa.inspect(_bind()).get_table_names()


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
    exists = _bind().execute(
        sa.text(f"SELECT 1 FROM {CORE_VERSION_TABLE} WHERE version_num = :version LIMIT 1"),
        {"version": REQUIRED_CORE_MIGRATION},
    ).scalar()
    if exists is None:
        _bind().execute(
            sa.text(f"INSERT INTO {CORE_VERSION_TABLE} (version_num) VALUES (:version)"),
            {"version": REQUIRED_CORE_MIGRATION},
        )


def upgrade() -> None:
    if _has_table(LEGACY_CORE_VERSION_TABLE):
        legacy_revisions = list(
            _bind()
            .execute(sa.text(f"SELECT version_num FROM {LEGACY_CORE_VERSION_TABLE}"))
            .scalars()
            .all()
        )
        if REQUIRED_CORE_MIGRATION in legacy_revisions and legacy_revisions != [REQUIRED_CORE_MIGRATION]:
            raise RuntimeError(
                "Legacy alembic_version contains mixed host/core revisions; "
                f"move the core marker to {CORE_VERSION_TABLE} before upgrading: "
                f"found {legacy_revisions!r}"
            )
    _record_core_head()


def downgrade() -> None:
    if not _has_table(CORE_VERSION_TABLE):
        return
    _bind().execute(
        sa.text(f"DELETE FROM {CORE_VERSION_TABLE} WHERE version_num = :version"),
        {"version": REQUIRED_CORE_MIGRATION},
    )
    if _bind().execute(sa.text(f"SELECT 1 FROM {CORE_VERSION_TABLE} LIMIT 1")).scalar() is None:
        op.drop_table(CORE_VERSION_TABLE)
