"""Stable per-user plan references."""
from alembic import op
import sqlalchemy as sa

revision = 'b12a7c04d002'
down_revision = 'b12a7c04d001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('goals', sa.Column('plan_ref', sa.String(), nullable=True))
    with op.batch_alter_table('goals') as batch:
        batch.create_unique_constraint('uq_goals_user_plan_ref', ['user_id', 'plan_ref'])


def downgrade():
    with op.batch_alter_table('goals') as batch:
        batch.drop_constraint('uq_goals_user_plan_ref', type_='unique')
        batch.drop_column('plan_ref')
