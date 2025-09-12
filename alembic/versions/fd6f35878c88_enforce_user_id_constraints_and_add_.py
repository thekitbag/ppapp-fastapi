"""enforce user_id constraints and add indexes

Revision ID: fd6f35878c88
Revises: 93eec90a8aae
Create Date: 2025-09-10 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fd6f35878c88'
down_revision = '93eec90a8aae'
branch_labels = None
depends_on = None


def upgrade():
    # Check if we're using SQLite
    connection = op.get_bind()
    dialect = connection.engine.dialect.name
    
    if dialect == 'sqlite':
        # For SQLite, skip foreign key constraints as they require batch mode
        # and recreating tables. We'll rely on application-level enforcement.
        # The foreign keys would be created properly in PostgreSQL production.
        pass
    else:
        # Add foreign key constraints for PostgreSQL
        op.create_foreign_key('fk_tasks_user_id', 'tasks', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_tags_user_id', 'tags', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_energy_state_user_id', 'energy_state', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_projects_user_id', 'projects', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_goals_user_id', 'goals', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_goal_krs_user_id', 'goal_krs', 'users', ['user_id'], ['id'])
        op.create_foreign_key('fk_task_goals_user_id', 'task_goals', 'users', ['user_id'], ['id'])
    
    # Add indexes for better query performance (works on both SQLite and PostgreSQL)
    op.create_index('ix_tasks_user_id', 'tasks', ['user_id'])
    op.create_index('ix_tags_user_id', 'tags', ['user_id'])
    op.create_index('ix_energy_state_user_id', 'energy_state', ['user_id'])
    op.create_index('ix_projects_user_id', 'projects', ['user_id'])
    op.create_index('ix_goals_user_id', 'goals', ['user_id'])
    op.create_index('ix_goal_krs_user_id', 'goal_krs', ['user_id'])
    op.create_index('ix_task_goals_user_id', 'task_goals', ['user_id'])
    
    # Add composite indexes for common query patterns
    op.create_index('ix_tasks_user_status_sort', 'tasks', ['user_id', 'status', 'sort_order'])
    
    # Update the unique constraint on tags to be per-user
    if dialect == 'sqlite':
        # For SQLite, skip constraint modifications as they require batch mode
        # In production with PostgreSQL, proper constraints would be enforced
        # We rely on application-level enforcement for SQLite
        pass
    else:
        op.drop_constraint('tags_name_key', 'tags', type_='unique')
        op.create_unique_constraint('uq_user_tag_name', 'tags', ['user_id', 'name'])


def downgrade():
    # Remove constraints and indexes in reverse order
    connection = op.get_bind()
    dialect = connection.engine.dialect.name
    
    # Handle unique constraint removal
    if dialect == 'sqlite':
        # For SQLite, skip constraint modifications as they require batch mode
        # No constraints were created in upgrade, so nothing to remove
        pass
    else:
        op.drop_constraint('uq_user_tag_name', 'tags', type_='unique')
        op.create_unique_constraint(None, 'tags', ['name'])
    
    op.drop_index('ix_tasks_user_status_sort', table_name='tasks')
    
    # Drop user_id indexes
    op.drop_index('ix_task_goals_user_id', table_name='task_goals')
    op.drop_index('ix_goal_krs_user_id', table_name='goal_krs')
    op.drop_index('ix_goals_user_id', table_name='goals')
    op.drop_index('ix_projects_user_id', table_name='projects')
    op.drop_index('ix_energy_state_user_id', table_name='energy_state')
    op.drop_index('ix_tags_user_id', table_name='tags')
    op.drop_index('ix_tasks_user_id', table_name='tasks')
    
    # Drop foreign key constraints only for non-SQLite
    if dialect != 'sqlite':
        op.drop_constraint('fk_task_goals_user_id', 'task_goals', type_='foreignkey')
        op.drop_constraint('fk_goal_krs_user_id', 'goal_krs', type_='foreignkey')
        op.drop_constraint('fk_goals_user_id', 'goals', type_='foreignkey')
        op.drop_constraint('fk_projects_user_id', 'projects', type_='foreignkey')
        op.drop_constraint('fk_energy_state_user_id', 'energy_state', type_='foreignkey')
        op.drop_constraint('fk_tags_user_id', 'tags', type_='foreignkey')
        op.drop_constraint('fk_tasks_user_id', 'tasks', type_='foreignkey')
