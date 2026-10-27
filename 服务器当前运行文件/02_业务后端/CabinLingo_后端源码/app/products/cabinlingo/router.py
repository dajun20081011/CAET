from uuid import uuid4
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import logging
from threading import Lock
from hashlib import sha256
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from ...core.rbac import Principal, assert_permission, get_principal
from ...core.config import settings
from ...integrations.oss import LocalObjectStorage, ObjectStorageError, build_object_storage
from ...integrations.provider_settings import DynamicAIGateway
from ...integrations.audio_transcoder import AudioTranscodeError, normalize_speech_audio
from .domain import ExamTask, PracticeTask, TrainingStore, new_id
from .schemas import (
    AssignmentCreate, AssignmentBatchCreate, BroadcastCreate, BroadcastUpdate,
    AssignmentOut,
    AssessmentOut,
    BroadcastOut,
    ExamSubmit,
    ExamTaskCreate,
    ExamTaskOut,
    ExamSubmissionOut,
    PracticeAttemptCreate,
    PracticeFeedback,
    PracticeTaskCreate,
    PracticeTaskOut,
    ProgressOut, RecordingCreate, RecordingOut, ReviewQueueItem, ManualReviewCreate,
    TaskListItem,
    ChapterCreate, ChapterOut, ContentItemOut, CourseCreate, CourseOut,
    CourseVersionCreate, CourseVersionOut, HTMLImportCreate,
    CourseStandardOut, CourseStandardSave,
    AudioUploadOut, GrowthProfileOut, LearnerAttemptOut, LearnerHomeOut,
    AdminLearnerBroadcastItemOut, LearnerPracticeSubmit, LearnerTaskOut, PracticeWorkspaceOut, TaskRosterOut, TeacherFeedbackOut,
    ClassReviewAnalytics, InstructorDashboard, InstructorLearnerOut, InstructorQueueItem, InstructorReviewDetail,
    InstructorReviewOut, InstructorReviewSave,
    PPTImportOut, PDFImportOut, ContentAssetOut,
    ContentInteractionCreate, ContentInteractionOut, ContentInteractionUpdate,
    InteractionAnswerCreate, InteractionAnswerOut,
    CourseImportResult, CourseMistakeImportPreview, CourseV23DetailOut, CourseV23DraftCreate,
    CosVideoKeyRequest, CosVideoListOut, CosVideoPlaybackOut,
)
from .html_sanitizer import sanitize_html
from .ppt_import import MAX_PPTX_BYTES, parse_pptx
from .broadcast_router import broadcast_repository
from .broadcast_service import BroadcastLibraryError
from .service import ExamService, LearnerPracticeService, PracticeService
from .storage import build_store
from .ai_runtime import provider_settings
from .course_v23_import import (
    MAX_EXCEL_BYTES, MAX_MEDIA_ZIP_BYTES, build_course_template, build_mistake_words_workbook,
    collect_course_media, merge_mistake_words, parse_mistake_words_workbook,
    read_media_zip, read_xlsx_tables, validate_course_tables,
)
from .course_media_security import CourseMediaAccessLogFilter, CourseMediaSigner, CourseMediaTokenError
from .course_audio_alignment import (
    CourseAudioAlignmentError,
    build_course_audio_alignment,
    cached_alignment_is_current,
)
from ...integrations.tencent_cos import (
    TencentCosError, TencentCosNotConfigured, TencentCosObjectMissing,
    TencentCosUnsupportedVideo, TencentCosVideoService,
)

router = APIRouter(prefix="/api/v1/cabinlingo", tags=["CabinLingo"])
MAX_COURSE_DOCUMENT_BYTES = 100 * 1024 * 1024
MAX_COURSE_DOCUMENT_PAGES = 200
store = build_store()
object_storage = build_object_storage(settings)
course_media_signer = CourseMediaSigner(settings.jwt_secret or "local-development-course-media")
cos_video_service = TencentCosVideoService(settings)
logging.getLogger("uvicorn.access").addFilter(CourseMediaAccessLogFilter())
ai_gateway = DynamicAIGateway(provider_settings, object_storage.read)
practice_service = PracticeService(store, ai_gateway)
exam_service = ExamService(store)
learner_practice_service = LearnerPracticeService(store, ai_gateway)
course_alignment_locks: dict[str, Lock] = {}
course_alignment_locks_guard = Lock()


def _course_alignment_lock(track_id: str, language: str) -> Lock:
    key = f"{track_id}:{language}"
    with course_alignment_locks_guard:
        return course_alignment_locks.setdefault(key, Lock())


def _ensure_course_audio_alignment(course_version_id: str, file_id: str, language: str) -> dict:
    course = store.get_course_v23(course_version_id, published_only=True)
    track = store.get_course_v23_audio_track(course_version_id, file_id)
    if not course or not track:
        raise LookupError("Course audio track not found")
    if language not in {"zh", "en"}:
        raise ValueError("Unsupported course language")
    source = str((course.get("annotated_scripts") or {}).get(language) or "")
    cached = (track.get("alignment") or {}).get(language)
    if cached_alignment_is_current(cached, source, language):
        return cached

    lock = _course_alignment_lock(str(track["id"]), language)
    with lock:
        track = store.get_course_v23_audio_track(course_version_id, file_id)
        if not track:
            raise LookupError("Course audio track not found")
        cached = ((track or {}).get("alignment") or {}).get(language)
        if cached_alignment_is_current(cached, source, language):
            return cached
        blob = object_storage.read(str(track["asset_ref"]))
        alignment = build_course_audio_alignment(
            source=source,
            language=language,
            blob=blob,
            effective_settings=provider_settings.effective_settings(),
        )
        store.save_course_v23_audio_alignment(str(track["id"]), language, alignment)
        return alignment


def _warm_course_audio_alignments(course: dict) -> None:
    languages = ["zh", "en"] if course.get("language") == "bilingual" else [str(course.get("language") or "zh")]
    for track in course.get("audio_tracks") or []:
        track_language = str(track.get("language") or "bilingual")
        for language in languages:
            if track_language not in {"bilingual", language}:
                continue
            try:
                _ensure_course_audio_alignment(str(course["course_version_id"]), str(track["file_id"]), language)
            except (CourseAudioAlignmentError, LookupError, ValueError):
                logging.getLogger(__name__).exception(
                    "Course audio alignment warmup failed: course_version_id=%s file_id=%s language=%s",
                    course.get("course_version_id"), track.get("file_id"), language,
                )


def _inline_content_disposition(filename: str) -> str:
    cleaned = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = cleaned.replace("\r", "").replace("\n", "").replace('"', "").strip() or "course-media"
    suffix = Path(cleaned).suffix.encode("ascii", "ignore").decode("ascii")
    fallback = f"course-media{suffix}"
    return f'inline; filename="{fallback}"; filename*=UTF-8\'\'{quote(cleaned, safe="")}'


def _course_media_range(range_header: str | None, size: int) -> tuple[int, int, bool]:
    if size <= 0:
        raise HTTPException(404, "课程媒体文件为空")
    if not range_header:
        return 0, size - 1, False
    try:
        unit, value = range_header.strip().split("=", 1)
        if unit.lower() != "bytes" or "," in value:
            raise ValueError
        first, last = value.split("-", 1)
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            if suffix <= 0:
                raise ValueError
            start, end = max(0, size - suffix), size - 1
        if start < 0 or start >= size or end < start:
            raise ValueError
        return start, end, True
    except (ValueError, TypeError):
        raise HTTPException(
            416,
            "无效的媒体分段请求",
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{size}"},
        )


def _course_media_chunks(path: Path, start: int, end: int, chunk_size: int = 256 * 1024):
    with path.open("rb") as source:
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _broadcast_task_course(script_id: str, created_by: str) -> str:
    try:
        script = broadcast_repository.get_script(script_id)
        if not script.get("enabled"):
            raise HTTPException(409, "Broadcast script is disabled")
        if not script.get("ready"):
            raise HTTPException(409, "Broadcast text and slices are incomplete")
        version = broadcast_repository.get_version(script["latest_version_id"])
        slices = broadcast_repository.list_slices(version["id"])
        return store.materialize_broadcast_course(script, version, slices, created_by)
    except BroadcastLibraryError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _broadcast_task_course_bundle(script_ids: list[str], created_by: str) -> str:
    try:
        sources = []
        for script_id in script_ids:
            script = broadcast_repository.get_script(script_id)
            if not script.get("enabled"):
                raise HTTPException(409, f"Broadcast script is disabled: {script.get('title', script_id)}")
            if not script.get("ready"):
                raise HTTPException(409, f"Broadcast text and slices are incomplete: {script.get('title', script_id)}")
            version = broadcast_repository.get_version(script["latest_version_id"])
            slices = broadcast_repository.list_slices(version["id"])
            sources.append((script, version, slices))
        return store.materialize_broadcast_course_bundle(sources, created_by)
    except BroadcastLibraryError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _assert_broadcast_task_publishable(task_type: str, task_id: str) -> None:
    task = store.get_practice_task(task_id) if task_type == "practice" else store.get_exam_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.broadcast_script_id:
        try:
            script = broadcast_repository.get_script(task.broadcast_script_id)
        except BroadcastLibraryError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        if not script.get("enabled"):
            raise HTTPException(409, "The broadcast script is disabled and cannot be published")


def _validate_task_unlock(task_type: str | None, task_id: str | None) -> None:
    if not task_id:
        return
    prerequisite = store.get_practice_task(task_id) if task_type == "practice" else store.get_exam_task(task_id)
    if not prerequisite:
        raise HTTPException(422, "前置周任务不存在或已删除")


def _assert_assignment_unlocked(task_type: str, assignment_id: str, user_id: str) -> None:
    if not store.is_assignment_unlocked(task_type, assignment_id, user_id):
        raise HTTPException(423, "请先完成上一周任务，完成后本周任务会自动解锁")


@router.get("/broadcasts", response_model=list[BroadcastOut])
async def list_broadcasts(query: str | None = Query(default=None), status: str | None = Query(default=None), principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    items = store.list_broadcasts()
    return [item for item in items if (not query or query.lower() in f"{item['code']} {item['title']}".lower()) and (not status or item.get("status") == status)]


@router.post("/broadcasts", response_model=BroadcastOut)
async def create_broadcast(data: BroadcastCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    try:
        return store.create_broadcast(data.code.strip(), data.title.strip(), data.language, data.status, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/broadcasts/{broadcast_id}", response_model=BroadcastOut)
async def update_broadcast(broadcast_id: str, data: BroadcastUpdate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    item = store.update_broadcast(broadcast_id, **data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(404, "Broadcast not found")
    return item


@router.get("/tasks", response_model=list[TaskListItem])
async def list_tasks(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    return store.list_tasks()


@router.post("/tasks/{task_type}/{task_id}/{action}", response_model=TaskListItem)
async def update_task_status(task_type: str, task_id: str, action: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if task_type not in {"practice", "exam"} or action not in {"publish", "close"}:
        raise HTTPException(400, "Invalid task action")
    if action == "publish":
        _assert_broadcast_task_publishable(task_type, task_id)
    status = "published" if action == "publish" and task_type == "practice" else "open" if action == "publish" else "closed"
    item = store.set_task_status(task_type, task_id, status)
    if not item:
        raise HTTPException(404, "Task not found")
    return item


@router.delete("/tasks/{task_type}/{task_id}", response_model=dict)
async def delete_task(task_type: str, task_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if task_type not in {"practice", "exam"}:
        raise HTTPException(400, "Invalid task type")
    if not store.delete_task(task_type, task_id, principal.user_id):
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, "task_type": task_type, "status": "deleted"}


@router.get("/dashboard", response_model=dict)
async def dashboard(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    tasks = store.list_tasks()
    return {
        "task_count": len(tasks),
        "practice_count": sum(item["task_type"] == "practice" for item in tasks),
        "exam_count": sum(item["task_type"] == "exam" for item in tasks),
        "published_count": sum(item["status"] in {"published", "open"} for item in tasks),
        "assignment_count": sum(item.get("assignment_count", 0) for item in tasks),
        "completed_count": sum(item.get("completed_count", 0) for item in tasks),
        "completion_rate": round(sum(item.get("completed_count", 0) for item in tasks) / max(sum(item.get("assignment_count", 0) for item in tasks), 1) * 100, 1),
    }


@router.post("/practice/tasks", response_model=PracticeTaskOut)
async def create_practice_task(data: PracticeTaskCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    _validate_task_unlock(data.unlock_after_task_type, data.unlock_after_task_id)
    if data.broadcast_id and not store.has_broadcast(data.broadcast_id):
        raise HTTPException(404, "Broadcast not found")
    if data.course_version_id and not store.has_course_version(data.course_version_id, published_only=True):
        raise HTTPException(409, "Course version must be published before task creation")
    course_version_id = data.course_version_id
    broadcast_script_id = data.broadcast_script_id
    if data.broadcast_script_ids:
        if len(data.broadcast_script_ids) == 1:
            broadcast_script_id = data.broadcast_script_ids[0]
            course_version_id = _broadcast_task_course(broadcast_script_id, principal.user_id)
        else:
            broadcast_script_id = None
            course_version_id = _broadcast_task_course_bundle(data.broadcast_script_ids, principal.user_id)
    elif broadcast_script_id:
        course_version_id = _broadcast_task_course(broadcast_script_id, principal.user_id)
    task = PracticeTask(
        id=new_id("pt"), title=data.title, broadcast_id=data.broadcast_id,
        due_at=data.due_at, completion_rule=data.completion_rule,
        course_version_id=course_version_id, broadcast_script_id=broadcast_script_id,
        week_no=data.week_no, unlock_after_task_type=data.unlock_after_task_type,
        unlock_after_task_id=data.unlock_after_task_id,
    )
    store.create_practice_task(task)
    return {"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id,
            "course_version_id": task.course_version_id, "broadcast_script_id": task.broadcast_script_id,
            "due_at": task.due_at, "completion_rule": task.completion_rule,
            "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type,
            "unlock_after_task_id": task.unlock_after_task_id,
            "status": task.status, "task_type": "practice"}


@router.get("/practice/tasks/{task_id}", response_model=PracticeTaskOut)
async def get_practice_task(task_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    task = store.get_practice_task(task_id)
    if not task:
        raise HTTPException(404, "Practice task not found")
    return {"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id, "course_version_id": task.course_version_id,
            "broadcast_script_id": task.broadcast_script_id, "due_at": task.due_at,
            "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type,
            "unlock_after_task_id": task.unlock_after_task_id,
            "completion_rule": task.completion_rule, "status": task.status, "task_type": "practice"}


@router.post("/practice/attempts", response_model=PracticeFeedback)
async def submit_practice_attempt(data: PracticeAttemptCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return await run_in_threadpool(practice_service.submit_attempt, data, principal.user_id)


@router.post("/practice/tasks/{task_id}/assignments", response_model=AssignmentOut)
async def assign_practice_task(task_id: str, data: AssignmentCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if not store.get_practice_task(task_id):
        raise HTTPException(404, "Practice task not found")
    assignment = store.create_practice_assignment(task_id, data.user_id)
    return {"id": assignment.id, "task_id": assignment.task_id, "user_id": assignment.user_id, "status": assignment.status, "task_type": "practice"}


@router.post("/practice/tasks/{task_id}/assignments/batch", response_model=list[AssignmentOut])
async def assign_practice_batch(task_id: str, data: AssignmentBatchCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if not store.get_practice_task(task_id):
        raise HTTPException(404, "Practice task not found")
    try:
        user_ids = store.resolve_task_assignee_ids(data.user_ids, data.class_ids, "practice")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = []
    for user_id in user_ids:
        assignment = store.create_practice_assignment(task_id, user_id)
        result.append({"id": assignment.id, "task_id": task_id, "user_id": user_id, "status": assignment.status, "task_type": "practice"})
    return result


@router.get("/practice/assignments", response_model=list[AssignmentOut])
async def list_practice_assignments(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    return [{"id": a.id, "task_id": a.task_id, "user_id": a.user_id, "status": a.status, "task_type": "practice"} for a in store.list_practice_assignments(principal.user_id)]


@router.get("/progress", response_model=list[ProgressOut])
async def list_progress(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    return store.list_practice_progress(principal.user_id)


@router.post("/exams/tasks", response_model=ExamTaskOut)
async def create_exam_task(data: ExamTaskCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    _validate_task_unlock(data.unlock_after_task_type, data.unlock_after_task_id)
    if data.broadcast_id and not store.has_broadcast(data.broadcast_id):
        raise HTTPException(404, "Broadcast not found")
    if data.course_version_id and not store.has_course_version(data.course_version_id, published_only=True):
        raise HTTPException(409, "Course version must be published before task creation")
    course_version_id = data.course_version_id
    broadcast_script_id = data.broadcast_script_id
    if data.broadcast_script_ids:
        if len(data.broadcast_script_ids) == 1:
            broadcast_script_id = data.broadcast_script_ids[0]
            course_version_id = _broadcast_task_course(broadcast_script_id, principal.user_id)
        else:
            broadcast_script_id = None
            course_version_id = _broadcast_task_course_bundle(data.broadcast_script_ids, principal.user_id)
    elif broadcast_script_id:
        course_version_id = _broadcast_task_course(broadcast_script_id, principal.user_id)
    task = ExamTask(
        id=new_id("et"), title=data.title, broadcast_id=data.broadcast_id,
        max_recordings=data.max_recordings, due_at=data.due_at,
        course_version_id=course_version_id, broadcast_script_id=broadcast_script_id,
        week_no=data.week_no, unlock_after_task_type=data.unlock_after_task_type,
        unlock_after_task_id=data.unlock_after_task_id,
    )
    store.create_exam_task(task)
    return {"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id,
            "course_version_id": task.course_version_id, "broadcast_script_id": task.broadcast_script_id,
            "max_recordings": task.max_recordings, "due_at": task.due_at,
            "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type,
            "unlock_after_task_id": task.unlock_after_task_id,
            "status": task.status, "task_type": "exam"}


@router.get("/exams/tasks/{task_id}", response_model=ExamTaskOut)
async def get_exam_task(task_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    task = store.get_exam_task(task_id)
    if not task:
        raise HTTPException(404, "Exam task not found")
    return {"id": task.id, "title": task.title, "broadcast_id": task.broadcast_id, "course_version_id": task.course_version_id,
            "broadcast_script_id": task.broadcast_script_id, "max_recordings": task.max_recordings,
            "week_no": task.week_no, "unlock_after_task_type": task.unlock_after_task_type,
            "unlock_after_task_id": task.unlock_after_task_id,
            "due_at": task.due_at, "status": task.status, "task_type": "exam"}


@router.post("/exams/tasks/{task_id}/assignments", response_model=AssignmentOut)
async def assign_exam_task(task_id: str, data: AssignmentCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if not store.get_exam_task(task_id):
        raise HTTPException(404, "Exam task not found")
    assignment = store.create_exam_assignment(task_id, data.user_id)
    return {"id": assignment.id, "task_id": assignment.task_id, "user_id": assignment.user_id, "status": assignment.status, "task_type": "exam"}


@router.post("/exams/tasks/{task_id}/assignments/batch", response_model=list[AssignmentOut])
async def assign_exam_batch(task_id: str, data: AssignmentBatchCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if not store.get_exam_task(task_id):
        raise HTTPException(404, "Exam task not found")
    try:
        user_ids = store.resolve_task_assignee_ids(data.user_ids, data.class_ids, "exam")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = []
    for user_id in user_ids:
        assignment = store.create_exam_assignment(task_id, user_id)
        result.append({"id": assignment.id, "task_id": task_id, "user_id": user_id, "status": assignment.status, "task_type": "exam"})
    return result


@router.get("/exams/assignments", response_model=list[AssignmentOut])
async def list_exam_assignments(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    return [{"id": a.id, "task_id": a.task_id, "user_id": a.user_id, "status": a.status, "task_type": "exam"} for a in store.list_exam_assignments(principal.user_id)]


@router.post("/exams/tasks/{task_id}/submit", response_model=ExamSubmissionOut)
async def submit_exam(task_id: str, data: ExamSubmit, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    _assert_assignment_unlocked("exam", data.assignment_id, principal.user_id)
    return exam_service.submit_whole_paper(data, principal.user_id, task_id=task_id)


@router.get("/assessments/{submission_id}", response_model=AssessmentOut)
async def get_assessment(submission_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    if not store.get_exam_assignment(submission_id, principal.user_id):
        raise HTTPException(404, "Submission not found")
    return {"submission_id": submission_id}


@router.post("/recordings", response_model=RecordingOut)
async def create_recording(data: RecordingCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    if data.purpose == "practice" and not store.get_practice_assignment(data.assignment_id, principal.user_id):
        raise HTTPException(404, "Practice assignment not found")
    if data.purpose == "exam" and not store.get_exam_assignment(data.assignment_id, principal.user_id):
        raise HTTPException(404, "Exam assignment not found")
    _assert_assignment_unlocked(data.purpose, data.assignment_id, principal.user_id)
    try:
        return store.create_recording(data.assignment_id, data.purpose, data.audio_ref, data.duration_ms)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/review/queue", response_model=list[ReviewQueueItem])
async def review_queue(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    return store.list_review_queue(principal.user_id)


@router.post("/review/{assignment_id}")
async def save_review(assignment_id: str, data: ManualReviewCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    try:
        payload = {
            "completeness_score": None, "pronunciation_score": None, "fluency_score": None,
            "expression_score": None, "final_score": data.manual_score, "evidence": {"source": "legacy_review_api"},
            "summary": data.comments.strip() or "人工评价", "correction_advice": "",
            "required_retraining": False, "remediation_due_at": None,
        }
        return store.save_instructor_review("exam", assignment_id, principal.user_id, payload, data.publish)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/courses", response_model=list[CourseOut])
async def list_courses(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.list_courses()


@router.post("/admin/courses", response_model=CourseOut)
async def create_course(data: CourseCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.create_course(
            data.code.strip(), data.title.strip(), data.description.strip(), data.category,
            data.organization_id, principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _course_v23_extension(mime_type: str) -> str:
    extensions = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/vnd.wave": ".wav",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
        "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/webm": ".webm",
        "audio/flac": ".flac", "audio/x-flac": ".flac",
        "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    }
    if mime_type not in extensions:
        raise ValueError("课程媒体格式不支持")
    return extensions[mime_type]


async def _save_course_v23_upload(course_code: str, role: str, upload: UploadFile, max_bytes: int) -> dict:
    body = await upload.read(max_bytes + 1)
    if not body:
        raise ValueError(f"{role} 文件为空")
    if len(body) > max_bytes:
        raise ValueError(f"{role} 文件超过大小限制")
    mime_type = (upload.content_type or "application/octet-stream").split(";", 1)[0].lower()
    mime_type = {
        "image/jpg": "image/jpeg", "audio/x-wav": "audio/wav", "audio/wave": "audio/wav",
        "audio/vnd.wave": "audio/wav", "audio/mp3": "audio/mpeg", "audio/x-m4a": "audio/mp4",
        "audio/x-flac": "audio/flac",
    }.get(mime_type, mime_type)
    filename_extension = Path(upload.filename or "").suffix.lower()
    inferred_types = {
        "cover": {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"},
        "video": {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"},
        "audio": {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".webm": "audio/webm", ".flac": "audio/flac"},
    }
    allowed_role = "audio" if role.startswith("audio") else role
    if filename_extension in inferred_types[allowed_role]:
        inferred_mime = inferred_types[allowed_role][filename_extension]
        if mime_type in {"application/octet-stream", "binary/octet-stream"}:
            mime_type = inferred_mime
    extension = _course_v23_extension(mime_type)
    allowed = {
        "cover": {"image/jpeg", "image/png", "image/webp"},
        "video": {"video/mp4", "video/webm", "video/quicktime"},
        "audio": {"audio/wav", "audio/mpeg", "audio/mp4", "audio/aac", "audio/ogg", "audio/webm", "audio/flac"},
    }
    if mime_type not in allowed[allowed_role]:
        raise ValueError(f"{role} 文件格式不支持")
    object_key = f"course-v23/{course_code}/{role}-{uuid4().hex}{extension}"
    asset_ref = object_storage.save(object_key, body, mime_type)
    return {"role": role, "asset_ref": asset_ref, "mime_type": mime_type, "byte_size": len(body), "filename": (upload.filename or f"{course_code}_{role}{extension}")[:255]}


@router.get("/admin/course-v23", response_model=list[CourseV23DetailOut])
async def list_course_v23(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.list_course_v23()


def _raise_cos_http_error(exc: TencentCosError) -> None:
    if isinstance(exc, TencentCosNotConfigured):
        raise HTTPException(503, "腾讯云 COS 尚未配置") from exc
    if isinstance(exc, TencentCosObjectMissing):
        raise HTTPException(404, "COS 视频不存在或已被移除") from exc
    if isinstance(exc, TencentCosUnsupportedVideo):
        raise HTTPException(422, str(exc)) from exc
    raise HTTPException(503, "腾讯云 COS 暂时不可用，请稍后重试") from exc


@router.get("/admin/cos-videos", response_model=CosVideoListOut)
async def list_cos_videos(
    search: str = Query(default="", max_length=200),
    marker: str = Query(default="", max_length=1024),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return await run_in_threadpool(cos_video_service.list_videos, search, marker, limit)
    except TencentCosError as exc:
        _raise_cos_http_error(exc)


@router.post("/admin/cos-videos/preview", response_model=CosVideoPlaybackOut)
async def preview_cos_video(payload: CosVideoKeyRequest, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return await run_in_threadpool(cos_video_service.signed_url, payload.key)
    except TencentCosError as exc:
        _raise_cos_http_error(exc)


@router.get("/admin/course-v23/template")
async def download_course_v23_template(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return Response(
        build_course_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="CabinLingo-Course-V2.3-Template.xlsx"'},
    )


def _mistake_import_preview(existing: list[dict], incoming: list[dict], errors: list[dict]) -> dict:
    merged = merge_mistake_words(existing, incoming)
    return {
        "incoming": len(incoming),
        "created": merged["created"],
        "updated": merged["updated"],
        "skipped": merged["skipped"],
        "invalid": len(errors),
        "total_after_merge": len(merged["mistake_words"]),
        "mistake_words": merged["mistake_words"],
        "errors": errors,
    }


@router.get("/admin/course-v23/mistake-words/template")
async def download_mistake_words_template(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return Response(
        build_mistake_words_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="CabinLingo-Mistake-Words-Template.xlsx"'},
    )


@router.post("/admin/course-v23/mistake-words/import/preview", response_model=CourseMistakeImportPreview)
async def preview_new_mistake_words_import(
    course_id: str = Form(...),
    existing: str = Form("[]"),
    excel: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    if not (excel.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "易错词模板必须是 .xlsx")
    try:
        current = json.loads(existing)
        if not isinstance(current, list):
            raise ValueError("existing 必须是数组")
        incoming, errors = parse_mistake_words_workbook(await excel.read(MAX_EXCEL_BYTES + 1), course_id.strip())
        return _mistake_import_preview(current, incoming, errors)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/admin/course-v23/{course_version_id}/mistake-words/export")
async def export_course_mistake_words(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    item = store.get_course_v23(course_version_id)
    if not item:
        raise HTTPException(404, "课程版本不存在")
    return Response(
        build_mistake_words_workbook(item["course_id"], item.get("mistake_words") or []),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{item["course_id"]}-mistake-words.xlsx"'},
    )


@router.post("/admin/course-v23/{course_version_id}/mistake-words/import/preview", response_model=CourseMistakeImportPreview)
async def preview_course_mistake_words_import(
    course_version_id: str,
    excel: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    item = store.get_course_v23(course_version_id)
    if not item:
        raise HTTPException(404, "课程版本不存在")
    if not (excel.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "易错词模板必须是 .xlsx")
    try:
        incoming, errors = parse_mistake_words_workbook(await excel.read(MAX_EXCEL_BYTES + 1), item["course_id"])
        return _mistake_import_preview(item.get("mistake_words") or [], incoming, errors)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/admin/course-v23/{course_version_id}/mistake-words/import", response_model=CourseV23DetailOut)
async def import_course_mistake_words(
    course_version_id: str,
    excel: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    item = store.get_course_v23(course_version_id)
    if not item:
        raise HTTPException(404, "课程版本不存在")
    if not (excel.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "易错词模板必须是 .xlsx")
    try:
        incoming, errors = parse_mistake_words_workbook(await excel.read(MAX_EXCEL_BYTES + 1), item["course_id"])
        if errors:
            raise ValueError("；".join(f"第 {error.get('row') or '-'} 行：{error['message']}" for error in errors))
        merged = merge_mistake_words(item.get("mistake_words") or [], incoming)
        return store.update_course_v23_mistake_words(course_version_id, merged["mistake_words"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/admin/course-v23/drafts", response_model=CourseV23DetailOut)
async def create_course_v23_draft(
    payload: str = Form(...),
    cover: UploadFile | None = File(default=None),
    video: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    audio_zh: UploadFile | None = File(default=None),
    audio_zh_2: UploadFile | None = File(default=None),
    audio_en: UploadFile | None = File(default=None),
    audio_en_2: UploadFile | None = File(default=None),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        data = CourseV23DraftCreate.model_validate(json.loads(payload)).model_dump()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, f"课程表单校验失败：{exc}") from exc
    requested_course_id = data["course_id"]
    data["course_id"] = store.next_available_course_code(requested_course_id, data.get("organization_id"))
    saved: list[dict] = []
    try:
        if cover:
            saved.append(await _save_course_v23_upload(data["course_id"], "cover", cover, 15 * 1024 * 1024))
        if video:
            saved.append(await _save_course_v23_upload(data["course_id"], "video", video, settings.course_media_max_bytes))
        if audio:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio", audio, settings.audio_max_bytes))
        if audio_zh:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_zh", audio_zh, settings.audio_max_bytes))
        if audio_zh_2:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_zh_2", audio_zh_2, settings.audio_max_bytes))
        if audio_en:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_en", audio_en, settings.audio_max_bytes))
        if audio_en_2:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_en_2", audio_en_2, settings.audio_max_bytes))
        return store.create_course_v23_draft(data, saved, principal.user_id)
    except (ValueError, ObjectStorageError) as exc:
        for item in saved:
            object_storage.delete(item["asset_ref"])
        raise HTTPException(409, str(exc)) from exc


@router.put("/admin/course-v23/drafts/{course_version_id}", response_model=CourseV23DetailOut)
async def update_course_v23_draft(
    course_version_id: str,
    payload: str = Form(...),
    expected_updated_at: str | None = Form(default=None),
    cover: UploadFile | None = File(default=None),
    video: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    audio_zh: UploadFile | None = File(default=None),
    audio_zh_2: UploadFile | None = File(default=None),
    audio_en: UploadFile | None = File(default=None),
    audio_en_2: UploadFile | None = File(default=None),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        data = CourseV23DraftCreate.model_validate(json.loads(payload)).model_dump()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, f"课程表单校验失败：{exc}") from exc
    saved: list[dict] = []
    try:
        if cover:
            saved.append(await _save_course_v23_upload(data["course_id"], "cover", cover, 15 * 1024 * 1024))
        if video:
            saved.append(await _save_course_v23_upload(data["course_id"], "video", video, settings.course_media_max_bytes))
        if audio:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio", audio, settings.audio_max_bytes))
        if audio_zh:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_zh", audio_zh, settings.audio_max_bytes))
        if audio_zh_2:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_zh_2", audio_zh_2, settings.audio_max_bytes))
        if audio_en:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_en", audio_en, settings.audio_max_bytes))
        if audio_en_2:
            saved.append(await _save_course_v23_upload(data["course_id"], "audio_en_2", audio_en_2, settings.audio_max_bytes))
        return store.update_course_v23_draft(course_version_id, data, saved, principal.user_id, expected_updated_at)
    except (ValueError, ObjectStorageError) as exc:
        for item in saved:
            object_storage.delete(item["asset_ref"])
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/course-v23/import", response_model=CourseImportResult)
async def import_course_v23(
    excel: UploadFile = File(...),
    media_zip: UploadFile | None = File(default=None),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    if not (excel.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "课程模板必须是 .xlsx")
    excel_body = await excel.read(MAX_EXCEL_BYTES + 1)
    zip_body = await media_zip.read(MAX_MEDIA_ZIP_BYTES + 1) if media_zip else b""
    try:
        drafts, errors = validate_course_tables(read_xlsx_tables(excel_body))
        media = read_media_zip(zip_body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    validation_error_count = len(errors)
    batch_id = store.start_course_import_batch(excel.filename or "courses.xlsx", media_zip.filename if media_zip else None, principal.user_id)
    created: list[dict] = []
    for row_number, draft in enumerate(drafts, 2):
        selected, media_errors = collect_course_media(draft, media)
        if media_errors:
            errors.append({"row": row_number, "course_id": draft["course_id"], "message": "；".join(media_errors)})
            continue
        saved: list[dict] = []
        try:
            for item in selected:
                extension = _course_v23_extension(item.mime_type)
                object_key = f"course-v23/{draft['course_id']}/{item.role}-{uuid4().hex}{extension}"
                asset_ref = object_storage.save(object_key, item.content, item.mime_type)
                saved.append({"role": item.role, "asset_ref": asset_ref, "mime_type": item.mime_type, "byte_size": len(item.content), "filename": item.filename})
            created.append(store.create_course_v23_draft(draft, saved, principal.user_id, batch_id))
        except (ValueError, ObjectStorageError) as exc:
            for item in saved:
                object_storage.delete(item["asset_ref"])
            errors.append({"row": row_number, "course_id": draft["course_id"], "message": str(exc)})
    total = len(drafts) + validation_error_count
    store.finish_course_import_batch(batch_id, total, len(created), errors)
    return {"batch_id": batch_id, "total": total, "created": len(created), "failed": len(errors), "drafts": created, "errors": errors}


@router.get("/admin/course-v23/{course_version_id}/preview", response_model=CourseV23DetailOut)
async def preview_course_v23(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    item = store.get_course_v23(course_version_id)
    if not item:
        raise HTTPException(404, "Course V2.3 draft not found")
    return item


@router.post("/admin/course-v23/{course_version_id}/revision", response_model=CourseV23DetailOut)
async def create_course_v23_revision(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.create_course_v23_revision(course_version_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/course-v23/{course_id}/enable", response_model=CourseV23DetailOut)
async def enable_course_v23(course_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.set_course_v23_status(course_id, "published")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/course-v23/{course_id}/disable", response_model=CourseV23DetailOut)
async def disable_course_v23(course_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.set_course_v23_status(course_id, "draft")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/admin/course-v23/{course_id}", response_model=CourseV23DetailOut)
async def delete_course_v23(course_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.set_course_v23_status(course_id, "archived")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/course-v23/{course_id}/restore", response_model=CourseV23DetailOut)
async def restore_course_v23(course_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.set_course_v23_status(course_id, "draft")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/course-v23/{course_version_id}/publish", response_model=CourseV23DetailOut)
async def publish_course_v23(course_version_id: str, background_tasks: BackgroundTasks,
                             principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        draft = store.get_course_v23(course_version_id)
        if not draft:
            raise ValueError("Course V2.3 draft not found")
        if draft.get("cos_video_key"):
            await run_in_threadpool(cos_video_service.head_video, draft["cos_video_key"])
        published = store.publish_course_v23(course_version_id, principal.user_id)
        background_tasks.add_task(_warm_course_audio_alignments, published)
        return published
    except TencentCosObjectMissing as exc:
        raise HTTPException(409, "发布失败：COS 视频不存在或已被移除，草稿已保留") from exc
    except TencentCosUnsupportedVideo as exc:
        raise HTTPException(409, f"发布失败：{exc}，草稿已保留") from exc
    except TencentCosError as exc:
        raise HTTPException(503, "发布前无法验证 COS 视频，草稿已保留，请稍后重试") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/learner/course-v23", response_model=list[CourseV23DetailOut])
async def learner_course_v23_catalog(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    return store.list_published_course_v23(principal.user_id)


@router.get("/learner/course-v23/{course_version_id}", response_model=CourseV23DetailOut)
async def learner_course_v23(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    item = store.get_published_course_v23_for_user(course_version_id, principal.user_id)
    if not item:
        raise HTTPException(404, "Published course not found")
    return item


@router.post("/learner/course-v23/{course_version_id}/video-playback", response_model=CosVideoPlaybackOut)
async def learner_course_v23_video_playback(
    course_version_id: str,
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    item = store.get_published_course_v23_for_user(course_version_id, principal.user_id)
    if not item:
        raise HTTPException(404, "课程不存在、已下架或无访问权限")
    if not item.get("cos_video_key"):
        raise HTTPException(404, "课程未关联 COS 视频")
    try:
        return await run_in_threadpool(cos_video_service.signed_url, item["cos_video_key"])
    except TencentCosObjectMissing as exc:
        raise HTTPException(409, "课程视频已被移除，请联系管理员") from exc
    except TencentCosUnsupportedVideo as exc:
        raise HTTPException(409, "课程视频格式暂不支持") from exc
    except TencentCosError as exc:
        raise HTTPException(503, "课程视频暂时无法加载，请稍后重试") from exc


@router.post("/learner/course-v23/{course_version_id}/audio-alignment/{file_id}")
async def learner_course_v23_audio_alignment(
    course_version_id: str,
    file_id: str,
    language: str = Query(pattern="^(zh|en)$"),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    if not store.get_published_course_v23_for_user(course_version_id, principal.user_id):
        raise HTTPException(404, "Published course not found")
    try:
        return await run_in_threadpool(_ensure_course_audio_alignment, course_version_id, file_id, language)
    except LookupError as exc:
        raise HTTPException(404, "课程标准音频不存在") from exc
    except (CourseAudioAlignmentError, ValueError) as exc:
        raise HTTPException(503, "标准音频暂时无法完成精准定位") from exc


@router.post("/course-v23-media/{file_id}/playback")
async def create_course_v23_media_playback(file_id: str, principal: Principal = Depends(get_principal)):
    """Exchange the normal bearer token for a short-lived, file-scoped media URL."""
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    if not store.get_course_v23_media(file_id) or not store.user_can_access_course_v23_media(file_id, principal.user_id):
        raise HTTPException(404, "课程媒体不存在")
    ticket = course_media_signer.issue(file_id, principal.user_id)
    return {
        "url": f"/api/v1/cabinlingo/course-v23-media-stream/{file_id}/{ticket}",
        "expires_in": course_media_signer.ttl_seconds,
    }


@router.api_route("/course-v23-media-stream/{file_id}/{ticket}", methods=["GET", "HEAD"])
async def stream_course_v23_media(file_id: str, ticket: str, request: Request):
    """Stream only the requested byte range so playback can start before download completes."""
    try:
        course_media_signer.verify(ticket, file_id)
    except CourseMediaTokenError as exc:
        raise HTTPException(401, "播放地址已失效，请重新加载") from exc
    item = store.get_course_v23_media(file_id)
    if not item:
        raise HTTPException(404, "课程媒体不存在")
    asset_ref = str(item["asset_ref"])
    filename = str(item.get("filename") or "course-media")
    media_type = str(item.get("mime_type") or "application/octet-stream")
    path: Path | None = None
    if isinstance(object_storage, LocalObjectStorage):
        try:
            path = object_storage.local_path(asset_ref)
        except ObjectStorageError as exc:
            raise HTTPException(404, "课程媒体文件不存在") from exc
        size = path.stat().st_size
    else:
        try:
            blob = await run_in_threadpool(object_storage.read, asset_ref)
        except ObjectStorageError as exc:
            raise HTTPException(404, "课程媒体文件不存在") from exc
        size = len(blob.data)
        filename = str(item.get("filename") or blob.filename)
        media_type = str(item.get("mime_type") or blob.content_type)

    start, end, partial = _course_media_range(request.headers.get("range"), size)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": _inline_content_disposition(filename),
        "Content-Length": str(end - start + 1),
        "ETag": f'"{file_id}-{size}"',
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    status_code = 206 if partial else 200
    if request.method == "HEAD":
        return Response(status_code=status_code, media_type=media_type, headers=headers)
    if path is not None:
        return StreamingResponse(
            _course_media_chunks(path, start, end),
            status_code=status_code,
            media_type=media_type,
            headers=headers,
        )
    return Response(blob.data[start:end + 1], status_code=status_code, media_type=media_type, headers=headers)


@router.get("/course-v23-media/{file_id}")
async def download_course_v23_media(file_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    item = store.get_course_v23_media(file_id)
    if not item:
        raise HTTPException(404, "课程媒体不存在")
    try:
        blob = object_storage.read(str(item["asset_ref"]))
    except ObjectStorageError as exc:
        raise HTTPException(404, "课程媒体文件不存在") from exc
    filename = str(item.get("filename") or blob.filename)
    return Response(blob.data, media_type=item.get("mime_type") or blob.content_type,
                    headers={
                        "Content-Disposition": _inline_content_disposition(filename),
                        "Cache-Control": "private, max-age=3600",
                        "Content-Length": str(len(blob.data)),
                    })


@router.get("/admin/courses/{course_id}/versions", response_model=list[CourseVersionOut])
async def list_course_versions(course_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.list_course_versions(course_id)


@router.post("/admin/courses/{course_id}/versions", response_model=CourseVersionOut)
async def create_course_version(course_id: str, data: CourseVersionCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.create_course_version(course_id, data.version_label.strip(), data.change_summary.strip(), principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/course-versions/published", response_model=list[CourseVersionOut])
async def list_published_course_versions(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    result = []
    for course in store.list_courses():
        result.extend(version for version in store.list_course_versions(course["id"]) if version["status"] == "published")
    return result


@router.get("/admin/course-versions/{course_version_id}/chapters", response_model=list[ChapterOut])
async def list_chapters(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.list_chapters(course_version_id)


@router.post("/admin/course-versions/{course_version_id}/chapters", response_model=ChapterOut)
async def create_chapter(course_version_id: str, data: ChapterCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.create_chapter(
            course_version_id, data.code.strip(), data.title.strip(), data.sequence_no,
            data.learning_objective.strip(),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/chapters/{chapter_id}/contents", response_model=list[ContentItemOut])
async def list_content_items(chapter_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.list_content_items(chapter_id)


@router.post("/admin/chapters/{chapter_id}/html-import", response_model=ContentItemOut)
async def import_html_content(chapter_id: str, data: HTMLImportCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    if not data.source_filename.lower().endswith((".html", ".htm")):
        raise HTTPException(422, "Only .html or .htm files are accepted")
    try:
        sanitized = sanitize_html(data.source_html)
        return store.create_html_content(
            chapter_id, data.title.strip(), data.sequence_no, data.source_filename,
            sanitized.html, sanitized.original_sha256, sanitized.sanitized_sha256,
            sanitized.report, principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/admin/course-versions/{course_version_id}/ppt-import", response_model=PPTImportOut)
async def import_ppt_course(course_version_id: str, file: UploadFile = File(...), principal: Principal = Depends(get_principal)):
    """Import a .pptx into the draft version as one chapter of HTML items."""
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".pptx"):
        raise HTTPException(415, "只支持 .pptx 格式；旧版 .ppt 请先另存为 .pptx")
    body = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_PPTX_BYTES:
            raise HTTPException(413, "PPTX 文件不能超过 50 MB")
    try:
        deck = parse_pptx(bytes(body), filename)
        prepared_slides = []
        for slide in deck.slides:
            sanitized = sanitize_html(slide.html)
            report = {
                **sanitized.report,
                "source_type": "pptx",
                "source_filename": filename[:255],
                "slide_no": slide.number,
                "slide_paragraph_count": len(slide.paragraphs),
            }
            prepared_slides.append({
                "title": f"第 {slide.number} 页 · {slide.title}"[:200],
                "html": sanitized.html,
                "original_sha256": sanitized.original_sha256,
                "sanitized_sha256": sanitized.sanitized_sha256,
                "validation_report": report,
            })
        chapter_code = f"PPT-{sha256(bytes(body)).hexdigest()[:12].upper()}"
        result = store.import_ppt_course(
            course_version_id,
            chapter_code,
            f"{deck.title} · PPT 课程"[:200],
            filename[:255],
            prepared_slides,
            principal.user_id,
        )
        result["warnings"] = list(deck.warnings)
        return result
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "draft course version" in message or "重复" in message else 422
        raise HTTPException(status_code, message) from exc


@router.post("/admin/course-versions/{course_version_id}/pdf-import", response_model=PDFImportOut)
async def import_pdf_course(course_version_id: str, file: UploadFile = File(...), principal: Principal = Depends(get_principal)):
    """Store the original PDF and expose one page item per learner step."""
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(415, "只支持 .pdf 格式")
    body = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_COURSE_DOCUMENT_BYTES:
            raise HTTPException(413, "PDF 文件不能超过 100 MB")
    raw = bytes(body)
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "文件内容不是有效 PDF")
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise ValueError("加密 PDF 暂不支持，请先解除密码保护")
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("PDF 中没有可导入的页面")
        if page_count > MAX_COURSE_DOCUMENT_PAGES:
            raise ValueError(f"PDF 最多支持 {MAX_COURSE_DOCUMENT_PAGES} 页")
    except ValueError:
        raise
    except Exception as exc:
        raise HTTPException(422, "PDF 解析失败，请确认文件未损坏") from exc
    pdf_hash = sha256(raw).hexdigest()
    object_key = f"course-documents/{course_version_id}/{uuid4().hex}.pdf"
    try:
        pdf_ref = object_storage.save(object_key, raw, "application/pdf")
    except ObjectStorageError as exc:
        raise HTTPException(503, "PDF 文件存储不可用") from exc
    try:
        result = store.import_pdf_course(
            course_version_id,
            f"PDF-{pdf_hash[:12].upper()}",
            f"{filename.rsplit('.', 1)[0]} · PDF 课程"[:200],
            filename[:255], pdf_ref, len(raw), page_count, pdf_hash, principal.user_id,
        )
        return result
    except ValueError as exc:
        object_storage.delete(pdf_ref)
        message = str(exc)
        status_code = 409 if "draft course version" in message or "重复" in message else 422
        raise HTTPException(status_code, message) from exc


@router.get("/admin/contents/{content_id}/assets", response_model=list[ContentAssetOut])
async def list_content_assets(content_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    if not store.get_content_item(content_id):
        raise HTTPException(404, "Content item not found")
    return [
        {**item, "url": f"/api/v1/cabinlingo/admin/content-assets/{item['id']}"}
        for item in store.list_content_assets(content_id)
    ]


@router.post("/admin/contents/{content_id}/assets", response_model=ContentAssetOut)
async def upload_content_asset(
    content_id: str,
    request: Request,
    source_filename: str = Query(..., min_length=1, max_length=255),
    asset_role: str = Query(default="attachment", min_length=1, max_length=40),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a", "audio/ogg": ".ogg", "audio/webm": ".webm",
        "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    }
    if mime_type not in extensions:
        raise HTTPException(415, "只支持 MP3、WAV、M4A、OGG、WebM、MP4 或 MOV 音视频")
    declared_size = int(request.headers.get("content-length", "0") or 0)
    if declared_size > settings.course_media_max_bytes:
        raise HTTPException(413, "课程媒体不能超过 100 MB")
    body = await request.body()
    if not body:
        raise HTTPException(422, "课程媒体文件为空")
    if len(body) > settings.course_media_max_bytes:
        raise HTTPException(413, "课程媒体不能超过 100 MB")
    object_key = f"course-media/{content_id}/{uuid4().hex}{extensions[mime_type]}"
    try:
        asset_ref = object_storage.save(object_key, body, mime_type)
    except ObjectStorageError as exc:
        raise HTTPException(503, "课程媒体存储不可用") from exc
    try:
        asset = store.create_content_asset(content_id, asset_ref, mime_type, len(body), source_filename, asset_role, principal.user_id)
        asset["url"] = f"/api/v1/cabinlingo/admin/content-assets/{asset['id']}"
        return asset
    except ValueError as exc:
        object_storage.delete(asset_ref)
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/content-assets/{asset_id}")
async def download_admin_content_asset(asset_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    asset = store.get_content_asset(asset_id)
    if not asset:
        raise HTTPException(404, "课程媒体不存在")
    try:
        blob = object_storage.read(str(asset["asset_ref"]))
    except ObjectStorageError as exc:
        raise HTTPException(404, "课程媒体文件不存在") from exc
    filename = str(asset.get("original_filename") or blob.filename).replace('"', "")
    return Response(blob.data, media_type=asset.get("mime_type") or blob.content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/admin/contents/{content_id}/standard", response_model=CourseStandardOut | None)
async def get_course_standard(content_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    return store.get_course_standard(content_id)


@router.put("/admin/contents/{content_id}/standard", response_model=CourseStandardOut)
async def save_course_standard(content_id: str, data: CourseStandardSave, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.save_course_standard(content_id, data.model_dump(), principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/admin/contents/{content_id}/standards/{standard_id}/audio", response_model=CourseStandardOut)
async def upload_course_standard_audio(
    content_id: str,
    standard_id: str,
    request: Request,
    source_filename: str = Query(..., min_length=1, max_length=255),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a", "audio/ogg": ".ogg", "audio/webm": ".webm",
    }
    if mime_type not in extensions:
        raise HTTPException(415, "Unsupported standard audio type")
    declared_size = int(request.headers.get("content-length", "0") or 0)
    if declared_size > settings.audio_max_bytes:
        raise HTTPException(413, "Standard audio exceeds the configured limit")
    body = await request.body()
    if not body:
        raise HTTPException(422, "Standard audio is empty")
    if len(body) > settings.audio_max_bytes:
        raise HTTPException(413, "Standard audio exceeds the configured limit")
    object_key = f"course-standards/{content_id}/{uuid4().hex}{extensions[mime_type]}"
    try:
        audio_ref = object_storage.save(object_key, body, mime_type)
    except ObjectStorageError as exc:
        raise HTTPException(503, "Standard audio storage is unavailable") from exc
    try:
        return store.attach_course_standard_audio(
            content_id, standard_id, audio_ref, mime_type, len(body), source_filename, principal.user_id,
        )
    except ValueError as exc:
        object_storage.delete(audio_ref)
        raise HTTPException(409, str(exc)) from exc


@router.get("/course-standard-audio/{file_id}")
async def download_course_standard_audio(file_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    item = store.get_course_standard_audio(file_id)
    if not item:
        raise HTTPException(404, "Standard audio not found")
    try:
        audio = object_storage.read(str(item["audio_ref"]))
    except ObjectStorageError:
        raise HTTPException(404, "Standard audio file not found")
    filename = str(item.get("source_filename") or audio.filename).replace('"', "")
    return Response(audio.data, media_type=item.get("mime_type") or audio.content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/admin/course-versions/{course_version_id}/publish", response_model=CourseVersionOut)
async def publish_course_version(course_version_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.publish_course_version(course_version_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/contents/{content_id}", response_model=ContentItemOut)
async def get_content_item(content_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    item = store.get_content_item(content_id)
    if not item:
        raise HTTPException(404, "Content item not found")
    return item


@router.get("/admin/contents/{content_id}/interactions", response_model=list[ContentInteractionOut])
async def list_content_interactions(content_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    if not store.get_content_item(content_id):
        raise HTTPException(404, "Content item not found")
    return store.list_content_interactions(content_id, include_archived=True)


@router.post("/admin/contents/{content_id}/interactions", response_model=ContentInteractionOut)
async def create_content_interaction(content_id: str, data: ContentInteractionCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        return store.create_content_interaction(content_id, data.model_dump(), principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/admin/interactions/{interaction_id}", response_model=ContentInteractionOut)
async def update_content_interaction(interaction_id: str, data: ContentInteractionUpdate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        item = store.update_content_interaction(interaction_id, data.model_dump(), principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Interaction not found")
    return item


@router.delete("/admin/interactions/{interaction_id}", response_model=ContentInteractionOut)
async def archive_content_interaction(interaction_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")
    try:
        item = store.archive_content_interaction(interaction_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Interaction not found")
    return item


@router.get("/learner/home", response_model=LearnerHomeOut)
async def learner_home(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return store.learner_home(principal.user_id)


@router.get("/admin/learners/{learner_id}/tasks", response_model=list[LearnerTaskOut])
async def admin_learner_tasks(learner_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    return store.list_learner_tasks(learner_id)


@router.get("/admin/learners/{learner_id}/broadcast-progress", response_model=list[AdminLearnerBroadcastItemOut])
async def admin_learner_broadcast_progress(learner_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    return store.list_admin_learner_broadcast_progress(learner_id)


@router.get("/admin/learners/{learner_id}/attempts/{attempt_id}", response_model=InstructorReviewDetail)
async def admin_learner_attempt_detail(learner_id: str, attempt_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    detail = store.get_instructor_review_detail("practice", attempt_id, None)
    if not detail or detail.get("learner_id") != learner_id:
        raise HTTPException(404, "Learner attempt not found")
    for recording in detail.get("recordings", []):
        recording["audio_url"] = f"/api/v1/cabinlingo/admin/learners/{learner_id}/recordings/{recording['id']}"
    detail["recording_url"] = (
        f"/api/v1/cabinlingo/admin/learners/{learner_id}/recordings/{detail['recording_id']}"
        if detail.get("recording_id") else None
    )
    return detail


@router.get("/admin/learners/{learner_id}/recordings/{recording_id}")
async def download_admin_learner_audio(learner_id: str, recording_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    recording = store.get_admin_learner_recording(recording_id, learner_id)
    if not recording:
        raise HTTPException(404, "Learner recording not found")
    try:
        audio = object_storage.read(str(recording["audio_ref"]))
    except ObjectStorageError:
        raise HTTPException(404, "Recording file not found")
    return Response(audio.data, media_type=recording.get("mime_type") or audio.content_type,
                    headers={"Content-Disposition": f'inline; filename="{audio.filename}"'})


@router.get("/admin/tasks/{task_type}/{task_id}/learners", response_model=TaskRosterOut)
async def admin_task_roster(task_type: str, task_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:task.manage")
    if task_type not in {"practice", "exam"}:
        raise HTTPException(422, "Task type must be practice or exam")
    roster = store.list_task_roster(task_type, task_id)
    if not roster:
        raise HTTPException(404, "Task not found")
    return roster


@router.get("/learner/tasks", response_model=list[LearnerTaskOut])
async def learner_tasks(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return store.list_learner_tasks(principal.user_id)


@router.get("/learner/practice/workspace/{assignment_id}", response_model=PracticeWorkspaceOut)
async def learner_practice_workspace(assignment_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    _assert_assignment_unlocked("practice", assignment_id, principal.user_id)
    workspace = store.learner_practice_workspace(assignment_id, principal.user_id)
    if not workspace:
        raise HTTPException(404, "Course-based practice assignment not found")
    return workspace


@router.get("/learner/course-documents/{content_id}")
async def download_learner_course_document(content_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    document = store.get_learner_document(content_id, principal.user_id)
    if not document:
        raise HTTPException(404, "课程 PDF 不存在或不属于当前任务")
    try:
        blob = object_storage.read(str(document["document_ref"]))
    except ObjectStorageError as exc:
        raise HTTPException(404, "课程 PDF 文件不存在") from exc
    filename = str(document.get("source_filename") or blob.filename).replace('"', "")
    return Response(blob.data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"', "Accept-Ranges": "bytes"})


@router.get("/learner/content-assets/{asset_id}")
async def download_learner_content_asset(asset_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    asset = store.get_learner_content_asset(asset_id, principal.user_id)
    if not asset:
        raise HTTPException(404, "课程媒体不存在或不属于当前任务")
    try:
        blob = object_storage.read(str(asset["asset_ref"]))
    except ObjectStorageError as exc:
        raise HTTPException(404, "课程媒体文件不存在") from exc
    filename = str(asset.get("original_filename") or blob.filename).replace('"', "")
    return Response(blob.data, media_type=asset.get("mime_type") or blob.content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/learner/interactions/{interaction_id}/answers", response_model=InteractionAnswerOut)
async def submit_interaction_answer(interaction_id: str, data: InteractionAnswerCreate, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    if data.assignment_id == "" or data.content_item_id == "":
        raise HTTPException(422, "assignment_id and content_item_id are required")
    _assert_assignment_unlocked("practice", data.assignment_id, principal.user_id)
    try:
        return store.submit_interaction_answer(data.assignment_id, principal.user_id, data.content_item_id, interaction_id, data.answer)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/learner/audio", response_model=AudioUploadOut)
async def upload_learner_audio(
    request: Request,
    assignment_id: str = Query(...),
    purpose: str = Query(..., pattern="^(practice|exam)$"),
    content_item_id: str | None = Query(default=None),
    duration_ms: int | None = Query(default=None, ge=0),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    _assert_assignment_unlocked(purpose, assignment_id, principal.user_id)
    if purpose == "practice":
        assignment = store.get_practice_assignment(assignment_id, principal.user_id)
        task = store.get_practice_task(assignment.task_id) if assignment else None
        if not assignment or not task:
            raise HTTPException(404, "Practice assignment not found")
        if task.status != "published":
            raise HTTPException(409, "Practice task is not open")
    if purpose == "exam":
        assignment = store.get_exam_assignment(assignment_id, principal.user_id)
        task = store.get_exam_task(assignment.task_id) if assignment else None
        if not assignment or not task:
            raise HTTPException(404, "Exam assignment not found")
        if task.status not in {"open", "published"}:
            raise HTTPException(409, "Exam task is not open")
    if purpose == "practice" and content_item_id:
        workspace = store.learner_practice_workspace(assignment_id, principal.user_id)
        if not workspace or content_item_id not in {item["id"] for item in workspace["contents"]}:
            raise HTTPException(409, "Content does not belong to this assignment")
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "video/webm": ".webm"}
    if mime_type not in extensions:
        raise HTTPException(415, "Unsupported audio type")
    declared_size = int(request.headers.get("content-length", "0") or 0)
    if declared_size > settings.audio_max_bytes:
        raise HTTPException(413, "Audio file exceeds the configured limit")
    body = await request.body()
    if not body:
        raise HTTPException(422, "Audio body is empty")
    if len(body) > settings.audio_max_bytes:
        raise HTTPException(413, "Audio file exceeds the configured limit")
    if settings.audio_transcode_enabled:
        try:
            normalized = await run_in_threadpool(
                normalize_speech_audio,
                body,
                mime_type,
                ffmpeg_binary=settings.audio_transcode_binary,
                timeout_seconds=settings.audio_transcode_timeout_seconds,
                max_seconds=settings.audio_transcode_max_seconds,
                max_input_bytes=settings.audio_max_bytes,
                max_output_bytes=settings.audio_transcode_max_output_bytes,
            )
        except AudioTranscodeError as exc:
            if exc.code == "audio_transcoder_unavailable":
                raise HTTPException(503, "Audio transcoder is unavailable") from exc
            if exc.code in {"audio_too_large", "audio_transcoded_too_large"}:
                raise HTTPException(413, "Audio file exceeds the configured limit") from exc
            raise HTTPException(422, "Audio could not be converted to the required speech format") from exc
        body = normalized.data
        mime_type = normalized.content_type
    object_key = f"audio/{principal.user_id}/{uuid4().hex}{extensions[mime_type]}"
    try:
        audio_ref = object_storage.save(object_key, body, mime_type)
    except ObjectStorageError as exc:
        raise HTTPException(503, "Audio storage is unavailable") from exc
    try:
        recording = store.create_recording(assignment_id, purpose, audio_ref, duration_ms, content_item_id,
                                            mime_type, len(body), sha256(body).hexdigest())
    except ValueError as exc:
        object_storage.delete(audio_ref)
        raise HTTPException(409, str(exc)) from exc
    protected_url = f"/api/v1/cabinlingo/learner/audio/{recording['id']}"
    return {"recording_id": recording["id"], "audio_ref": audio_ref, "audio_url": protected_url, "mime_type": mime_type, "byte_size": len(body)}


@router.get("/learner/audio/{recording_id}")
async def download_learner_audio(recording_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    recording = store.get_learner_recording(recording_id, principal.user_id)
    if not recording:
        raise HTTPException(404, "Recording not found")
    try:
        audio = object_storage.read(str(recording["audio_ref"]))
    except ObjectStorageError:
        raise HTTPException(404, "Recording file not found")
    return Response(audio.data, media_type=recording.get("mime_type") or audio.content_type,
                    headers={"Content-Disposition": f'inline; filename="{audio.filename}"'})


@router.post("/learner/practice/attempts", response_model=LearnerAttemptOut)
async def submit_learner_practice(data: LearnerPracticeSubmit, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    _assert_assignment_unlocked("practice", data.assignment_id, principal.user_id)
    return await run_in_threadpool(learner_practice_service.submit, data, principal.user_id)


@router.get("/learner/practice/attempts", response_model=list[LearnerAttemptOut])
async def learner_attempts(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return store.list_learner_attempts(principal.user_id)


@router.get("/learner/practice/attempts/{attempt_id}", response_model=LearnerAttemptOut)
async def learner_attempt(attempt_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    item = store.get_learner_attempt(attempt_id, principal.user_id)
    if not item:
        raise HTTPException(404, "Practice attempt not found")
    return item


@router.post("/learner/practice/attempts/{attempt_id}/reanalyze", response_model=LearnerAttemptOut)
async def reanalyze_learner_attempt(attempt_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return await run_in_threadpool(learner_practice_service.reanalyze, attempt_id, principal.user_id)


@router.get("/learner/feedback", response_model=list[TeacherFeedbackOut])
async def learner_feedback(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return store.list_learner_feedback(principal.user_id)


@router.get("/learner/growth", response_model=GrowthProfileOut)
async def learner_growth(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    return store.learner_growth_profile(principal.user_id)


def _assert_review_permission(principal: Principal, review_type: str) -> None:
    if review_type not in {"practice", "exam"}:
        raise HTTPException(422, "Review type must be practice or exam")
    assert_permission(principal, "cabinlingo", f"cabinlingo:review.{review_type}")


@router.get("/instructor/reviews/queue", response_model=list[InstructorQueueItem])
async def instructor_review_queue(
    review_type: str | None = Query(default=None, pattern="^(practice|exam)$"),
    review_status: str | None = Query(default=None, pattern="^(pending|draft|published)$"),
    class_id: str | None = Query(default=None),
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    if review_type:
        _assert_review_permission(principal, review_type)
    return store.list_instructor_queue(review_type, review_status, class_id, instructor_id=principal.user_id)


@router.get("/instructor/learners", response_model=list[InstructorLearnerOut])
async def instructor_learners(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    return store.list_instructor_learners(principal.user_id)


@router.get("/instructor/dashboard", response_model=InstructorDashboard)
async def instructor_dashboard(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    return store.instructor_dashboard(principal.user_id)


@router.get("/instructor/learners/{learner_id}/submissions", response_model=list[InstructorQueueItem])
async def instructor_learner_submissions(learner_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    return store.list_instructor_learner_submissions(principal.user_id, learner_id)


@router.get("/instructor/reviews/{review_type}/{target_id}", response_model=InstructorReviewDetail)
async def instructor_review_detail(review_type: str, target_id: str, principal: Principal = Depends(get_principal)):
    _assert_review_permission(principal, review_type)
    detail = store.get_instructor_review_detail(review_type, target_id, principal.user_id)
    if not detail:
        raise HTTPException(404, "Review target not found")
    return detail


@router.get("/instructor/audio/{recording_id}")
async def download_instructor_audio(recording_id: str, principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:review")
    recording = store.get_instructor_recording(recording_id, principal.user_id)
    if not recording:
        raise HTTPException(404, "Recording not found")
    try:
        audio = object_storage.read(str(recording["audio_ref"]))
    except ObjectStorageError:
        raise HTTPException(404, "Recording file not found")
    return Response(audio.data, media_type=recording.get("mime_type") or audio.content_type,
                    headers={"Content-Disposition": f'inline; filename="{audio.filename}"'})


@router.post("/instructor/reviews/{review_type}/{target_id}/feedback-audio")
async def upload_instructor_feedback_audio(
    review_type: str,
    target_id: str,
    request: Request,
    duration_ms: int = Query(default=0, ge=0, le=30 * 60 * 1000),
    principal: Principal = Depends(get_principal),
):
    _assert_review_permission(principal, review_type)
    if not store.get_instructor_review_detail(review_type, target_id, principal.user_id):
        raise HTTPException(404, "Review target not found")
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {
        "audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
    }
    if mime_type not in extensions:
        raise HTTPException(415, "Unsupported feedback audio type")
    declared_size = int(request.headers.get("content-length", "0") or 0)
    if declared_size > settings.audio_max_bytes:
        raise HTTPException(413, "Feedback audio exceeds the configured limit")
    body = await request.body()
    if not body:
        raise HTTPException(422, "Feedback audio is empty")
    if len(body) > settings.audio_max_bytes:
        raise HTTPException(413, "Feedback audio exceeds the configured limit")
    object_key = f"instructor-feedback/{principal.user_id}/{uuid4().hex}{extensions[mime_type]}"
    try:
        audio_ref = object_storage.save(object_key, body, mime_type)
    except ObjectStorageError as exc:
        raise HTTPException(503, "Feedback audio storage is unavailable") from exc
    return {
        "audio_ref": audio_ref,
        "audio_url": f"/api/v1/cabinlingo/instructor/reviews/{review_type}/{target_id}/feedback-audio",
        "mime_type": mime_type,
        "byte_size": len(body),
        "duration_ms": duration_ms,
    }


@router.get("/instructor/reviews/{review_type}/{target_id}/feedback-audio")
async def download_instructor_feedback_audio(
    review_type: str,
    target_id: str,
    principal: Principal = Depends(get_principal),
):
    _assert_review_permission(principal, review_type)
    detail = store.get_instructor_review_detail(review_type, target_id, principal.user_id)
    if not detail:
        raise HTTPException(404, "Review target not found")
    review = detail.get("review") or {}
    evidence = review.get("evidence") or {}
    audio = evidence.get("feedback_audio") or {}
    audio_ref = audio.get("audio_ref")
    if not isinstance(audio_ref, str) or not audio_ref:
        raise HTTPException(404, "Feedback audio not found")
    try:
        blob = object_storage.read(audio_ref)
    except ObjectStorageError:
        raise HTTPException(404, "Feedback audio file not found")
    return Response(blob.data, media_type=audio.get("mime_type") or blob.content_type,
                    headers={"Content-Disposition": f'inline; filename="{blob.filename}"'})


@router.put("/instructor/reviews/{review_type}/{target_id}", response_model=InstructorReviewOut)
async def save_instructor_review(review_type: str, target_id: str, data: InstructorReviewSave, principal: Principal = Depends(get_principal)):
    _assert_review_permission(principal, review_type)
    try:
        return store.save_instructor_review(review_type, target_id, principal.user_id, data.model_dump(), False)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/instructor/reviews/{review_type}/{target_id}/publish", response_model=InstructorReviewOut)
async def publish_instructor_review(review_type: str, target_id: str, data: InstructorReviewSave, principal: Principal = Depends(get_principal)):
    _assert_review_permission(principal, review_type)
    try:
        return store.save_instructor_review(review_type, target_id, principal.user_id, data.model_dump(), True)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/instructor/analytics/classes", response_model=list[ClassReviewAnalytics])
async def instructor_class_analytics(principal: Principal = Depends(get_principal)):
    assert_permission(principal, "cabinlingo", "cabinlingo:analytics.class")
    return store.class_review_analytics(principal.user_id)
