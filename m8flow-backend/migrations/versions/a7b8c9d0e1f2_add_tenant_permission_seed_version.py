"""Track the canonical permission seed version per tenant.

Request-time permission repair used to infer outdated seed state by checking for
individual expected grants. That caused a missing or intentionally revoked grant
to trigger a full YAML re-import on a later request. This marker allows one
canonical upgrade pass per tenant and leaves subsequent operator changes alone.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

TABLE = "m8flow_tenant_permission_seed"


def upgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("seed_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("m8f_tenant_id", name="pk_host_m8flow_tenant_permission_seed"),
    )


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
