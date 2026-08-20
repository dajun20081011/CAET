# ============================================================
# CAET 管理端路由（require_admin）
# GET /admin/dashboard
# GET /admin/learners
# GET /admin/learners/{id}
# GET /admin/events
# GET /admin/export/{type}  → CSV
# （以上均相对于 /api 前缀）
# ============================================================
import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import require_admin
from ..models import (
    CourseContent,
    LearnerProgress,
    LearningEvent,
    Profile,
    Task,
    TaskAssignment,
)
from ..schemas import DashboardOut, LearnerAdminOut, LearnerDetailOut

router = APIRouter()


@router.get("/admin/dashboard", response_model=DashboardOut)
async def dashboard(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    learning_people = (
        await db.scalar(select(func.count(func.distinct(LearnerProgress.learner_id))))
        or 0
    )
    overall_rate = await db.scalar(select(func.avg(TaskAssignment.progress_percent))) or 0
    total_seconds = (
        await db.scalar(select(func.coalesce(func.sum(LearnerProgress.effective_seconds), 0))) or 0
    )
    avg_seconds = (total_seconds / learning_people) if learning_people else 0
    task_completed = (
        await db.scalar(
            select(func.count()).select_from(TaskAssignment).where(
                TaskAssignment.status == "completed"
            )
        )
        or 0
    )

    # 内容完成率 Top5
    rows = (
        await db.execute(
            select(
                LearnerProgress.content_id,
                func.count().label("total"),
                func.sum(func.cast(LearnerProgress.completed, type_=func.Integer)).label("done"),
            )
            .group_by(LearnerProgress.content_id)
        )
    ).all()
    content_stats = []
    for r in rows:
        total = r.total or 0
        done = int(r.done or 0)
        rate = round(done / total * 100, 2) if total else 0.0
        content = await db.get(CourseContent, r.content_id)
        content_stats.append(
            {
                "content_id": str(r.content_id),
                "title": content.chapter_title if content else "",
                "chapter_no": content.chapter_no if content else None,
                "day_no": content.day_no if content else None,
                "content_type": content.content_type if content else None,
                "completion_rate": rate,
                "completed": done,
                "total": total,
            }
        )
    content_stats.sort(key=lambda x: x["completion_rate"], reverse=True)
    content_completion_top5 = content_stats[:5]

    # 每日活跃趋势（近 14 天去重学习人数）
    since = datetime.now(timezone.utc) - timedelta(days=13)
    trend_rows = (
        await db.execute(
            select(
                func.date(LearningEvent.created_at).label("day"),
                func.count(func.distinct(LearningEvent.learner_id)).label("active"),
            )
            .where(LearningEvent.created_at >= since)
            .group_by(func.date(LearningEvent.created_at))
            .order_by(func.date(LearningEvent.created_at))
        )
    ).all()
    trend_map = {str(r.day): r.active for r in trend_rows}
    daily_active_trend = []
    for i in range(14):
        d = (datetime.now(timezone.utc) - timedelta(days=13 - i)).date()
        daily_active_trend.append({"date": str(d), "active": trend_map.get(str(d), 0)})

    return DashboardOut(
        learning_people_count=int(learning_people),
        overall_completion_rate=round(float(overall_rate or 0), 2),
        total_effective_seconds=int(total_seconds),
        avg_seconds_per_person=round(float(avg_seconds), 2),
        task_completion_count=int(task_completed),
        content_completion_top5=content_completion_top5,
        daily_active_trend=daily_active_trend,
    )


@router.get("/admin/learners", response_model=list[LearnerAdminOut])
async def list_learners(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    learners = (
        await db.execute(
            select(Profile).where(Profile.role == "learner").order_by(Profile.created_at.desc())
        )
    ).scalars().all()

    result: list[LearnerAdminOut] = []
    for u in learners:
        assignment_count = (
            await db.scalar(
                select(func.count()).select_from(TaskAssignment).where(
                    TaskAssignment.learner_id == u.id
                )
            )
            or 0
        )
        completed_count = (
            await db.scalar(
                select(func.count()).select_from(TaskAssignment).where(
                    TaskAssignment.learner_id == u.id, TaskAssignment.status == "completed"
                )
            )
            or 0
        )
        avg_progress = (
            await db.scalar(
                select(func.avg(TaskAssignment.progress_percent)).where(
                    TaskAssignment.learner_id == u.id
                )
            )
            or 0
        )
        total_seconds = (
            await db.scalar(
                select(func.coalesce(func.sum(LearnerProgress.effective_seconds), 0)).where(
                    LearnerProgress.learner_id == u.id
                )
            )
            or 0
        )
        result.append(
            LearnerAdminOut(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                employee_no=u.employee_no,
                role=u.role,
                is_active=u.is_active,
                created_at=u.created_at,
                assignment_count=int(assignment_count),
                completed_count=int(completed_count),
                avg_progress=round(float(avg_progress or 0), 2),
                total_seconds=int(total_seconds),
            )
        )
    return result


@router.get("/admin/learners/{learner_id}", response_model=LearnerDetailOut)
async def learner_detail(
    learner_id: UUID,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    learner = await db.get(Profile, learner_id)
    if learner is None or learner.role != "learner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学员不存在")

    assignments = (
        await db.execute(
            select(TaskAssignment).where(TaskAssignment.learner_id == learner_id)
        )
    ).scalars().all()
    assignment_list = []
    for a in assignments:
        task = await db.get(Task, a.task_id)
        assignment_list.append(
            {
                **row_to_dict(a),
                "task_title": task.title if task else "",
                "course_id": str(task.course_id) if task else None,
                "due_at": task.due_at.isoformat() if task and task.due_at else None,
            }
        )

    # 时长趋势（近 14 天按天汇总有效秒数）
    since = datetime.now(timezone.utc) - timedelta(days=13)
    trend_rows = (
        await db.execute(
            select(
                func.date(LearnerProgress.updated_at).label("day"),
                func.coalesce(func.sum(LearnerProgress.effective_seconds), 0).label("seconds"),
            )
            .where(LearnerProgress.learner_id == learner_id, LearnerProgress.updated_at >= since)
            .group_by(func.date(LearnerProgress.updated_at))
            .order_by(func.date(LearnerProgress.updated_at))
        )
    ).all()
    trend_map = {str(r.day): int(r.seconds) for r in trend_rows}
    duration_trend = []
    for i in range(14):
        d = (datetime.now(timezone.utc) - timedelta(days=13 - i)).date()
        duration_trend.append({"date": str(d), "seconds": trend_map.get(str(d), 0)})

    events = (
        await db.execute(
            select(LearningEvent)
            .where(LearningEvent.learner_id == learner_id)
            .order_by(LearningEvent.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    event_list = [row_to_dict(e) for e in events]

    return LearnerDetailOut(
        profile=row_to_dict(learner),
        assignments=assignment_list,
        duration_trend=duration_trend,
        events=event_list,
    )


@router.get("/admin/events")
async def list_events(
    learner_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LearningEvent).order_by(LearningEvent.created_at.desc())
    if learner_id is not None:
        stmt = stmt.where(LearningEvent.learner_id == learner_id)
    if event_type is not None:
        stmt = stmt.where(LearningEvent.event_type == event_type)
    total = await db.scalar(
        select(func.count()).select_from(LearningEvent).where(
            *(
                [LearningEvent.learner_id == learner_id] if learner_id else []
            )
            + (
                [LearningEvent.event_type == event_type] if event_type else []
            )
        )
    )
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {
        "total": int(total or 0),
        "items": [row_to_dict(e) for e in rows],
    }


@router.get("/admin/export/{export_type}")
async def export_csv(
    export_type: str,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if export_type not in ("events", "progress", "assignments"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的导出类型")

    if export_type == "events":
        rows = (
            await db.execute(
                select(LearningEvent).order_by(LearningEvent.created_at.desc())
            )
        ).scalars().all()
        columns = [
            "id", "learner_id", "assignment_id", "course_id", "content_id",
            "event_type", "event_value", "client_timestamp", "created_at",
        ]
        data = [row_to_dict(r) for r in rows]
        filename = "learning_events.csv"
    elif export_type == "progress":
        rows = (
            await db.execute(
                select(LearnerProgress).order_by(LearnerProgress.updated_at.desc())
            )
        ).scalars().all()
        columns = [
            "id", "assignment_id", "content_id", "learner_id", "completed",
            "effective_seconds", "last_position", "attempt_count", "updated_at",
        ]
        data = [row_to_dict(r) for r in rows]
        filename = "learner_progress.csv"
    else:
        rows = (
            await db.execute(
                select(TaskAssignment).order_by(TaskAssignment.created_at.desc())
            )
        ).scalars().all()
        columns = [
            "id", "task_id", "learner_id", "status", "started_at",
            "completed_at", "progress_percent", "updated_at",
        ]
        data = [row_to_dict(r) for r in rows]
        filename = "task_assignments.csv"

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for d in data:
        row = {}
        for c in columns:
            v = d.get(c)
            row[c] = "" if v is None else str(v)
        writer.writerow(row)
    csv_text = buf.getvalue()

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
