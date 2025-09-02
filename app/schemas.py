from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

Status = Literal["backlog","week", "today", "doing","done", "waiting"]

class ProjectBase(BaseModel):
    name: str
    color: Optional[str] = None
    milestone_title: Optional[str] = None
    milestone_due_at: Optional[datetime] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    milestone_title: Optional[str] = None
    milestone_due_at: Optional[datetime] = None

class Project(ProjectBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class GoalBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = None

class GoalCreate(GoalBase):
    pass

class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None

class GoalOut(GoalBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class GoalSummary(BaseModel):
    id: str
    title: str

    class Config:
        from_attributes = True

class KRCreate(BaseModel):
    name: str
    target_value: float
    unit: Optional[str] = None
    baseline_value: Optional[float] = None

class KROut(BaseModel):
    id: str
    goal_id: str
    name: str
    target_value: float
    unit: Optional[str] = None
    baseline_value: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True

class TaskGoalLink(BaseModel):
    task_ids: List[str]
    goal_id: str

class TaskGoalLinkResponse(BaseModel):
    linked: List[str]
    already_linked: List[str]

class GoalDetail(GoalOut):
    key_results: List[KROut] = []
    tasks: List['TaskOut'] = []

# Backward compatibility
class Goal(GoalOut):
    pass

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
    sort_order: Optional[float] = None

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
    goal_id: Optional[str] = None  # DEPRECATED: Use task-goal linking API instead

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
    goal_id: Optional[str] = None  # DEPRECATED: Use goals[] field instead. Kept for backward compatibility.
    goals: List[GoalSummary] = []  # Many-to-many goals - use this instead of goal_id
    created_at: datetime
    updated_at: datetime

class RecommendationItem(BaseModel):
    task: TaskOut
    score: float
    factors: dict
    why: str

class RecommendationResponse(BaseModel):
    items: List[RecommendationItem]
