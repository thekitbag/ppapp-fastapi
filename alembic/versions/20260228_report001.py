"""REPORT-001: drop effort_minutes, add completed_at

Revision ID: 20260228_report001
Revises: 20260227_size_fibonacci
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = '20260228_report001'
down_revision = '20260227_size_fibonacci'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('effort_minutes')
        batch.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('completed_at')
        batch.add_column(sa.Column('effort_minutes', sa.Integer(), nullable=True))
