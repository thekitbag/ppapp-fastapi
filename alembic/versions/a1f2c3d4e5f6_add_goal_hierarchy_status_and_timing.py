"""add goal hierarchy, status enum, and end_date

Revision ID: a1f2c3d4e5f6
Revises: 7bafdec72296
Create Date: 2025-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = 'a1f2c3d4e5f6'
down_revision = '7bafdec72296'
branch_labels = None
depends_on = None


def upgrade():
    """Add goal hierarchy columns and status enum with defaults.
    Postgres uses ENUM types and FK constraints, SQLite uses TEXT and app-level validation.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Add end_date (both dialects)
    op.add_column('goals', sa.Column('end_date', sa.DateTime(timezone=True), nullable=True))

    # Add parent_goal_id (both dialects)
    op.add_column('goals', sa.Column('parent_goal_id', sa.String(), nullable=True))
    op.create_index('ix_goals_parent_goal_id', 'goals', ['parent_goal_id'])

    if dialect == 'postgresql':
        # Create goalstatusenum if missing
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goalstatusenum') THEN
                    CREATE TYPE goalstatusenum AS ENUM ('on_target', 'at_risk', 'off_target');
                END IF;
            END $$;
            """
        )

        # Add status column with enum and default
        op.add_column(
            'goals',
            sa.Column(
                'status',
                sa.Enum('on_target', 'at_risk', 'off_target', name='goalstatusenum'),
                nullable=False,
                server_default='on_target'
            )
        )

        # Add self-referential FK for hierarchy
        op.create_foreign_key(
            None, 'goals', 'goals', ['parent_goal_id'], ['id'], ondelete='SET NULL'
        )

        # Optional index for end_date ordering
        op.create_index('ix_goals_end_date', 'goals', ['end_date'])
    else:
        # SQLite: use TEXT for status with server default; no real ENUM
        op.add_column('goals', sa.Column('status', sa.Text(), nullable=False, server_default='on_target'))
        # Optional index for end_date ordering
        op.create_index('ix_goals_end_date', 'goals', ['end_date'])


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Drop indexes first
    op.drop_index('ix_goals_end_date', table_name='goals')
    op.drop_index('ix_goals_parent_goal_id', table_name='goals')

    # Drop FK if on Postgres
    if dialect == 'postgresql':
        # Alembic cannot drop unnamed FK easily without reflection; attempt best-effort
        # Try to drop FK by discovering its name; if not, fallback to implicit cascade via drop column
        # For simplicity, rely on cascade behavior by dropping the column next.
        pass

    # Drop columns (status, end_date, parent_goal_id)
    with op.batch_alter_table('goals') as batch_op:
        batch_op.drop_column('status')
        batch_op.drop_column('end_date')
        batch_op.drop_column('parent_goal_id')

    if dialect == 'postgresql':
        # Drop enum type if exists
        op.execute("DROP TYPE IF EXISTS goalstatusenum")

