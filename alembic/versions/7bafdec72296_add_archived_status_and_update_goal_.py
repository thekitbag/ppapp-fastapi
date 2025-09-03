revision = '7bafdec72296'
down_revision = '8f9e2b1d4c5a'
branch_labels = 'None'
depends_on = 'None'

from alembic import op
import sqlalchemy as sa

def upgrade():
    """
    Add archived status and update goal type enum.
    SQLite path keeps TEXT + app-level validation; Postgres path enforces DB enum.
    Idempotent on Postgres, no-op for ENUM on SQLite as designed.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    
    if dialect == "postgresql":
        # PostgreSQL: Use proper ENUM types
        op.execute("ALTER TYPE statusenum ADD VALUE IF NOT EXISTS 'archived'")
        
        op.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goaltypeenum') THEN
                    CREATE TYPE goaltypeenum AS ENUM ('annual', 'quarterly', 'weekly');
                END IF;
            END $$;
        """)
        
        op.execute("UPDATE goals SET type = 'weekly' WHERE type = 'monthly'")
        op.execute("ALTER TABLE goals ALTER COLUMN type TYPE goaltypeenum USING type::goaltypeenum")
        op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'week'")
    else:
        # SQLite-safe path: Keep TEXT columns, rely on app-level validation
        op.execute("UPDATE goals SET type = 'weekly' WHERE type = 'monthly'")
        op.execute("UPDATE tasks SET status = 'week' WHERE status = 'backlog'")
        # DB default change omitted for SQLite; ORM default covers new rows

def downgrade():
    """Rollback changes with dialect safety."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    
    if dialect == "postgresql":
        op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'backlog'")
        op.execute("ALTER TABLE goals ALTER COLUMN type TYPE VARCHAR")
        op.execute("DROP TYPE IF EXISTS goaltypeenum")
        op.execute("UPDATE tasks SET status = 'backlog' WHERE status = 'archived'")
    else:
        # Best-effort rollback for SQLite
        op.execute("UPDATE tasks SET status = 'backlog' WHERE status = 'archived'")
