# ============================================================
# CAET 学习记录路由
# GET /record — 聚合当前学员：7 天学习日历、统计指标、
#               最近学习内容、事件类型分布
# （以上均相对于 /api 前缀）
# ============================================================
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user
from ..models import CourseContent, LearnerProgress, LearningEvent, Profile, TaskAssignment
from ..schemas import RecordOut

router = APIRouter()


@router.get("/record", response_model=RecordOut)
async def get_record(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid: UUID = user.id

    # 7 天学习日历（按天统计事件数）
    since = datetime.now(timezone.utc) - timedelta(days=6)
    cal_rows = (
        await db.execute(
            select(
                func.date(LearningEvent.created_at).label("day"),
                func.count().label("count"),
            )
            .where(LearningEvent.learner_id == uid, LearningEvent.created_at >= since)
            .group_by(func.date(LearningEvent.created_at))
            .order_by(func.date(LearningEvent.created_at))
        )
    ).all()
    cal_map = {str(r.day): r.count for r in cal_rows}
    calendar_7d = []
    for i in range(7):
        d = (datetime.now(timezone.utc) - timedelta(days=6 - i)).date()
        calendar_7d.append({"date": str(d), "count": cal_map.get(str(d), 0)})

    # 统计指标
    total_seconds = (
        await db.scalar(
            select(func.coalesce(func.sum(LearnerProgress.effective_seconds), 0)).where(
                LearnerProgress.learner_id == uid
            )
        )
        or 0
    )
    task_total = (
        await db.scalar(
            select(func.count()).select_from(TaskAssignment).where(TaskAssignment.learner_id == uid)
        )
        or 0
    )
    task_completed = (
        await db.scalar(
            select(func.count())
            .select_from(TaskAssignment)
            .where(TaskAssignment.learner_id == uid, TaskAssignment.status == "completed")
        )
        or 0
    )
    total_events = (
        await db.scalar(
            select(func.count()).select_from(LearningEvent).where(LearningEvent.learner_id == uid)
        )
        or 0
    )
    completed_contents = (
        await db.scalar(
            select(func.count())
            .select_from(LearnerProgress)
            .where(LearnerProgress.learner_id == uid, LearnerProgress.completed == True)  # noqa: E712
        )
        or 0
    )

    stats = {
        "total_effective_seconds": int(total_seconds),
        "total_effective_minutes": round(int(total_seconds) / 60, 1),
        "task_total": int(task_total),
        "task_completed": int(task_completed),
        "task_completion_rate": round(int(task_completed) / int(task_total) * 100, 2) if task_total else 0.0,
        "total_events": int(total_events),
        "completed_contents": int(completed_contents),
    }

    # 最近学习内容
    recent_rows = (
        await db.execute(
            select(LearnerProgress)
            .where(LearnerProgress.learner_id == uid)
            .order_by(LearnerProgress.updated_at.desc())
            .limit(10)
        )
    ).scalars().all()
    recent_content = []
    for p in recent_rows:
        content = await db.get(CourseContent, p.content_id)
        recent_content.append(
            {
                "content_id": str(p.content_id),
                "completed": bool(p.completed),
                "effective_seconds": p.effective_seconds or 0,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "chapter_no": content.chapter_no if content else None,
                "day_no": content.day_no if content else None,
                "content_type": content.content_type if content else None,
                "chapter_title": content.chapter_title if content else None,
                "payload": content.payload if content else {},
            }
        )

    # 事件类型分布
    dist_rows = (
        await db.execute(
            select(LearningEvent.event_type, func.count().label("count"))
            .where(LearningEvent.learner_id == uid)
            .group_by(LearningEvent.event_type)
            .order_by(func.count().desc())
        )
    ).all()
    event_distribution = [{"event_type": r.event_type, "count": r.count} for r in dist_rows]

    return RecordOut(
        calendar_7d=calendar_7d,
        stats=stats,
        recent_content=recent_content,
        event_distribution=event_distribution,
    )
