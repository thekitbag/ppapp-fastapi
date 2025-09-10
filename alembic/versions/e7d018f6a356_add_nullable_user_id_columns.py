"""add nullable user_id columns

Revision ID: e7d018f6a356
Revises: 91b737de800b
Create Date: 2025-09-10 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7d018f6a356'
down_revision = '91b737de800b'
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable user_id columns to all resource tables
    op.add_column('tasks', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('tags', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('energy_state', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('goals', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('goal_krs', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('task_goals', sa.Column('user_id', sa.String(), nullable=True))


def downgrade():
    # Drop user_id columns
    op.drop_column('task_goals', 'user_id')
    op.drop_column('goal_krs', 'user_id')
    op.drop_column('goals', 'user_id')
    op.drop_column('projects', 'user_id')
    op.drop_column('energy_state', 'user_id')
    op.drop_column('tags', 'user_id')
    op.drop_column('tasks', 'user_id')
