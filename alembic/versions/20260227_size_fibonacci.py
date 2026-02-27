"""change task size from enum to integer (fibonacci scale)

Revision ID: 20260227_size_fibonacci
Revises: 608845dcbeec
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

revision = '20260227_size_fibonacci'
down_revision = '608845dcbeec'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.alter_column(
            'size',
            existing_type=sa.Enum('xs', 's', 'm', 'l', 'xl', name='sizeenum'),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using='NULL',
        )
    # Drop the now-unused enum type (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP TYPE IF EXISTS sizeenum")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sizeenum') "
            "THEN CREATE TYPE sizeenum AS ENUM ('xs', 's', 'm', 'l', 'xl'); "
            "END IF; END $$;"
        )
    with op.batch_alter_table('tasks') as batch:
        batch.alter_column(
            'size',
            existing_type=sa.Integer(),
            type_=sa.Enum('xs', 's', 'm', 'l', 'xl', name='sizeenum'),
            existing_nullable=True,
            postgresql_using='NULL',
        )
