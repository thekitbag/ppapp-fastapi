from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone

Status = Literal["backlog","week", "today", "doing","done", "waiting", "archived"]
GoalType = Literal["annual", "quarterly", "weekly"]
GoalStatus = Literal["on_target", "at_risk", "off_target"]

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
    type: Optional[GoalType] = None

class GoalCreate(GoalBase):
    # Goals v2 fields
    parent_goal_id: Optional[str] = None
    end_date: Optional[datetime] = None
    status: Optional[GoalStatus] = "on_target"
    priority: Optional[float] = 0.0

class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[GoalType] = None
    # Goals v2 fields
    parent_goal_id: Optional[str] = None
    end_date: Optional[datetime] = None
    status: Optional[GoalStatus] = None
    priority: Optional[float] = None

class GoalOut(GoalBase):
    id: str
    created_at: datetime
    # Goals v2 fields
    parent_goal_id: Optional[str] = None
    end_date: Optional[datetime] = None
    status: GoalStatus = "on_target"
    # Goal lifecycle fields
    is_closed: bool = False
    closed_at: Optional[datetime] = None
    priority: float = 0.0

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
    # goal_id is provided via the path param; keep optional for backward-compat payloads
    goal_id: Optional[str] = None

class TaskGoalLinkResponse(BaseModel):
    linked: List[str]
    already_linked: List[str]

class GoalDetail(GoalOut):
    key_results: List[KROut] = Field(default_factory=list)
    tasks: List['TaskOut'] = Field(default_factory=list)

# Goals v2: Tree and hierarchy schemas
class GoalNode(GoalOut):
    """Goal with hierarchical children for tree view"""
    children: List['GoalNode'] = Field(default_factory=list)
    # Optional: include tasks for weekly goals when requested
    tasks: Optional[List['TaskOut']] = None
    # Optional: include path showing ancestry (e.g., "Annual › Quarterly")
    path: Optional[str] = None

class GoalsByTypeRequest(BaseModel):
    """Query parameters for getting goals by type"""
    type: GoalType
    parent_id: Optional[str] = None

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
    tags: List[str] = Field(default_factory=list)
    status: Optional[Status] = None
    sort_order: Optional[float] = None
    insert_at: Optional[Literal["top", "bottom"]] = Field(default="top", description="Position for new task in status bucket")
    client_request_id: Optional[str] = Field(default=None, description="Optional client-generated token for idempotent requests")
    goals: Optional[List[str]] = Field(default=None, description="Array of goal IDs to link to this task")

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

    @field_validator("hard_due_at")
    @classmethod
    def hard_due_cannot_be_past(cls, v):
        if v:
            # Ensure both datetimes are timezone-aware for comparison
            now = datetime.now(timezone.utc)
            if v.tzinfo is None:
                # If the input is naive, assume UTC
                v = v.replace(tzinfo=timezone.utc)
            if v < now:
                raise ValueError("hard_due_at cannot be in the past")
        return v

    @field_validator("soft_due_at")
    @classmethod
    def soft_due_before_hard_due(cls, v, info):
        if v and (hard := info.data.get("hard_due_at")):
            # Ensure both datetimes are timezone-aware for comparison
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            if hard.tzinfo is None:
                hard = hard.replace(tzinfo=timezone.utc)
            if v > hard:
                raise ValueError("soft_due_at cannot be after hard_due_at")
        return v

class TaskOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: Status
    sort_order: float
    tags: List[str] = Field(default_factory=list)
    size: Optional[Literal["xs","s","m","l","xl"]] = None
    effort_minutes: Optional[int] = None
    hard_due_at: Optional[datetime] = None
    soft_due_at: Optional[datetime] = None
    energy: Optional[Literal["low","medium","high","energized","neutral","tired"]] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None  # DEPRECATED: Use goals[] field instead. Kept for backward compatibility.
    goals: List[GoalSummary] = Field(default_factory=list)  # Many-to-many goals - use this instead of goal_id
    created_at: datetime
    updated_at: datetime

class RecommendationItem(BaseModel):
    task: TaskOut
    score: float
    factors: dict
    why: str

class RecommendationResponse(BaseModel):
    items: List[RecommendationItem]
