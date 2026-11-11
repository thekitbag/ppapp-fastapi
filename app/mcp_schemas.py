"""MCP write contracts; REST models remain the source of persisted fields."""
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas import GoalType, GoalStatus, Status, PlanRefFields, FIBONACCI_SIZES


class WriteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('end_date', 'soft_due_at', 'hard_due_at', check_fields=False)
    @classmethod
    def utc_dates(cls, value):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @field_validator('key', check_fields=False)
    @classmethod
    def clean_key(cls, value):
        if value is None:
            return None
        if not value.strip():
            raise ValueError('Batch keys cannot be blank')
        return value.strip()

    @field_validator('title', check_fields=False)
    @classmethod
    def clean_title(cls, value):
        if value is None or not value.strip():
            raise ValueError('Title cannot be empty or null')
        return value.strip()

    @field_validator('tags', 'add_tags', 'remove_tags', check_fields=False)
    @classmethod
    def clean_tags(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Tag names cannot be blank')
        return list(dict.fromkeys(value.strip() for value in values))


class GoalDraft(PlanRefFields, WriteInput):
    type: GoalType
    title: str
    parent: str | None = None
    end_date: datetime | None = None
    description: str | None = None


class TaskDraft(WriteInput):
    title: str
    description: str | None = None
    goals: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: Status = 'backlog'
    soft_due_at: datetime | None = None
    hard_due_at: datetime | None = None
    size: int | None = None
    project: str | None = None

    @field_validator('size')
    @classmethod
    def fibonacci_size(cls, value):
        if value is not None and value not in FIBONACCI_SIZES:
            raise ValueError('Size must be a Fibonacci number: 1, 2, 3, 5, 8, 13 or 21')
        return value


class BatchGoal(GoalDraft):
    key: str | None = Field(default=None, min_length=1)


class BatchTask(TaskDraft):
    key: str | None = Field(default=None, min_length=1)


class TaskPatch(WriteInput):
    title: str | None = None
    description: str | None = None
    status: Status | None = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)
    add_goals: list[str] = Field(default_factory=list)
    remove_goals: list[str] = Field(default_factory=list)
    soft_due_at: datetime | None = None
    hard_due_at: datetime | None = None

    @model_validator(mode='after')
    def required_values(self):
        if 'status' in self.model_fields_set and self.status is None:
            raise ValueError('Status cannot be null')
        if set(self.add_tags) & set(self.remove_tags):
            raise ValueError('The same tag cannot be added and removed together')
        return self


class GoalPatch(PlanRefFields, WriteInput):
    title: str | None = None
    status: GoalStatus | None = None
    end_date: datetime | None = None
    description: str | None = None

    @model_validator(mode='after')
    def required_values(self):
        if 'status' in self.model_fields_set and self.status is None:
            raise ValueError('Status cannot be null')
        return self
