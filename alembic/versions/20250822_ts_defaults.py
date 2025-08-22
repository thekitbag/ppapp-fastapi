"""add server defaults for created_at/updated_at

Revision ID: 20250822_ts_defaults
Revises: 20250821_0001
Create Date: 2025-08-22
"""
from alembic import op
import sqlalchemy as sa

revision = '20250822_ts_defaults'
down_revision = '20250821_0001'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.alter_column('created_at', server_default=sa.text('CURRENT_TIMESTAMP'))
        batch.alter_column('updated_at', server_default=sa.text('CURRENT_TIMESTAMP'))
    op.execute("""UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL""")

def downgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.alter_column('created_at', server_default=None)
        batch.alter_column('updated_at', server_default=None)
