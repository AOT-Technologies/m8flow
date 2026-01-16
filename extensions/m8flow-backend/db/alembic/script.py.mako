"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    """
    Apply this migration.
    
    This function is called when upgrading the database schema.
    Make changes here that modify the database structure.
    
    For data migrations, consider using op.execute() with raw SQL
    or SQLAlchemy operations. Always test data migrations thoroughly.
    """
    ${upgrades if upgrades else "pass"}


def downgrade():
    """
    Rollback this migration.
    
    This function is called when downgrading the database schema.
    It should reverse all changes made in upgrade().
    
    IMPORTANT: Ensure downgrade() properly reverses upgrade() changes.
    Test both upgrade and downgrade paths before committing.
    """
    ${downgrades if downgrades else "pass"}
