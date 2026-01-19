"""add_template_table

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-15 11:56:30.471226

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply this migration.
    
    This function is called when upgrading the database schema.
    Creates the template table with all required columns, indexes, constraints,
    and foreign key relationships.
    
    The template table stores template metadata and version information,
    with tenant scoping support via foreign key to m8flow_tenant table.
    """
    # Create the template table
    op.create_table(
        'template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_key', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('m8f_tenant_id', sa.String(length=255), nullable=True),
        sa.Column('visibility', sa.String(length=20), nullable=False),
        sa.Column('bpmn_object_key', sa.String(length=1024), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'm8f_tenant_id', 
            'template_key', 
            'version', 
            name='uq_template_key_version_tenant'
        )
    )
    
    # Create indexes for better query performance
    op.create_index('ix_template_is_published', 'template', ['is_published'], unique=False)
    op.create_index('ix_template_m8f_tenant_id', 'template', ['m8f_tenant_id'], unique=False)
    op.create_index('ix_template_status', 'template', ['status'], unique=False)
    op.create_index('ix_template_template_key', 'template', ['template_key'], unique=False)
    op.create_index('ix_template_visibility', 'template', ['visibility'], unique=False)
    
    # Create foreign key constraint for tenant scoping
    op.create_foreign_key(
        'template_m8f_tenant_id_fkey',
        'template',
        'm8flow_tenant',
        ['m8f_tenant_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade():
    """
    Rollback this migration.
    
    This function is called when downgrading the database schema.
    It reverses all changes made in upgrade().
    
    IMPORTANT: Ensure downgrade() properly reverses upgrade() changes.
    Test both upgrade and downgrade paths before committing.
    """
    # Drop foreign key constraint first
    op.drop_constraint('template_m8f_tenant_id_fkey', 'template', type_='foreignkey')
    
    # Drop all indexes
    op.drop_index('ix_template_visibility', table_name='template')
    op.drop_index('ix_template_template_key', table_name='template')
    op.drop_index('ix_template_status', table_name='template')
    op.drop_index('ix_template_m8f_tenant_id', table_name='template')
    op.drop_index('ix_template_is_published', table_name='template')
    
    # Drop the table
    op.drop_table('template')
