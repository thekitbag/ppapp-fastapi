# Claude Code Assistant Notes

## Test Environment Setup
**IMPORTANT**: Always activate the virtual environment and use the Makefile for testing:
```bash
source env/bin/activate && make test
```
- The virtual environment is in `env/` (not `venv/`)
- The Makefile sets the correct `PYTHONPATH=/Users/markgray/projects/ppapp-fastapi`
- Direct pytest commands may fail due to missing environment setup

## Architecture (Updated Sept 2025)

**Current Architecture**: Clean service-based pattern with v1 API
- All endpoints are now under `/api/v1/` prefix
- Service layer in `/app/services/` handles business logic
- Controllers in `/app/api/v1/` are thin and use dependency injection
- Database access only through services, not direct in controllers

**Legacy Cleanup Completed**:
- ❌ Removed `/app/routers/` (legacy direct-DB access)
- ❌ Removed `/app/main_legacy.py` 
- ✅ All endpoints migrated to `/app/api/v1/` service pattern

**Current Endpoints**:
- `/api/v1/tasks` - Task CRUD with TaskService
- `/api/v1/projects` - Project CRUD with ProjectService  
- `/api/v1/goals` - Goals and key results with GoalService
- `/api/v1/health` - Health check
- `/api/v1/recommendations` - Task recommendations

**Service Pattern Example**:
```python
# Controller (thin)
@router.post("", response_model=TaskOut)
def create_task(
    payload: TaskCreate,
    task_service: TaskService = Depends(get_task_service)
):
    return task_service.create_task(payload)

# Service (business logic)
def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)
```

## Database Migrations
- Use Alembic for all schema changes
- Always test both upgrade AND downgrade functions
- Use `server_default=sa.text('CURRENT_TIMESTAMP')` not Python callables
- Drop indexes and tables in reverse order in downgrade()

## Goals & Key Results Implementation
- Many-to-many relationship: Task ↔ Goal via `task_goals` table
- `TaskGoal` junction table with optional `weight` field
- Goals have `key_results` (GoalKR table) with target/baseline values
- Backward compatibility: kept deprecated `goal_id` field on Task model