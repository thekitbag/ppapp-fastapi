"""add goals key results and task goal links

Revision ID: 8f9e2b1d4c5a
Revises: 7abd1eaa9b72
Create Date: 2025-09-01

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '8f9e2b1d4c5a'
down_revision = '7abd1eaa9b72'
branch_labels = None
depends_on = None

def upgrade():
    # Create goals table
    op.create_table('goals',
        sa.Column('id', sa.Text(), nullable=False, primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=datetime.utcnow),
    )
    
    # Create goal_krs table
    op.create_table('goal_krs',
        sa.Column('id', sa.Text(), nullable=False, primary_key=True),
        sa.Column('goal_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('target_value', sa.Float(), nullable=False),
        sa.Column('unit', sa.Text(), nullable=True),
        sa.Column('baseline_value', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=datetime.utcnow),
    )
    
    # Create task_goals table (many-to-many relationship)
    op.create_table('task_goals',
        sa.Column('id', sa.Text(), nullable=False, primary_key=True),
        sa.Column('task_id', sa.Text(), nullable=False),
        sa.Column('goal_id', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=datetime.utcnow),
    )

def downgrade():
    op.drop_table('task_goals')
    op.drop_table('goal_krs')
    op.drop_table('goals')