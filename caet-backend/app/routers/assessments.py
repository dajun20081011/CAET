# ============================================================
# CAET 测评路由
# 三类独立测评：
#   broadcast_recording — 广播词录音（需中文+英文录音齐全）
#   english_qa          — 英文问答（仅英文）
#   zh_to_en            — 中译英
# 学习流程共享；测评类型独立。
# 端点（均相对于 /api 前缀）：
#   POST   /assessments/submit      学员提交本人测评
#   GET    /assessments/my          学员查看本人提交
#   GET    /assessments/task/{id}   教员/管理员查看某任务全部提交
#   GET    /assessments/pending     教员/管理员查看待评分队列
#   GET    /assessments/{id}        查看单条
#   POST   /assessments/{id}/grade  教员/管理员评分与反馈
# ============================================================
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user, require_instructor
from ..models import Assessment, Course, Profile, Task, TaskAssignment
from ..schemas import AssessmentGradeIn, AssessmentOut, AssessmentSubmitIn

router = APIRouter()

ALLOWED_TYPES = {"broadcast_recording", "english_qa", "zh_to_en"}


def _validate_answers(assessment_type: str, answers: dict) -> None:
    if assessment_type == "broadcast_recording":
        cn = (answers or {}).get("cn_audio_url")
        en = (answers or {}).get("en_audio_url")
        if not cn or not en:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="广播词测评需同时提交中文录音与英文录音",
            )
    # english_qa / zh_to_en 在前端保证结构，后端宽松接受


async def _serialize(a: Assessment, db: AsyncSession) -> dict:
    d = row_to_dict(a)
    learner = await db.get(Profile, a.learner_id)
    d["learner_name"] = learner.display_name or learner.email if learner else None
    assignment = await db.get(TaskAssignment, a.assignment_id)
    task_title = course_title = None
    if assignment:
        task = await db.get(Task, assignment.task_id)
        if task:
            task_title = task.title
            course = await db.get(Course, task.course_id)
            if course:
                course_title = course.title
    d["task_title"] = task_title
    d["course_title"] = course_title
    return d


@router.post("/assessments/submit", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
async def submit_assessment(
    payload: AssessmentSubmitIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.assessment_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的测评类型")
    assignment = await db.get(TaskAssignment, payload.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务分配不存在")
    if assignment.learner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能提交本人的测评")

    _validate_answers(payload.assessment_type, payload.answers)

    a = Assessment(
        assignment_id=payload.assignment_id,
        learner_id=user.id,
        content_id=payload.content_id,
        course_id=assignment.task.course_id if assignment.task else None,
        assessment_type=payload.assessment_type,
        attempt_no=payload.attempt_no,
        status="submitted",
        answers=payload.answers,
    )
    db.add(a)
    # 标记任务进行中（若尚未完成）
    if assignment.status == "not_started":
        assignment.status = "in_progress"
    await db.commit()
    await db.refresh(a)
    return await _serialize(a, db)


@router.get("/assessments/my", response_model=list[AssessmentOut])
async def my_assessments(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Assessment)
            .where(Assessment.learner_id == user.id)
            .order_by(Assessment.created_at.desc())
        )
    ).scalars().all()
    return [await _serialize(r, db) for r in rows]


@router.get("/assessments/task/{task_id}", response_model=list[AssessmentOut])
async def task_assessments(
    task_id: UUID,
    _u=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    # 取该任务下所有 assignment 的测评
    assignment_ids = (
        await db.execute(select(TaskAssignment.id).where(TaskAssignment.task_id == task_id))
    ).scalars().all()
    if not assignment_ids:
        return []
    rows = (
        await db.execute(
            select(Assessment)
            .where(Assessment.assignment_id.in_(assignment_ids))
            .order_by(Assessment.created_at.desc())
        )
    ).scalars().all()
    return [await _serialize(r, db) for r in rows]


@router.get("/assessments/pending", response_model=list[AssessmentOut])
async def pending_queue(
    user: Profile = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Assessment).where(Assessment.status == "submitted")
    rows = (await db.execute(stmt.order_by(Assessment.created_at.asc()))).scalars().all()
    out = []
    for r in rows:
        assignment = await db.get(TaskAssignment, r.assignment_id)
        # 教员只看指派给自己的；管理员看全部
        if user.role == "instructor" and assignment and assignment.instructor_id != user.id:
            continue
        out.append(await _serialize(r, db))
    return out


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(
    assessment_id: int,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a = await db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测评记录不存在")
    if user.role == "learner" and a.learner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看")
    return await _serialize(a, db)


@router.post("/assessments/{assessment_id}/grade", response_model=AssessmentOut)
async def grade_assessment(
    assessment_id: int,
    payload: AssessmentGradeIn,
    user: Profile = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    a = await db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测评记录不存在")
    assignment = await db.get(TaskAssignment, a.assignment_id)
    if user.role == "instructor" and assignment and assignment.instructor_id not in (None, user.id):
        # 允许未指派（null）或指派给本人
        if assignment.instructor_id is not None and assignment.instructor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="非你负责的测评")
    a.score = payload.score
    a.feedback = payload.feedback
    a.status = payload.status
    a.instructor_id = user.id
    a.graded_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db.commit()
    return await _serialize(a, db)
