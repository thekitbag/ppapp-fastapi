revision = '7bafdec72296'
down_revision = '8f9e2b1d4c5a'
branch_labels = 'None'
depends_on = 'None'

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add 'archived' status to the StatusEnum
    op.execute("ALTER TYPE statusenum ADD VALUE IF NOT EXISTS 'archived'")
    
    # Update Goal.type column to use enum
    # First, create the enum type for goals
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goaltypeenum') THEN
                CREATE TYPE goaltypeenum AS ENUM ('annual', 'quarterly', 'weekly');
            END IF;
        END $$;
    """)
    
    # Migrate existing 'monthly' goals to 'weekly' as per requirement
    op.execute("UPDATE goals SET type = 'weekly' WHERE type = 'monthly'")
    
    # Update goals table to use the enum type
    op.execute("ALTER TABLE goals ALTER COLUMN type TYPE goaltypeenum USING type::goaltypeenum")
    
    # Change default task status to 'week'
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'week'")

def downgrade():
    # Revert default task status to 'backlog'
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'backlog'")
    
    # Revert Goal.type back to string
    op.execute("ALTER TABLE goals ALTER COLUMN type TYPE VARCHAR")
    
    # Drop the goal type enum
    op.execute("DROP TYPE IF EXISTS goaltypeenum")
    
    # Remove 'archived' from StatusEnum (this is tricky in PostgreSQL, would need to recreate the type)
    # For safety, we'll leave the enum value but ensure no tasks use it
    op.execute("UPDATE tasks SET status = 'backlog' WHERE status = 'archived'")
