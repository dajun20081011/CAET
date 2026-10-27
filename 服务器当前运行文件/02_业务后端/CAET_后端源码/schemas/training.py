from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class InitAdminIn(LoginIn):
    display_name: str = "管理员"


class UserCreateIn(LoginIn):
    display_name: str | None = None
    employee_no: str | None = None
    role: Literal["learner", "instructor", "admin"] = "learner"
    group_id: UUID | None = None


class UserUpdateIn(BaseModel):
    display_name: str | None = None
    employee_no: str | None = None
    role: Literal["learner", "instructor", "admin"] | None = None
    group_id: UUID | None = None
    is_active: bool | None = None


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task_type: Literal["practice", "exam"]
    course_id: int
    chapter_from: int = 1
    chapter_to: int = 1
    day_from: int = 1
    day_to: int = 1
    start_at: datetime
    due_at: datetime
    completion_rule: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "closed"] = "active"
    learner_ids: list[UUID] = Field(default_factory=list)
    instructor_id: UUID | None = None


class ProgressIn(BaseModel):
    assignment_id: UUID
    content_id: str
    completed: bool = False
    effective_seconds: int = Field(default=0, ge=0, le=86400)
    last_position: dict[str, Any] | None = None


class EventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    event_value: dict[str, Any] | None = None
    assignment_id: UUID | None = None
    course_id: int | None = None
    content_id: str | None = None
    client_timestamp: datetime


class PracticeAttemptIn(BaseModel):
    assignment_id: UUID
    content_id: str
    transcript: str = ""
    audio_url: str | None = None


class ExamSubmitIn(BaseModel):
    assessment_type: Literal["broadcast_recording"] = "broadcast_recording"
    assignment_id: UUID
    content_id: str | None = None
    answers: dict[str, Any] = Field(default_factory=dict)
    attempt_no: int = 1


class GradeIn(BaseModel):
    score: float | None = Field(default=None, ge=0, le=100)
    feedback: str | None = Field(default=None, max_length=4000)
    status: Literal["graded", "resubmit"] = "graded"
