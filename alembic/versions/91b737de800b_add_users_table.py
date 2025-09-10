"""add users table

Revision ID: 91b737de800b
Revises: e21c8b11ba88
Create Date: 2025-09-10 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '91b737de800b'
down_revision = 'e21c8b11ba88'
branch_labels = None
depends_on = None


def upgrade():
    # Create users table with provider as string (SQLite doesn't need enum creation)
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('provider_sub', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_sub', name='uq_user_provider_sub')
    )
    
    # Create indexes
    op.create_index('ix_users_email', 'users', ['email'])


def downgrade():
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
    # SQLite doesn't support DROP TYPE - the enum is just stored as string
