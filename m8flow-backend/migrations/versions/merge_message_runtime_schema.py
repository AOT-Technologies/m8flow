"""Converge message correlation and upstream runtime schema migrations."""

from alembic import op

from m8flow_backend.migration_compatibility import require_message_schema

revision = "merge_message_runtime_schema"
down_revision = ("merge_message_error_timestamp", "b6c7d8e9f0a1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both branches have now installed their schema, including databases that
    # applied the original message revision before the upstream runtime work.
    require_message_schema(op.get_bind())


def downgrade() -> None:
    pass
