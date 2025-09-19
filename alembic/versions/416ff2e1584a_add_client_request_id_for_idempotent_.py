"""add client_request_id for idempotent task creation

Revision ID: 416ff2e1584a
Revises: fd6f35878c88
Create Date: 2025-09-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '416ff2e1584a'
down_revision = 'fd6f35878c88'
branch_labels = None
depends_on = None


def upgrade():
    # Add client_request_id column to tasks table
    op.add_column('tasks', sa.Column('client_request_id', sa.String(), nullable=True))

    # Check if we're using SQLite
    connection = op.get_bind()
    dialect = connection.engine.dialect.name

    if dialect == 'sqlite':
        # For SQLite, skip unique constraint as it requires batch mode
        # In production with PostgreSQL, proper constraints would be enforced
        # We rely on application-level enforcement for SQLite
        pass
    else:
        # Add partial unique constraint for PostgreSQL: UNIQUE(user_id, client_request_id) WHERE client_request_id IS NOT NULL
        op.create_unique_constraint(
            'uq_task_user_client_request_id',
            'tasks',
            ['user_id', 'client_request_id'],
            postgresql_where=sa.text('client_request_id IS NOT NULL')
        )


def downgrade():
    # Check if we're using SQLite
    connection = op.get_bind()
    dialect = connection.engine.dialect.name

    if dialect != 'sqlite':
        # Drop unique constraint for PostgreSQL
        op.drop_constraint('uq_task_user_client_request_id', 'tasks', type_='unique')

    # Drop client_request_id column
    op.drop_column('tasks', 'client_request_id')