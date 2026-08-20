# ============================================================
# CAET Pydantic 请求/响应模型
# 响应字段与 src/types/database.ts 及 src/lib/api.ts 对齐。
# ============================================================
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------- 用户 ----------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    employee_no: str | None = None
    role: str
    group_id: UUID | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    employee_no: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class InitAdminIn(BaseModel):
    email: str
    password: str
    display_name: str = "管理员"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------- 任务 / 作业 ----------------
class AssignmentOut(BaseModel):
    assignment_id: UUID
    task_id: UUID
    task_title: str
    course_id: UUID
    course_title: str
    course_type: str | None = None
    chapter_from: int
    chapter_to: int
    day_from: int
    day_to: int
    status: str
    progress_percent: float
    started_at: datetime | None = None
    completed_at: datetime | None = None
    due_at: datetime


class TaskDetailContentOut(BaseModel):
    id: UUID
    course_id: UUID
    chapter_no: int
    chapter_title: str
    day_no: int
    content_order: int
    content_type: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    # 当前学员完成情况
    completed: bool = False
    progress_id: UUID | None = None


class TaskDayOut(BaseModel):
    chapter_no: int
    day_no: int
    chapter_title: str
    contents: list = Field(default_factory=list)


class TaskDetailOut(BaseModel):
    task: dict
    course: dict | None = None
    days: list = Field(default_factory=list)
    assignment: dict


# ---------------- 管理端创建任务 ----------------
class TaskCreateIn(BaseModel):
    title: str
    course_id: UUID
    chapter_from: int = 1
    chapter_to: int = 1
    day_from: int = 1
    day_to: int = 7
    start_at: datetime
    due_at: datetime
    completion_rule: dict = Field(default_factory=dict)
    status: str = "active"
    learner_ids: list[UUID] = Field(default_factory=list)
    instructor_id: UUID | None = None  # 可选：创建时统一指派教员（仅 role=instructor|admin）


class TaskAdminOut(BaseModel):
    task: dict
    assignment_count: int = 0
    completed_count: int = 0
    completion_rate: float = 0.0


# ---------------- 课程内容 ----------------
class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    chapter_no: int
    chapter_title: str
    day_no: int
    content_order: int
    content_type: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# ---------------- 进度 ----------------
class ProgressUpsertIn(BaseModel):
    assignment_id: UUID
    content_id: UUID
    completed: bool = False
    effective_seconds: int = 0
    last_position: dict | None = None


class ProgressItemOut(BaseModel):
    progress_id: UUID
    assignment_id: UUID
    content_id: UUID
    completed: bool
    effective_seconds: int
    last_position: dict | None = None
    attempt_count: int
    chapter_no: int | None = None
    day_no: int | None = None
    content_type: str | None = None
    content_order: int | None = None
    chapter_title: str | None = None
    payload: dict = Field(default_factory=dict)


class ProgressGetOut(BaseModel):
    assignment: dict
    task: dict | None = None
    items: list = Field(default_factory=list)


# ---------------- 事件 ----------------
class EventIn(BaseModel):
    event_type: str
    event_value: dict | None = None
    assignment_id: UUID | None = None
    course_id: UUID | None = None
    content_id: UUID | None = None
    client_timestamp: datetime


class EventOut(BaseModel):
    id: int
    learner_id: UUID
    assignment_id: UUID | None = None
    course_id: UUID | None = None
    content_id: UUID | None = None
    event_type: str
    event_value: dict | None = None
    client_timestamp: datetime
    created_at: datetime


# ---------------- 学习记录 / 仪表盘（宽松结构） ----------------
class RecordOut(BaseModel):
    calendar_7d: list = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    recent_content: list = Field(default_factory=list)
    event_distribution: list = Field(default_factory=list)


class LearnerAdminOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    employee_no: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    assignment_count: int = 0
    completed_count: int = 0
    avg_progress: float = 0.0
    total_seconds: int = 0


class LearnerDetailOut(BaseModel):
    profile: dict
    assignments: list = Field(default_factory=list)
    duration_trend: list = Field(default_factory=list)
    events: list = Field(default_factory=list)


class DashboardOut(BaseModel):
    learning_people_count: int = 0
    overall_completion_rate: float = 0.0
    total_effective_seconds: int = 0
    avg_seconds_per_person: float = 0.0
    task_completion_count: int = 0
    content_completion_top5: list = Field(default_factory=list)
    daily_active_trend: list = Field(default_factory=list)


# ---------------- 上传 ----------------
class UploadOut(BaseModel):
    url: str
    filename: str


# ---------------- 班级（班级管理） ----------------
class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    learner_count: int = 0


class GroupCreateIn(BaseModel):
    name: str


class GroupUpdateIn(BaseModel):
    name: str


# ---------------- 用户 / 权限管理（管理员） ----------------
class UserCreateIn(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    employee_no: str | None = None
    role: str = "learner"  # admin | instructor | learner
    group_id: UUID | None = None


class UserUpdateIn(BaseModel):
    display_name: str | None = None
    employee_no: str | None = None
    role: str | None = None
    group_id: UUID | None = None
    is_active: bool | None = None


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    employee_no: str | None = None
    role: str
    group_id: UUID | None = None
    is_active: bool
    created_at: datetime


# ---------------- 测评（三类独立） ----------------
class AssessmentSubmitIn(BaseModel):
    # broadcast_recording | english_qa | zh_to_en
    assessment_type: str
    assignment_id: UUID
    content_id: UUID | None = None
    answers: dict = Field(default_factory=dict)
    attempt_no: int = 1


class AssessmentGradeIn(BaseModel):
    score: float | None = None
    feedback: str | None = None
    status: str = "graded"  # graded | resubmit


class AssessmentOut(BaseModel):
    id: int
    assignment_id: UUID
    learner_id: UUID
    content_id: UUID | None = None
    course_id: UUID | None = None
    assessment_type: str
    attempt_no: int
    status: str
    answers: dict = Field(default_factory=dict)
    score: float | None = None
    feedback: str | None = None
    instructor_id: UUID | None = None
    graded_at: datetime | None = None
    created_at: datetime
    # 关联冗余字段（列表展示用）
    learner_name: str | None = None
    task_title: str | None = None
    course_title: str | None = None
