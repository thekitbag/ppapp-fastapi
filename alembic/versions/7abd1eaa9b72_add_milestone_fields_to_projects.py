"""add milestone fields to projects

Revision ID: 7abd1eaa9b72
Revises: c4baf552f87e
Create Date: 2025-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = '7abd1eaa9b72'
down_revision = 'c4baf552f87e'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('projects') as b:
        b.add_column(sa.Column('milestone_title', sa.Text(), nullable=True))
        b.add_column(sa.Column('milestone_due_at', sa.DateTime(timezone=True), nullable=True))

def downgrade():
    with op.batch_alter_table('projects') as b:
        b.drop_column('milestone_due_at')
        b.drop_column('milestone_title')
