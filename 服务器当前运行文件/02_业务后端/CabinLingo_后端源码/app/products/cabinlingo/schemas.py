from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class BroadcastOut(BaseModel):
    id: str
    code: str
    title: str
    language: str = "en-US"
    segment_count: int = 0
    status: Literal["draft", "published", "archived"] = "published"


class BroadcastCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="en-US", min_length=2, max_length=20)
    status: Literal["draft", "published"] = "draft"


class BroadcastUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    status: Literal["draft", "published", "archived"] | None = None


class PracticeTaskCreate(BaseModel):
    title: str = Field(min_length=1)
    broadcast_id: str | None = None
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    broadcast_script_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    due_at: datetime | None = None
    week_no: int | None = Field(default=None, ge=1, le=52)
    unlock_after_task_type: Literal["practice", "exam"] | None = None
    unlock_after_task_id: str | None = None
    completion_rule: dict[str, Any] = Field(default_factory=lambda: {"min_attempts": 1})

    @model_validator(mode="after")
    def validate_source(self):
        if self.broadcast_script_ids and len(set(self.broadcast_script_ids)) != len(self.broadcast_script_ids):
            raise ValueError("Broadcast script sources must be unique")
        if sum((self.broadcast_id is not None, self.course_version_id is not None,
                self.broadcast_script_id is not None, bool(self.broadcast_script_ids))) != 1:
            raise ValueError("Choose exactly one task source")
        if (self.unlock_after_task_type is None) != (self.unlock_after_task_id is None):
            raise ValueError("Choose both the prerequisite task type and task")
        if self.unlock_after_task_id and self.week_no is None:
            raise ValueError("A prerequisite task requires a week number")
        return self


class PracticeTaskOut(BaseModel):
    id: str
    title: str
    broadcast_id: str | None = None
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    due_at: datetime | None = None
    week_no: int | None = None
    unlock_after_task_type: Literal["practice", "exam"] | None = None
    unlock_after_task_id: str | None = None
    completion_rule: dict[str, Any] = Field(default_factory=lambda: {"min_attempts": 1})
    status: Literal["draft", "published", "closed"] = "draft"
    task_type: Literal["practice"] = "practice"


class TaskListItem(BaseModel):
    id: str
    title: str
    broadcast_id: str | None = None
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    broadcast_script_count: int = 0
    due_at: datetime | None = None
    week_no: int | None = None
    unlock_after_task_type: Literal["practice", "exam"] | None = None
    unlock_after_task_id: str | None = None
    status: str
    task_type: Literal["practice", "exam"]
    assignment_count: int = 0
    completed_count: int = 0


class PracticeAttemptCreate(BaseModel):
    assignment_id: str
    segment_id: str
    audio_ref: str
    reference_text: str


class PracticeFeedback(BaseModel):
    attempt_id: str
    mode: Literal["practice"] = "practice"
    ai_status: str
    issues: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str = "review_feedback_and_retry"
    attempt_no: int


class AssignmentCreate(BaseModel):
    user_id: str


class AssignmentBatchCreate(BaseModel):
    user_ids: list[str] = Field(default_factory=list, max_length=500)
    class_ids: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def require_target(self):
        if not self.user_ids and not self.class_ids:
            raise ValueError("Select at least one learner or class")
        return self


class AssignmentOut(BaseModel):
    id: str
    task_id: str
    user_id: str
    status: str
    task_type: Literal["practice", "exam"]


class ProgressOut(BaseModel):
    user_id: str
    assignment_id: str
    task_id: str
    task_type: Literal["practice"] = "practice"
    attempts: int
    status: str


class ExamTaskCreate(BaseModel):
    title: str = Field(min_length=1)
    broadcast_id: str | None = None
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    broadcast_script_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    max_recordings: int = Field(default=1, ge=1, le=10)
    due_at: datetime | None = None
    week_no: int | None = Field(default=None, ge=1, le=52)
    unlock_after_task_type: Literal["practice", "exam"] | None = None
    unlock_after_task_id: str | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if self.broadcast_script_ids and len(set(self.broadcast_script_ids)) != len(self.broadcast_script_ids):
            raise ValueError("Broadcast script sources must be unique")
        if sum((self.broadcast_id is not None, self.course_version_id is not None,
                self.broadcast_script_id is not None, bool(self.broadcast_script_ids))) != 1:
            raise ValueError("Choose exactly one task source")
        if (self.unlock_after_task_type is None) != (self.unlock_after_task_id is None):
            raise ValueError("Choose both the prerequisite task type and task")
        if self.unlock_after_task_id and self.week_no is None:
            raise ValueError("A prerequisite task requires a week number")
        return self


class ExamTaskOut(BaseModel):
    id: str
    title: str
    broadcast_id: str | None = None
    course_version_id: str | None = None
    broadcast_script_id: str | None = None
    max_recordings: int = Field(default=1, ge=1, le=10)
    due_at: datetime | None = None
    week_no: int | None = None
    unlock_after_task_type: Literal["practice", "exam"] | None = None
    unlock_after_task_id: str | None = None
    status: Literal["draft", "published", "open", "closed"] = "draft"
    task_type: Literal["exam"] = "exam"


class ExamSubmit(BaseModel):
    assignment_id: str
    recording_refs: list[str] = Field(min_length=1)
    paper_item_ids: list[str] = Field(min_length=1)


class ExamSubmissionOut(BaseModel):
    assignment_id: str
    task_type: Literal["exam"] = "exam"
    status: Literal["submitted"] = "submitted"
    recording_count: int
    max_recordings: int
    submitted_at: datetime


class AssessmentOut(BaseModel):
    submission_id: str
    ai_status: Literal["pending", "completed"] = "pending"
    manual_status: Literal["pending", "completed"] = "pending"
    score_status: Literal["unpublished", "published"] = "unpublished"


class RecordingCreate(BaseModel):
    assignment_id: str
    purpose: Literal["practice", "exam"]
    audio_ref: str = Field(min_length=1, max_length=500)
    duration_ms: int | None = Field(default=None, ge=0)


class RecordingOut(BaseModel):
    id: str
    assignment_id: str
    purpose: Literal["practice", "exam"]
    audio_ref: str
    status: Literal["uploaded"] = "uploaded"


class ReviewQueueItem(BaseModel):
    assignment_id: str
    task_id: str
    user_id: str
    status: str
    submitted_at: datetime | None = None
    ai_status: str = "pending"
    manual_status: str = "pending"


class ManualReviewCreate(BaseModel):
    manual_score: float = Field(ge=0, le=100)
    comments: str = Field(default="", max_length=4000)
    publish: bool = False


class UserOut(BaseModel):
    id: str
    external_ref: str | None = None
    display_name: str
    email: str | None = None
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    class_id: str | None = None


class UserCreate(BaseModel):
    account: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=1024)
    role: Literal["learner", "evaluator", "instructor", "admin"] = "learner"
    email: str | None = None
    class_id: str | None = None


class UserImportRow(BaseModel):
    """A loose row schema so one invalid row does not reject the whole import."""
    account: str = Field(default="", max_length=160)
    display_name: str = Field(default="", max_length=160)
    password: str = Field(default="", max_length=1024)
    role: str = Field(default="learner", max_length=40)
    email: str | None = Field(default=None, max_length=320)
    class_id: str | None = Field(default=None, max_length=80)


class UserImportRequest(BaseModel):
    rows: list[UserImportRow] = Field(min_length=1, max_length=500)


class UserImportError(BaseModel):
    row: int
    account: str = ""
    message: str


class UserImportResult(BaseModel):
    imported: int
    failed: int
    users: list[UserOut] = Field(default_factory=list)
    errors: list[UserImportError] = Field(default_factory=list)


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="broadcast", min_length=1, max_length=60)
    organization_id: str | None = None


class CourseOut(CourseCreate):
    id: str
    status: Literal["draft", "published", "archived"]
    version_count: int = 0
    published_version_id: str | None = None


class CourseVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=40)
    change_summary: str = Field(default="", max_length=2000)


class CourseVersionOut(BaseModel):
    id: str
    course_id: str
    version_no: int
    version_label: str
    status: Literal["draft", "published", "archived"]
    change_summary: str = ""
    chapter_count: int = 0
    content_count: int = 0
    published_at: datetime | None = None


class CourseMistakeWord(BaseModel):
    language: Literal["zh", "en"]
    term: str = Field(min_length=1, max_length=200)
    pronunciation: str = Field(default="", max_length=500)
    meaning: str = Field(default="", max_length=2000)
    common_mistake: str = Field(default="", max_length=2000)
    tip: str = Field(default="", max_length=2000)


class CourseV23DraftCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title_zh: str = Field(min_length=1, max_length=200)
    title_en: str = Field(default="", max_length=200)
    category: str = Field(min_length=1, max_length=60)
    summary: str = Field(default="", max_length=4000)
    language: Literal["zh", "en", "bilingual"] = "bilingual"
    version_label: str = Field(default="V1.0", min_length=1, max_length=40)
    organization_id: str | None = None
    course_kind: Literal["lesson", "expression_skill"] = "lesson"
    content_mode: Literal["audio_text", "video"] = "audio_text"
    training_enabled: bool = True
    content_config: dict[str, Any] = Field(default_factory=dict)
    explanation: str = Field(default="", max_length=20000)
    annotated_scripts: dict[str, str] = Field(default_factory=dict)
    delivery_tone: list[str] = Field(default_factory=list, max_length=12)
    delivery_pace: str = Field(default="", max_length=100)
    delivery_rhythm: list[str] = Field(default_factory=list, max_length=12)
    pronunciation_notes: str = Field(default="", max_length=4000)
    mistake_words: list[CourseMistakeWord] = Field(default_factory=list, max_length=100)
    cos_video_key: str | None = Field(default=None, max_length=1024)
    cos_video_filename: str | None = Field(default=None, max_length=255)
    cos_video_size: int | None = Field(default=None, ge=0)
    cos_video_etag: str | None = Field(default=None, max_length=255)
    sort_order: int = Field(default=0, ge=0, le=999999)
    publish_scope: Literal["all_authorized", "classes"] = "all_authorized"
    publish_class_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def normalize_expression_skill_fields(cls, data):
        if isinstance(data, dict) and data.get("course_kind") == "expression_skill" and data.get("content_mode") == "video":
            normalized = dict(data)
            normalized["mistake_words"] = []
            return normalized
        return data

    @model_validator(mode="after")
    def validate_detail(self):
        if self.course_kind == "expression_skill" and self.content_mode == "video":
            return self
        expected = {"zh", "en"} if self.language == "bilingual" else {self.language}
        missing = [language for language in expected if not self.annotated_scripts.get(language, "").strip()]
        if missing:
            raise ValueError(f"专业标注原文缺少语言：{','.join(missing)}")
        if not self.mistake_words:
            raise ValueError("至少需要一条易错词")
        return self


class CourseV23DetailOut(BaseModel):
    id: str
    course_id: str
    course_version_id: str
    content_item_id: str
    code: str
    title_zh: str
    title_en: str = ""
    category: str
    summary: str
    language: Literal["zh", "en", "bilingual"]
    version_label: str
    status: Literal["draft", "published", "archived"]
    course_status: Literal["draft", "published", "archived"] = "draft"
    has_published_version: bool = False
    task_count: int = 0
    active_task_count: int = 0
    course_kind: Literal["lesson", "expression_skill"] = "lesson"
    content_mode: Literal["audio_text", "video"] = "audio_text"
    training_enabled: bool = True
    content_config: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    annotated_scripts: dict[str, str] = Field(default_factory=dict)
    delivery_tone: list[str] = Field(default_factory=list)
    delivery_pace: str = ""
    delivery_rhythm: list[str] = Field(default_factory=list)
    pronunciation_notes: str = ""
    mistake_words: list[CourseMistakeWord] = Field(default_factory=list)
    cover_filename: str | None = None
    cover_url: str | None = None
    video_filename: str | None = None
    video_url: str | None = None
    cos_video_key: str | None = None
    cos_video_filename: str | None = None
    cos_video_size: int | None = None
    cos_video_etag: str | None = None
    sort_order: int = 0
    publish_scope: Literal["all_authorized", "classes"] = "all_authorized"
    publish_class_ids: list[str] = Field(default_factory=list)
    audio_filename: str | None = None
    audio_url: str | None = None
    audio_zh_filename: str | None = None
    audio_zh_url: str | None = None
    audio_en_filename: str | None = None
    audio_en_url: str | None = None
    audio_tracks: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    updated_at: datetime | None = None


class CosVideoObjectOut(BaseModel):
    key: str
    filename: str
    size: int
    etag: str = ""
    last_modified: str = ""


class CosVideoListOut(BaseModel):
    bucket: str
    prefix: str
    items: list[CosVideoObjectOut] = Field(default_factory=list)
    next_marker: str = ""
    is_truncated: bool = False


class CosVideoKeyRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024)


class CosVideoPlaybackOut(BaseModel):
    url: str
    expires_in: int
    video: CosVideoObjectOut


class CourseImportError(BaseModel):
    row: int | None = None
    course_id: str = ""
    message: str


class CourseImportResult(BaseModel):
    batch_id: str | None = None
    total: int
    created: int
    failed: int
    drafts: list[CourseV23DetailOut] = Field(default_factory=list)
    errors: list[CourseImportError] = Field(default_factory=list)


class CourseMistakeImportError(BaseModel):
    row: int | None = None
    course_id: str = ""
    language: str = ""
    term: str = ""
    message: str


class CourseMistakeImportPreview(BaseModel):
    incoming: int
    created: int
    updated: int
    skipped: int
    invalid: int
    total_after_merge: int
    mistake_words: list[CourseMistakeWord] = Field(default_factory=list)
    errors: list[CourseMistakeImportError] = Field(default_factory=list)


class PPTImportOut(BaseModel):
    course_version_id: str
    chapter_id: str
    chapter_title: str
    slides_imported: int
    content_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PDFImportOut(BaseModel):
    course_version_id: str
    chapter_id: str
    chapter_title: str
    pages_imported: int
    content_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChapterCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    sequence_no: int = Field(ge=1)
    learning_objective: str = Field(default="", max_length=4000)


class ChapterOut(ChapterCreate):
    id: str
    course_version_id: str
    content_count: int = 0


class HTMLImportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_filename: str = Field(min_length=1, max_length=255)
    source_html: str = Field(min_length=1)
    sequence_no: int = Field(ge=1)


class ContentItemOut(BaseModel):
    id: str
    chapter_id: str
    content_type: Literal["html", "broadcast", "audio", "document"]
    title: str
    sequence_no: int
    source_filename: str | None = None
    sanitized_html: str | None = None
    original_sha256: str | None = None
    sanitized_sha256: str | None = None
    validation_report: dict[str, Any] = Field(default_factory=dict)
    interaction_count: int = 0
    learning_card_id: str | None = None


class ContentAssetOut(BaseModel):
    id: str
    content_item_id: str
    asset_role: str = "attachment"
    original_filename: str | None = None
    mime_type: str
    byte_size: int
    url: str


InteractionType = Literal["choice", "hotspot", "fill_blank"]


class ContentInteractionCreate(BaseModel):
    interaction_type: InteractionType
    title: str = Field(default="互动练习", min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list, max_length=20)
    correct_answer: str = Field(default="", max_length=1000)
    accepted_answers: list[str] = Field(default_factory=list, max_length=20)
    feedback_correct: str = Field(default="回答正确，继续保持。", max_length=2000)
    feedback_incorrect: str = Field(default="再看一下课程内容，再试一次。", max_length=2000)
    required: bool = True
    sequence_no: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_interaction(self):
        if self.interaction_type in {"choice", "hotspot"} and len(self.options) < 2:
            raise ValueError("选择或点击互动至少需要两个选项")
        if self.interaction_type in {"choice", "hotspot"} and self.correct_answer not in self.options:
            raise ValueError("正确答案必须是选项之一")
        if self.interaction_type == "fill_blank" and not (self.accepted_answers or self.correct_answer.strip()):
            raise ValueError("填空互动至少需要一个可接受答案")
        return self


class ContentInteractionUpdate(ContentInteractionCreate):
    pass


class ContentInteractionOut(ContentInteractionCreate):
    id: str
    content_item_id: str
    status: Literal["draft", "published", "archived"] = "draft"
    version_no: int = 1
    created_at: datetime
    updated_at: datetime


class LearnerInteractionOut(BaseModel):
    id: str
    content_item_id: str
    interaction_type: InteractionType
    title: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    required: bool = True
    sequence_no: int = 1
    completed: bool = False
    attempt_count: int = 0


class InteractionAnswerCreate(BaseModel):
    assignment_id: str
    content_item_id: str
    answer: str = Field(default="", max_length=4000)


class InteractionAnswerOut(BaseModel):
    interaction_id: str
    assignment_id: str
    content_item_id: str
    is_correct: bool
    score: float
    feedback: str
    completed: bool
    attempt_count: int
    answer: str = ""


class CourseStandardSave(BaseModel):
    standard_text: str = Field(min_length=1, max_length=20000)
    stress_rules: str = Field(default="", max_length=4000)
    pronunciation_notes: str = Field(default="", max_length=4000)
    pause_rules: str = Field(default="", max_length=4000)
    tone_requirements: str = Field(default="", max_length=4000)
    rule_version: str = Field(default="1.0", min_length=1, max_length=40)
    change_summary: str = Field(default="", max_length=2000)


class CourseStandardOut(CourseStandardSave):
    id: str
    content_item_id: str
    standard_audio_file_id: str | None = None
    standard_audio_filename: str | None = None
    standard_audio_url: str | None = None
    created_at: datetime


class LearnerTaskOut(BaseModel):
    assignment_id: str
    task_id: str
    task_type: Literal["practice", "exam"]
    title: str
    status: str
    due_at: datetime | None = None
    course_version_id: str | None = None
    course_title: str
    version_label: str | None = None
    total_items: int = 0
    completed_items: int = 0
    attempt_count: int = 0
    progress_percent: int = Field(default=0, ge=0, le=100)
    next_content_item_id: str | None = None
    week_no: int | None = None
    locked: bool = False
    unlock_reason: str | None = None


class AdminLearnerBroadcastItemOut(BaseModel):
    assignment_id: str
    task_id: str
    task_title: str
    content_item_id: str
    content_title: str
    chapter_title: str
    chapter_sequence: int
    sequence_no: int
    progress_status: Literal["not_started", "in_progress", "completed"]
    attempt_count: int = 0
    required_attempts: int = 1
    completed_interactions: int = 0
    required_interactions: int = 0
    latest_attempt_id: str | None = None
    latest_attempt_at: datetime | None = None
    latest_ai_status: str | None = None
    latest_score: float | None = None
    review_status: Literal["not_submitted", "pending_review", "draft", "published"] = "not_submitted"


class TaskRosterLearnerOut(BaseModel):
    assignment_id: str
    learner_id: str
    display_name: str
    external_ref: str | None = None
    class_name: str | None = None
    assignment_status: str
    progress_status: Literal["not_started", "in_progress", "completed"]
    final_status: Literal["passed", "pending_review", "not_passed"]
    total_items: int = 0
    completed_items: int = 0
    attempt_count: int = 0
    progress_percent: int = Field(default=0, ge=0, le=100)
    pending_review: bool = False
    needs_retraining: bool = False


class TaskRosterOut(BaseModel):
    task_id: str
    task_type: Literal["practice", "exam"]
    task_title: str
    task_status: str
    total_count: int = 0
    passed_count: int = 0
    pending_review_count: int = 0
    not_passed_count: int = 0
    not_started_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    learners: list[TaskRosterLearnerOut] = Field(default_factory=list)


class LearnerHomeOut(BaseModel):
    practice_count: int
    exam_count: int
    completed_count: int
    total_attempts: int
    pending_feedback: int
    next_task: LearnerTaskOut | None = None


class LearnerContentOut(BaseModel):
    id: str
    chapter_id: str
    chapter_title: str
    chapter_sequence: int
    title: str
    sequence_no: int
    content_type: Literal["html", "broadcast", "audio", "document"] = "html"
    learning_card_id: str | None = None
    sanitized_html: str
    reference_text: str
    document_url: str | None = None
    document_page_no: int | None = None
    document_page_count: int | None = None
    assets: list[ContentAssetOut] = Field(default_factory=list)
    standard_audio_url: str | None = None
    stress_rules: str = ""
    pronunciation_notes: str = ""
    pause_rules: str = ""
    tone_requirements: str = ""
    rule_version: str | None = None
    attempt_count: int = 0
    latest_attempt_id: str | None = None
    latest_ai_status: str | None = None
    completed: bool = False
    interactions: list[LearnerInteractionOut] = Field(default_factory=list)
    required_interactions: int = 0
    completed_interactions: int = 0


class PracticeWorkspaceOut(BaseModel):
    assignment_id: str
    task_id: str
    task_title: str
    assignment_status: str
    course_title: str
    version_label: str
    minimum_attempts: int = 1
    progress_percent: int = Field(default=0, ge=0, le=100)
    contents: list[LearnerContentOut] = Field(default_factory=list)


class AudioUploadOut(BaseModel):
    recording_id: str
    audio_ref: str
    audio_url: str
    mime_type: str
    byte_size: int


class LearnerPracticeSubmit(BaseModel):
    assignment_id: str
    content_item_id: str
    recording_id: str
    correction_of_attempt_id: str | None = None
    recognized_text: str | None = Field(default=None, max_length=12000)


class LearnerAttemptOut(BaseModel):
    attempt_id: str
    assignment_id: str
    content_item_id: str | None = None
    content_title: str
    attempt_no: int
    ai_status: str
    score_summary: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    overall_score: float | None = None
    speed: int | None = None
    duration_seconds: float | None = None
    rear_tone: str | None = None
    word_details: list[dict[str, Any]] = Field(default_factory=list)
    word_detail_level: Literal["word", "sentence"] | None = None
    word_detail_count: int = 0
    recognized_text: str | None = None
    browser_transcript: str | None = None
    iat_transcript: str | None = None
    transcript_source: str | None = None
    alignment: list[dict[str, Any]] = Field(default_factory=list)
    alignment_source: str | None = None
    alignment_provider: str | None = None
    next_action: str
    recording_url: str | None = None
    correction_of_attempt_id: str | None = None
    teacher_feedback: dict[str, Any] | None = None
    created_at: datetime


class TeacherFeedbackOut(BaseModel):
    id: str
    practice_attempt_id: str | None = None
    exam_assignment_id: str | None = None
    teacher_name: str
    summary: str
    correction_advice: str
    required_retraining: bool
    status: str
    published_at: datetime | None = None


class GrowthPoint(BaseModel):
    date: str
    attempts: int
    completed_tasks: int
    average_score: float | None = None


class GrowthProfileOut(BaseModel):
    total_attempts: int
    completed_tasks: int
    corrected_attempts: int
    feedback_count: int
    issue_counts: dict[str, int] = Field(default_factory=dict)
    trend: list[GrowthPoint] = Field(default_factory=list)


class InstructorQueueItem(BaseModel):
    review_type: Literal["practice", "exam"]
    target_id: str
    assignment_id: str
    task_id: str
    task_title: str
    learner_id: str
    learner_name: str
    class_id: str | None = None
    class_name: str | None = None
    content_title: str | None = None
    submitted_at: datetime
    ai_status: str
    review_status: Literal["pending", "draft", "published"]
    priority: Literal["normal", "overdue", "retraining"] = "normal"


class InstructorLearnerOut(BaseModel):
    learner_id: str
    learner_name: str
    external_ref: str | None = None
    class_id: str | None = None
    class_name: str | None = None
    assignment_types: list[str] = Field(default_factory=list)
    assigned_at: datetime
    submitted_count: int = 0
    pending_review_count: int = 0
    published_review_count: int = 0
    retraining_count: int = 0
    latest_submitted_at: datetime | None = None


class InstructorRecentPass(BaseModel):
    learner_id: str
    learner_name: str
    passed_at: datetime


class InstructorDashboard(BaseModel):
    pending_reviews: int = 0
    retraining_followups: int = 0
    today_completed: int = 0
    week_completed: int = 0
    week_total: int = 0
    week_retraining_completed: int = 0
    total_evaluations: int = 0
    month_evaluations: int = 0
    total_mentored: int = 0
    current_mentoring: int = 0
    passed_mentoring: int = 0
    active_mentoring: int = 0
    recent_passed: list[InstructorRecentPass] = Field(default_factory=list)


class InstructorReviewDetail(BaseModel):
    review_type: Literal["practice", "exam"]
    target_id: str
    assignment_id: str
    task_id: str
    task_title: str
    learner_id: str
    learner_name: str
    class_name: str | None = None
    content_title: str | None = None
    reference_text: str = ""
    recording_id: str | None = None
    recording_url: str | None = None
    recordings: list[dict[str, Any]] = Field(default_factory=list)
    submitted_at: datetime
    ai_status: str
    ai_scores: dict[str, Any] = Field(default_factory=dict)
    ai_issues: list[dict[str, Any]] = Field(default_factory=list)
    ai_evidence: dict[str, Any] = Field(default_factory=dict)
    overall_score: float | None = None
    speed: int | None = None
    duration_seconds: float | None = None
    rear_tone: str | None = None
    word_details: list[dict[str, Any]] = Field(default_factory=list)
    word_detail_level: Literal["word", "sentence"] | None = None
    word_detail_count: int = 0
    recognized_text: str | None = None
    alignment: list[dict[str, Any]] = Field(default_factory=list)
    alignment_source: str | None = None
    alignment_provider: str | None = None
    review: dict[str, Any] | None = None


class InstructorReviewSave(BaseModel):
    completeness_score: float | None = Field(default=None, ge=0, le=100)
    pronunciation_score: float | None = Field(default=None, ge=0, le=100)
    fluency_score: float | None = Field(default=None, ge=0, le=100)
    expression_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float | None = Field(default=None, ge=0, le=100)
    evidence: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=4000)
    correction_advice: str = Field(default="", max_length=4000)
    required_retraining: bool = False
    remediation_due_at: datetime | None = None


class InstructorReviewOut(InstructorReviewSave):
    id: str
    review_type: Literal["practice", "exam"]
    target_id: str
    reviewer_id: str
    revision_no: int
    status: Literal["draft", "published", "superseded"]
    reviewed_at: datetime | None = None
    published_at: datetime | None = None


class ClassReviewAnalytics(BaseModel):
    class_id: str
    class_name: str
    learner_count: int
    submitted_count: int
    pending_review_count: int
    published_review_count: int
    remediation_count: int
    average_score: float | None = None
