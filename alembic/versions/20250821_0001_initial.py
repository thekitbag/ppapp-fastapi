
from alembic import op
import sqlalchemy as sa

revision = '20250821_0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('status', sa.Enum('inbox','todo','doing','done', name='statusenum'), nullable=False, server_default='inbox'),
        sa.Column('size', sa.Enum('xs','s','m','l','xl', name='sizeenum'), nullable=True),
        sa.Column('effort_minutes', sa.Integer(), nullable=True),
        sa.Column('hard_due_at', sa.DateTime(), nullable=True),
        sa.Column('soft_due_at', sa.DateTime(), nullable=True),
        sa.Column('energy', sa.Enum('low','medium','high','energized','neutral','tired', name='energyenum'), nullable=True),
        sa.Column('focus_score', sa.Float(), nullable=True),
        sa.Column('checklist', sa.JSON(), nullable=True),
        sa.Column('recurrence_rule', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table('tags',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), unique=True, nullable=False),
    )
    op.create_table(
        'task_tags',
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.String(), sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table('energy_state',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('value', sa.Enum('low','medium','high','energized','neutral','tired', name='energyenum'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='manual'),
        sa.Column('confidence', sa.Float(), nullable=True),
    )

def downgrade():
    op.drop_table('task_tags')
    op.drop_table('tags')
    op.drop_table('tasks')
    op.drop_table('energy_state')
    op.execute("DROP TYPE IF EXISTS statusenum")
    op.execute("DROP TYPE IF EXISTS sizeenum")
    op.execute("DROP TYPE IF EXISTS energyenum")
