# SPDX-License-Identifier: Apache-2.0
"""Mirror the core collaboration migration in the host schema."""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_TABLE = "process_instance"
_COLUMN = "collaboration_correlation_key"
_INDEX = "ix_process_instance_collaboration_lookup"


def upgrade() -> None:
    # Fresh databases may already have the column and index via create_all().
    # The host revision tracks this addition. The separate core baseline marker
    # is used by the legacy schema handoff and pre-squash recovery.
    inspector = sa.inspect(op.get_bind())
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(255), nullable=True))
    if _INDEX not in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["m8f_tenant_id", "bpmn_process_definition_id", "bpmn_version_id", _COLUMN])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
