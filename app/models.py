# app/models.py
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, DateTime, Enum, Boolean, JSON, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .db import Base

# --- NEW: association table (no id column) ---
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




class SizeEnum(str, enum.Enum):
    xs="xs"; s="s"; m="m"; l="l"; xl="xl"

class EnergyEnum(str, enum.Enum):
    low="low"; medium="medium"; high="high"
    energized="energized"; neutral="neutral"; tired="tired"  # PM language

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.backlog, nullable=False)
    size = Column(Enum(SizeEnum), nullable=True)
    effort_minutes = Column(Integer, nullable=True)
    hard_due_at = Column(DateTime, nullable=True)
    soft_due_at = Column(DateTime, nullable=True)
    energy = Column(Enum(EnergyEnum), nullable=True)
    focus_score = Column(Float, nullable=True)
    checklist = Column(JSON, nullable=True)
    recurrence_rule = Column(Text, nullable=True)
    sort_order = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # point to the association table
    tags = relationship("Tag", secondary=task_tags, back_populates="tasks")
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=True)

class Tag(Base):
    __tablename__ = "tags"
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Goal(Base):
    __tablename__ = "goals"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
