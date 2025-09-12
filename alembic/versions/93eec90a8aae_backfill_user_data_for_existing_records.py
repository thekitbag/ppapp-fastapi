"""backfill user data for existing records

Revision ID: 93eec90a8aae
Revises: e7d018f6a356
Create Date: 2025-09-10 14:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
import uuid
import os

# revision identifiers, used by Alembic.
revision = '93eec90a8aae'
down_revision = 'e7d018f6a356'
branch_labels = None
depends_on = None


def upgrade():
    # Get database connection
    connection = op.get_bind()
    
    # Create or find the "system" user for backfill
    # This user will own all existing data during migration
    system_user_id = str(uuid.uuid4())
    system_email = os.getenv("BACKFILL_USER_EMAIL", "product.lead@example.com")
    system_name = os.getenv("BACKFILL_USER_NAME", "Product Lead")
    
    # Insert system user (using microsoft as default provider)
    connection.execute(sa.text("""
        INSERT INTO users (id, provider, provider_sub, email, name, created_at)
        VALUES (:user_id, 'microsoft', 'system-backfill', :email, :name, CURRENT_TIMESTAMP)
    """), {
        'user_id': system_user_id,
        'email': system_email,
        'name': system_name
    })
    
    # Backfill all existing records with the system user ID
    tables_to_backfill = [
        'tasks',
        'tags', 
        'energy_state',
        'projects',
        'goals',
        'goal_krs',
        'task_goals'
    ]
    
    for table in tables_to_backfill:
        # Check if table has any records
        result = connection.execute(sa.text(f"SELECT COUNT(*) as count FROM {table}")).fetchone()
        record_count = result[0] if result else 0
        
        if record_count > 0:
            connection.execute(sa.text(f"""
                UPDATE {table} 
                SET user_id = :user_id 
                WHERE user_id IS NULL
            """), {'user_id': system_user_id})
            print(f"Backfilled {record_count} records in {table}")


def downgrade():
    # Remove the backfill by setting user_id back to NULL
    # This allows the migration to be reversed cleanly
    connection = op.get_bind()
    
    tables_to_clear = [
        'task_goals',
        'goal_krs',
        'goals',
        'projects',
        'energy_state',
        'tags',
        'tasks'
    ]
    
    for table in tables_to_clear:
        connection.execute(sa.text(f"UPDATE {table} SET user_id = NULL"))
    
    # Remove the system user
    connection.execute(sa.text("DELETE FROM users WHERE provider_sub = 'system-backfill'"))
