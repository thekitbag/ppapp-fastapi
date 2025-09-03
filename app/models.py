# app/models.py
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, DateTime, Enum, Boolean, JSON, Table, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

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
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tags = relationship("Tag", secondary=task_tags, back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    goal_links = relationship("TaskGoal", back_populates="task", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_tasks_status_sort_order", "status", "sort_order"),
    )


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    
    # Relationships
    tasks = relationship("Task", secondary=task_tags, back_populates="tags")


class EnergyState(Base):
    __tablename__ = "energy_state"
    
    id = Column(String, primary_key=True)
    value = Column(Enum(EnergyEnum), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String, default="manual", nullable=False)  # manual|inferred
    confidence = Column(Float, nullable=True)

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    milestone_title = Column(Text, nullable=True)
    milestone_due_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    tasks = relationship("Task", back_populates="project")

class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(GoalTypeEnum), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships - update to use many-to-many through task_goals
    key_results = relationship("GoalKR", back_populates="goal", cascade="all, delete-orphan")
    task_links = relationship("TaskGoal", back_populates="goal", cascade="all, delete-orphan")

class GoalKR(Base):
    __tablename__ = "goal_krs"
    
    id = Column(String, primary_key=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False)
    name = Column(Text, nullable=False)
    target_value = Column(Float, nullable=False)
    unit = Column(Text, nullable=True)
    baseline_value = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships
    goal = relationship("Goal", back_populates="key_results")

class TaskGoal(Base):
    __tablename__ = "task_goals"
    
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False)
    weight = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships
    task = relationship("Task", back_populates="goal_links")
    goal = relationship("Goal", back_populates="task_links")
