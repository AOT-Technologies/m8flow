"""update the tenant table columns

Revision ID: 2cfce680c743
Revises: 0003
Create Date: 2026-01-21 12:51:49.418203

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '2cfce680c743'
down_revision = '0003'
branch_labels = None
depends_on = None

def _is_postgres():
    return op.get_bind().dialect.name == 'postgresql'


def _column_exists(table, column):
    insp = inspect(op.get_bind())
    return column in [c['name'] for c in insp.get_columns(table)]


def _constraint_exists(table, name):
    insp = inspect(op.get_bind())
    return any(c['name'] == name for c in insp.get_unique_constraints(table))


def _index_exists(table, name):
    insp = inspect(op.get_bind())
    return any(idx['name'] == name for idx in insp.get_indexes(table))


def upgrade():
    if _is_postgres():
        # Idempotent: create enum only if it does not exist (e.g. after version reset).
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenantstatus') THEN
                    CREATE TYPE tenantstatus AS ENUM ('ACTIVE', 'INACTIVE', 'DELETED');
                END IF;
            END
            $$;
        """)

    # Add slug column (idempotent)
    if not _column_exists('m8flow_tenant', 'slug'):
        op.add_column('m8flow_tenant', sa.Column('slug', sa.String(length=255), nullable=True))

    # Add status column (PostgreSQL: native ENUM; SQLite: string)
    if not _column_exists('m8flow_tenant', 'status'):
        if _is_postgres():
            op.add_column('m8flow_tenant',
                sa.Column('status',
                          postgresql.ENUM('ACTIVE', 'INACTIVE', 'DELETED', name='tenantstatus'),
                          nullable=True,
                          server_default='ACTIVE'))
        else:
            op.add_column('m8flow_tenant',
                sa.Column('status', sa.String(length=20), nullable=True, server_default='ACTIVE'))

    # Alter existing created_at (PostgreSQL: timezone-aware; SQLite: keep DateTime)
    if _is_postgres():
        op.alter_column('m8flow_tenant', 'created_at',
                        type_=sa.DateTime(timezone=True),
                        existing_type=sa.DateTime(),
                        existing_nullable=False,
                        existing_server_default=sa.text('now()'))

    # Add modified_at column (SQLite: no server_default on add, backfill below)
    if not _column_exists('m8flow_tenant', 'modified_at'):
        if _is_postgres():
            op.add_column('m8flow_tenant',
                sa.Column('modified_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
        else:
            op.add_column('m8flow_tenant',
                sa.Column('modified_at', sa.DateTime(), nullable=True))

    # Add created_by column
    if not _column_exists('m8flow_tenant', 'created_by'):
        op.add_column('m8flow_tenant', sa.Column('created_by', sa.String(length=255), nullable=True))

    # Add modified_by column
    if not _column_exists('m8flow_tenant', 'modified_by'):
        op.add_column('m8flow_tenant', sa.Column('modified_by', sa.String(length=255), nullable=True))

    # Backfill slug with name for existing records
    op.execute(sa.text("UPDATE m8flow_tenant SET slug = name WHERE slug IS NULL"))

    # Backfill modified_at for SQLite (added without server_default)
    if not _is_postgres():
        op.execute(sa.text("UPDATE m8flow_tenant SET modified_at = CURRENT_TIMESTAMP WHERE modified_at IS NULL"))

    # Backfill created_by and modified_by with 'system' for existing records
    op.execute(sa.text("UPDATE m8flow_tenant SET created_by = 'system' WHERE created_by IS NULL"))
    op.execute(sa.text("UPDATE m8flow_tenant SET modified_by = 'system' WHERE modified_by IS NULL"))

    # Make columns non-nullable after backfill (safe to re-run alter)
    op.alter_column('m8flow_tenant', 'slug', nullable=False)
    op.alter_column('m8flow_tenant', 'status', nullable=False)
    op.alter_column('m8flow_tenant', 'modified_at', nullable=False)
    op.alter_column('m8flow_tenant', 'created_by', nullable=False)
    op.alter_column('m8flow_tenant', 'modified_by', nullable=False)

    # Add unique constraint on slug (idempotent)
    if not _constraint_exists('m8flow_tenant', 'uq_m8flow_tenant_slug'):
        op.create_unique_constraint('uq_m8flow_tenant_slug', 'm8flow_tenant', ['slug'])

    # Add index on slug (idempotent)
    if not _index_exists('m8flow_tenant', 'ix_m8flow_tenant_slug'):
        op.create_index('ix_m8flow_tenant_slug', 'm8flow_tenant', ['slug'])

    # Drop the unique constraint on name (slug is now the unique identifier)
    if _constraint_exists('m8flow_tenant', 'm8flow_tenant_name_key'):
        op.drop_constraint('m8flow_tenant_name_key', 'm8flow_tenant', type_='unique')


def downgrade():
    # Recreate unique constraint on name
    op.create_unique_constraint('m8flow_tenant_name_key', 'm8flow_tenant', ['name'])
    
    # Drop index and constraint on slug
    op.drop_index('ix_m8flow_tenant_slug', table_name='m8flow_tenant')
    op.drop_constraint('uq_m8flow_tenant_slug', 'm8flow_tenant', type_='unique')
    
    # Drop added columns
    op.drop_column('m8flow_tenant', 'modified_by')
    op.drop_column('m8flow_tenant', 'created_by')
    op.drop_column('m8flow_tenant', 'modified_at')
    op.drop_column('m8flow_tenant', 'status')
    op.drop_column('m8flow_tenant', 'slug')
    if _is_postgres():
        op.execute('DROP TYPE tenantstatus')
