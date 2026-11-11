"""Personal access tokens; plaintext is never persisted."""
from alembic import op
import sqlalchemy as sa

revision = 'b12a7c04d001'
down_revision = '20260228_report001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('api_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('prefix', sa.String(8), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'])


def downgrade():
    op.drop_index('ix_api_tokens_user_id', table_name='api_tokens')
    op.drop_table('api_tokens')
