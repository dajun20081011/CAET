# ============================================================
# CAET 学习事件路由
# POST /events — 写入 learning_events（learner_id 强制为当前登录用户）
# （以上均相对于 /api 前缀）
# ============================================================
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user
from ..models import LearningEvent, Profile
from ..schemas import EventIn

router = APIRouter()


@router.post("/events")
async def add_event(
    payload: EventIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = LearningEvent(
        learner_id=user.id,  # 强制为当前登录用户
        assignment_id=payload.assignment_id,
        course_id=payload.course_id,
        content_id=payload.content_id,
        event_type=payload.event_type,
        event_value=payload.event_value,
        client_timestamp=payload.client_timestamp,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return row_to_dict(event)
