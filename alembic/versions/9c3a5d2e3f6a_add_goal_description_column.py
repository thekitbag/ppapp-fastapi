"""add description column to goals

Revision ID: 9c3a5d2e3f6a
Revises: 7bafdec72296
Create Date: 2025-09-03
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9c3a5d2e3f6a'
down_revision = '7bafdec72296'
branch_labels = None
depends_on = None


def upgrade():
    # Add the missing description column to goals to align with models
    # Safe across dialects; on SQLite it's a simple table alter add column
    with op.batch_alter_table('goals') as batch:
        batch.add_column(sa.Column('description', sa.Text(), nullable=True))


def downgrade():
    # Drop the description column
    with op.batch_alter_table('goals') as batch:
        batch.drop_column('description')

