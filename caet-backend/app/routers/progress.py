# ============================================================
# CAET 学习进度路由
# GET  /progress          — 某 assignment 的进度列表
# POST /progress          — upsert 并服务端重算完成率/状态
# （以上均相对于 /api 前缀）
# 进度计算在服务端完成，不信任客户端百分比。
# ============================================================
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user
from ..models import CourseContent, LearnerProgress, Profile, Task, TaskAssignment
from ..schemas import ProgressGetOut, ProgressItemOut, ProgressUpsertIn

router = APIRouter()


async def recompute_assignment(db: AsyncSession, assignment_id: UUID) -> TaskAssignment | None:
    """根据范围内内容完成数重算 assignment 的完成率与状态。"""
    assignment = await db.get(TaskAssignment, assignment_id)
    if assignment is None:
        return None
    task = await db.get(Task, assignment.task_id)
    if task is None:
        return assignment

    # 范围内的内容 id
    content_ids = (
        await db.execute(
            select(CourseContent.id).where(
                CourseContent.course_id == task.course_id,
                CourseContent.chapter_no >= task.chapter_from,
                CourseContent.chapter_no <= task.chapter_to,
                CourseContent.day_no >= task.day_from,
                CourseContent.day_no <= task.day_to,
            )
        )
    ).scalars().all()
    total = len(content_ids)

    completed = 0
    if total > 0:
        completed = (
            await db.scalar(
                select(func.count())
                .select_from(LearnerProgress)
                .where(
                    LearnerProgress.assignment_id == assignment_id,
                    LearnerProgress.completed == True,  # noqa: E712
                    LearnerProgress.content_id.in_(content_ids),
                )
            )
            or 0
        )

    percent = round(completed / total * 100, 2) if total > 0 else 0.0
    assignment.progress_percent = percent

    if percent == 0:
        status_val = "not_started"
    elif percent >= 100:
        status_val = "completed"
    else:
        status_val = "in_progress"

    # 超期且未完成 → overdue
    now = datetime.now(timezone.utc)
    due = task.due_at
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    if status_val != "completed" and due is not None and due < now:
        status_val = "overdue"
    assignment.status = status_val

    if percent > 0 and assignment.started_at is None:
        assignment.started_at = datetime.now(timezone.utc)
    if percent >= 100:
        if assignment.completed_at is None:
            assignment.completed_at = datetime.now(timezone.utc)
    else:
        assignment.completed_at = None

    return assignment


@router.get("/progress", response_model=ProgressGetOut)
async def get_progress(
    assignment_id: UUID = Query(...),
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TaskAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作业不存在")
    if assignment.learner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该作业进度")

    task = await db.get(Task, assignment.task_id)

    rows = (
        await db.execute(
            select(LearnerProgress)
            .where(LearnerProgress.assignment_id == assignment_id)
            .order_by(LearnerProgress.content_id)
        )
    ).scalars().all()

    items: list[ProgressItemOut] = []
    for p in rows:
        content = await db.get(CourseContent, p.content_id)
        items.append(
            ProgressItemOut(
                progress_id=p.id,
                assignment_id=p.assignment_id,
                content_id=p.content_id,
                completed=bool(p.completed),
                effective_seconds=p.effective_seconds or 0,
                last_position=p.last_position,
                attempt_count=p.attempt_count or 0,
                chapter_no=content.chapter_no if content else None,
                day_no=content.day_no if content else None,
                content_type=content.content_type if content else None,
                content_order=content.content_order if content else None,
                chapter_title=content.chapter_title if content else None,
                payload=content.payload if content else {},
            )
        )

    return ProgressGetOut(
        assignment=row_to_dict(assignment),
        task=row_to_dict(task) if task else None,
        items=items,
    )


@router.post("/progress", response_model=ProgressGetOut)
async def upsert_progress(
    payload: ProgressUpsertIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TaskAssignment, payload.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作业不存在")
    if assignment.learner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改该作业进度")

    existing = (
        await db.execute(
            select(LearnerProgress).where(
                LearnerProgress.assignment_id == payload.assignment_id,
                LearnerProgress.content_id == payload.content_id,
                LearnerProgress.learner_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.completed = payload.completed
        if payload.effective_seconds:
            existing.effective_seconds = (existing.effective_seconds or 0) + payload.effective_seconds
        if payload.last_position is not None:
            existing.last_position = payload.last_position
        existing.attempt_count = (existing.attempt_count or 0) + 1
        progress_row = existing
    else:
        progress_row = LearnerProgress(
            assignment_id=payload.assignment_id,
            content_id=payload.content_id,
            learner_id=user.id,
            completed=payload.completed,
            effective_seconds=payload.effective_seconds,
            last_position=payload.last_position,
            attempt_count=1,
        )
        db.add(progress_row)

    await db.flush()
    await recompute_assignment(db, payload.assignment_id)
    await db.commit()

    # 返回更新后的完整进度
    return await get_progress(assignment_id=payload.assignment_id, user=user, db=db)
