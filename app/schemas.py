from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

Status = Literal["backlog","week", "today", "doing","done", "waiting"]

class ProjectBase(BaseModel):
    name: str
    color: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class GoalBase(BaseModel):
    title: str
    type: Optional[str] = None

class GoalCreate(GoalBase):
    pass

class Goal(GoalBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    size: Optional[Literal["xs","s","m","l","xl"]] = None
    effort_minutes: Optional[int] = None
    hard_due_at: Optional[datetime] = None
    soft_due_at: Optional[datetime] = None
    energy: Optional[Literal["low","medium","high","energized","neutral","tired"]] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None

class TaskCreate(TaskBase):
    tags: List[str] = []
    status: Optional[Status] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Status] = None
    sort_order: Optional[float] = None
    tags: Optional[List[str]] = None
    size: Optional[Literal["xs","s","m","l","xl"]] = None
    effort_minutes: Optional[int] = None
    hard_due_at: Optional[datetime] = None
    soft_due_at: Optional[datetime] = None
    energy: Optional[Literal["low","medium","high","energized","neutral","tired"]] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None

class TaskOut(BaseModel):
    id: str
    title: str
    status: Status
    sort_order: float
    tags: List[str] = []
    effort_minutes: Optional[int] = None
    hard_due_at: Optional[datetime] = None
    soft_due_at: Optional[datetime] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class RecommendationItem(BaseModel):
    task: TaskOut
    score: float
    factors: dict
    why: str

class RecommendationResponse(BaseModel):
    items: List[RecommendationItem]
