from fastapi import APIRouter
from . import tasks, projects, goals

# Import existing routers that don't need refactoring yet
from app.routers import health, recommendations

api_router = APIRouter(prefix="/api/v1")

# New clean routers
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])

# Legacy routers (to be refactored later)
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])