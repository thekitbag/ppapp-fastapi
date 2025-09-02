"""add goals key results and task goal links

Revision ID: 8f9e2b1d4c5a
Revises: 7abd1eaa9b72
Create Date: 2025-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = '8f9e2b1d4c5a'
down_revision = '7abd1eaa9b72'
branch_labels = None
depends_on = None

def upgrade():
    # Goals table already exists from previous migration, only create the new tables
    
    # Create goal_krs table
    op.create_table(
        'goal_krs',
        sa.Column('id', sa.Text(), primary_key=True, nullable=False),
        sa.Column('goal_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('target_value', sa.Float(), nullable=False),
        sa.Column('unit', sa.Text(), nullable=True),
        sa.Column('baseline_value', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_goal_krs_goal', 'goal_krs', ['goal_id'])

    # Create task_goals table (many-to-many relationship)
    op.create_table(
        'task_goals',
        sa.Column('id', sa.Text(), primary_key=True, nullable=False),
        sa.Column('task_id', sa.Text(), nullable=False),
        sa.Column('goal_id', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_task_goals_task', 'task_goals', ['task_id'])
    op.create_index('ix_task_goals_goal', 'task_goals', ['goal_id'])
    
    # Optional FKs (commented out until FE stabilizes as requested by tech lead)
    # op.create_foreign_key(None, 'goal_krs', 'goals', ['goal_id'], ['id'], ondelete='CASCADE')
    # op.create_foreign_key(None, 'task_goals', 'tasks', ['task_id'], ['id'], ondelete='CASCADE')
    # op.create_foreign_key(None, 'task_goals', 'goals', ['goal_id'], ['id'], ondelete='CASCADE')

def downgrade():
    op.drop_index('ix_task_goals_goal', table_name='task_goals')
    op.drop_index('ix_task_goals_task', table_name='task_goals')
    op.drop_table('task_goals')
    op.drop_index('ix_goal_krs_goal', table_name='goal_krs')
    op.drop_table('goal_krs')
    # Don't drop goals table as it existed before this migration