from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tasks, recommendations, health

app = FastAPI(title="Personal Productivity API", version="0.1.0-alpha")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(health.router, tags=["health"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])

@app.get("/")
def root():
    return {"ok": True}
