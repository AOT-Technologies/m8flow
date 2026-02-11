"""update the tenant table columns

Revision ID: 2cfce680c743
Revises: a750bbb5c234
Create Date: 2026-01-21 12:51:49.418203

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '2cfce680c743'
down_revision = 'a750bbb5c234'
branch_labels = None
depends_on = None

def upgrade():
    # Create the TenantStatus enum type if it doesn't exist
    op.execute("CREATE TYPE tenantstatus AS ENUM ('ACTIVE', 'INACTIVE', 'DELETED')")
    
    # Add slug column
    op.add_column('m8flow_tenant', sa.Column('slug', sa.String(length=255), nullable=True))
    
    # Add status column with enum type
    op.add_column('m8flow_tenant', 
        sa.Column('status', 
                  postgresql.ENUM('ACTIVE', 'INACTIVE', 'DELETED', name='tenantstatus'),
                  nullable=True,
                  server_default='ACTIVE'))
    
    # Alter existing created_at column to add UTC timezone support
    op.alter_column('m8flow_tenant', 'created_at',
                    type_=sa.DateTime(timezone=True),
                    existing_type=sa.DateTime(),
                    existing_nullable=False,
                    existing_server_default=sa.text('now()'))
    
    # Add modified_at column (UTC timezone-aware)
    op.add_column('m8flow_tenant', 
        sa.Column('modified_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    
    # Add created_by column
    op.add_column('m8flow_tenant', sa.Column('created_by', sa.String(length=255), nullable=True))
    
    # Add modified_by column
    op.add_column('m8flow_tenant', sa.Column('modified_by', sa.String(length=255), nullable=True))
    
    # Backfill slug with name for existing records
    op.execute("UPDATE m8flow_tenant SET slug = name WHERE slug IS NULL")
    
    # Backfill created_by and modified_by with 'system' for existing records
    op.execute("UPDATE m8flow_tenant SET created_by = 'system' WHERE created_by IS NULL")
    op.execute("UPDATE m8flow_tenant SET modified_by = 'system' WHERE modified_by IS NULL")
    
    # Make columns non-nullable after backfill
    op.alter_column('m8flow_tenant', 'slug', nullable=False)
    op.alter_column('m8flow_tenant', 'status', nullable=False)
    op.alter_column('m8flow_tenant', 'modified_at', nullable=False)
    op.alter_column('m8flow_tenant', 'created_by', nullable=False)
    op.alter_column('m8flow_tenant', 'modified_by', nullable=False)
    
    # Add unique constraint on slug
    op.create_unique_constraint('uq_m8flow_tenant_slug', 'm8flow_tenant', ['slug'])
    
    # Add index on slug
    op.create_index('ix_m8flow_tenant_slug', 'm8flow_tenant', ['slug'])
    
    # Drop the unique constraint on name (slug is now the unique identifier)
    bind = op.get_bind()
    insp = inspect(bind)
    constraints = insp.get_unique_constraints('m8flow_tenant')
    constraint_names = [c['name'] for c in constraints]
    
    if 'm8flow_tenant_name_key' in constraint_names:
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
    # Drop the enum type
    op.execute('DROP TYPE tenantstatus')