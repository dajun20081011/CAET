# ============================================================
# CAET ORM 模型 — 对应 8 张表
# profiles, learner_groups, courses, course_content,
# tasks, task_assignments, learner_progress, learning_events
# ============================================================
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, JsonType


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    employee_no: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, nullable=False, default="learner")
    group_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearnerGroup(Base):
    __tablename__ = "learner_groups"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    # 课程类型：broadcast(广播词) | caet2(英文问答) | caet3(中译英)
    course_type: Mapped[str] = mapped_column(String, nullable=False, default="broadcast")
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseContent(Base):
    __tablename__ = "course_content"

    id: Mapped[UUID] = _uuid_pk()
    course_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_title: Mapped[str] = mapped_column(String, nullable=False)
    day_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_order: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, server_default="{}", default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    course_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    chapter_from: Mapped[int] = mapped_column(Integer, default=1)
    chapter_to: Mapped[int] = mapped_column(Integer, default=1)
    day_from: Mapped[int] = mapped_column(Integer, default=1)
    day_to: Mapped[int] = mapped_column(Integer, default=7)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completion_rule: Mapped[dict] = mapped_column(JsonType, nullable=False, server_default="{}", default=dict)
    status: Mapped[str] = mapped_column(String, default="active")
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    id: Mapped[UUID] = _uuid_pk()
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    instructor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String, default="not_started")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearnerProgress(Base):
    __tablename__ = "learner_progress"

    id: Mapped[UUID] = _uuid_pk()
    assignment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("course_content.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_position: Mapped[dict | None] = mapped_column(JsonType)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningEvent(Base):
    __tablename__ = "learning_events"

    # learning_events 的 id 是 BIGSERIAL 自增
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="SET NULL")
    )
    course_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL")
    )
    content_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("course_content.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_value: Mapped[dict | None] = mapped_column(JsonType)
    client_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assessment(Base):
    __tablename__ = "assessments"

    # 测评记录：id 为 BIGSERIAL 自增
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    assignment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("course_content.id", ondelete="SET NULL")
    )
    course_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL")
    )
    # 测评类型：broadcast_recording | english_qa | zh_to_en
    assessment_type: Mapped[str] = mapped_column(String, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    # 状态：submitted | graded | resubmit
    status: Mapped[str] = mapped_column(String, default="submitted")
    answers: Mapped[dict] = mapped_column(JsonType, nullable=False, server_default="{}", default=dict)
    score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    feedback: Mapped[str | None] = mapped_column(Text)
    instructor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
