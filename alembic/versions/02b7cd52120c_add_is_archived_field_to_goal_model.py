revision = '02b7cd52120c'
down_revision = '463c5c35a185'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('goals', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')))

def downgrade():
    op.drop_column('goals', 'is_archived')
