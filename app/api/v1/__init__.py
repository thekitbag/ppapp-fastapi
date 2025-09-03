from fastapi import APIRouter
from . import tasks, projects, goals, health, recommendations, imports

api_router = APIRouter(prefix="/api/v1")

# Clean service-based routers
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(imports.router, prefix="/import", tags=["imports"])