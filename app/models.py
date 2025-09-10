# app/models.py
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, DateTime, Enum, Boolean, JSON, Table, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from .db import Base

# Association table for many-to-many relationship between tasks and tags
task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class StatusEnum(str, enum.Enum):
    backlog = "backlog"
    doing = "doing"
    done = "done"
    week = "week"
    today = "today"
    waiting = "waiting"
    archived = "archived"


class SizeEnum(str, enum.Enum):
    xs = "xs"
    s = "s"
    m = "m"
    l = "l"
    xl = "xl"


class EnergyEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    energized = "energized"
    neutral = "neutral"
    tired = "tired"


class GoalTypeEnum(str, enum.Enum):
    annual = "annual"
    quarterly = "quarterly"
    weekly = "weekly"


class GoalStatusEnum(str, enum.Enum):
    on_target = "on_target"
    at_risk = "at_risk"
    off_target = "off_target"


class ProviderEnum(str, enum.Enum):
    microsoft = "microsoft"
    google = "google"


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(Enum(ProviderEnum), nullable=False)
    provider_sub = Column(String, nullable=False)  # The stable subject/oid from IdP
    email = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships
    tasks = relationship("Task", back_populates="user")
    tags = relationship("Tag", back_populates="user")
    energy_states = relationship("EnergyState", back_populates="user")
    projects = relationship("Project", back_populates="user")
    goals = relationship("Goal", back_populates="user")
    goal_krs = relationship("GoalKR", back_populates="user")
    task_goals = relationship("TaskGoal", back_populates="user")
    
    __table_args__ = (
        UniqueConstraint("provider", "provider_sub", name="uq_user_provider_sub"),
        Index("ix_users_email", "email"),
    )

class Task(Base):
    __tablename__ = "tasks"
    
    # Primary key and basic info
    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    
    # Status and workflow
    status = Column(Enum(StatusEnum), default=StatusEnum.week, nullable=False)
    size = Column(Enum(SizeEnum), nullable=True)
    effort_minutes = Column(Integer, nullable=True)
    
    # Due dates
    hard_due_at = Column(DateTime, nullable=True)
    soft_due_at = Column(DateTime, nullable=True)
    
    # Energy and focus
    energy = Column(Enum(EnergyEnum), nullable=True)
    focus_score = Column(Float, nullable=True)
    
    # Task details
    checklist = Column(JSON, nullable=True)
    recurrence_rule = Column(Text, nullable=True)
    sort_order = Column(Float, nullable=False, default=0.0)
    
    # Foreign keys
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=True)  # Deprecated - keep for backward compatibility
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tags = relationship("Tag", secondary=task_tags, back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    goal_links = relationship("TaskGoal", back_populates="task", cascade="all, delete-orphan")
    user = relationship("User", back_populates="tasks")
    
    __table_args__ = (
        Index("ix_tasks_status_sort_order", "status", "sort_order"),
        Index("ix_tasks_user_status_sort", "user_id", "status", "sort_order"),
    )


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    tasks = relationship("Task", secondary=task_tags, back_populates="tags")
    user = relationship("User", back_populates="tags")
    
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_tag_name"),
    )


class EnergyState(Base):
    __tablename__ = "energy_state"
    
    id = Column(String, primary_key=True)
    value = Column(Enum(EnergyEnum), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String, default="manual", nullable=False)  # manual|inferred
    confidence = Column(Float, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    user = relationship("User", back_populates="energy_states")

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    milestone_title = Column(Text, nullable=True)
    milestone_due_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    tasks = relationship("Task", back_populates="project")
    user = relationship("User", back_populates="projects")

class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(GoalTypeEnum), nullable=True)
    
    # Goals v2 fields - hierarchy, status, and timing
    parent_goal_id = Column(String, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(GoalStatusEnum), nullable=False, default=GoalStatusEnum.on_target)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    key_results = relationship("GoalKR", back_populates="goal", cascade="all, delete-orphan")
    task_links = relationship("TaskGoal", back_populates="goal", cascade="all, delete-orphan")
    user = relationship("User", back_populates="goals")
    
    # Hierarchy relationships
    parent = relationship("Goal", remote_side=[id], back_populates="children")
    children = relationship("Goal", back_populates="parent")

class GoalKR(Base):
    __tablename__ = "goal_krs"
    
    id = Column(String, primary_key=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False)
    name = Column(Text, nullable=False)
    target_value = Column(Float, nullable=False)
    unit = Column(Text, nullable=True)
    baseline_value = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    goal = relationship("Goal", back_populates="key_results")
    user = relationship("User", back_populates="goal_krs")

class TaskGoal(Base):
    __tablename__ = "task_goals"
    
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False)
    weight = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)  # Will be NOT NULL after backfill
    
    # Relationships
    task = relationship("Task", back_populates="goal_links")
    goal = relationship("Goal", back_populates="task_links")
    user = relationship("User", back_populates="task_goals")
