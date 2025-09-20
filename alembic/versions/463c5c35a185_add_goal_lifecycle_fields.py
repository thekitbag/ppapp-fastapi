"""add goal lifecycle fields

Revision ID: 463c5c35a185
Revises: 416ff2e1584a
Create Date: 2025-09-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '463c5c35a185'
down_revision = '416ff2e1584a'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_closed column with default False
    op.add_column('goals', sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # Add closed_at column (nullable)
    op.add_column('goals', sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))

    # Check if we're using SQLite
    connection = op.get_bind()
    dialect = connection.engine.dialect.name

    if dialect != 'sqlite':
        # Add index for efficient querying by user and closed status (PostgreSQL only)
        op.create_index('ix_goals_user_is_closed', 'goals', ['user_id', 'is_closed'])


def downgrade():
    # Check if we're using SQLite
    connection = op.get_bind()
    dialect = connection.engine.dialect.name

    if dialect != 'sqlite':
        # Drop index
        op.drop_index('ix_goals_user_is_closed', table_name='goals')

    # Drop columns
    op.drop_column('goals', 'closed_at')
    op.drop_column('goals', 'is_closed')