revision = '8fdbc4df682c'
down_revision = 'fd6f35878c88'
branch_labels = 'None'
depends_on = 'None'

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Task table indexes for filtering performance
    op.create_index('ix_tasks_user_project', 'tasks', ['user_id', 'project_id'])
    op.create_index('ix_tasks_user_goal', 'tasks', ['user_id', 'goal_id'])
    op.create_index('ix_tasks_hard_due_at', 'tasks', ['hard_due_at'])
    op.create_index('ix_tasks_soft_due_at', 'tasks', ['soft_due_at'])
    op.create_index('ix_tasks_project_id', 'tasks', ['project_id'])

    # TaskGoal junction table indexes for goal filtering performance
    op.create_index('ix_task_goals_goal_id', 'task_goals', ['goal_id'])
    op.create_index('ix_task_goals_task_id', 'task_goals', ['task_id'])
    op.create_index('ix_task_goals_user_goal', 'task_goals', ['user_id', 'goal_id'])
    op.create_index('ix_task_goals_user_task', 'task_goals', ['user_id', 'task_id'])


def downgrade():
    # Drop TaskGoal indexes in reverse order
    op.drop_index('ix_task_goals_user_task', 'task_goals')
    op.drop_index('ix_task_goals_user_goal', 'task_goals')
    op.drop_index('ix_task_goals_task_id', 'task_goals')
    op.drop_index('ix_task_goals_goal_id', 'task_goals')

    # Drop Task table indexes in reverse order
    op.drop_index('ix_tasks_project_id', 'tasks')
    op.drop_index('ix_tasks_soft_due_at', 'tasks')
    op.drop_index('ix_tasks_hard_due_at', 'tasks')
    op.drop_index('ix_tasks_user_goal', 'tasks')
    op.drop_index('ix_tasks_user_project', 'tasks')
