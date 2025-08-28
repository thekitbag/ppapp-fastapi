from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '81f80f37840f'
down_revision = '20250822_ts_defaults'  # or your last revision id
branch_labels = None
depends_on = None

def upgrade():
    # SQLite: easiest is batch recreate of the table to update the CHECK for status enum
    with op.batch_alter_table('tasks', recreate='always') as batch_op:
        batch_op.alter_column('status',
            type_=sa.Enum('backlog','today','waiting','doing','done','week', name='statusenum'),
            existing_nullable=False,
            server_default='inbox'
        )

def downgrade():
    with op.batch_alter_table('tasks', recreate='always') as batch_op:
        batch_op.alter_column('status',
            type_=sa.Enum('inbox','todo','doing','done', name='statusenum'),
            existing_nullable=False,
            server_default='inbox'
        )
