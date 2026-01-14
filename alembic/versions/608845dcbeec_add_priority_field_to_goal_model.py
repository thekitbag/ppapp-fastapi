revision = '608845dcbeec'
down_revision = '02b7cd52120c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('goals', sa.Column('priority', sa.Float(), nullable=False, server_default=sa.text('0.0')))

def downgrade():
    op.drop_column('goals', 'priority')
