# ============================================================
# CAET 课程路由
# GET /courses            — 返回全部课程（管理员创建任务时选择课程用）
# （以上均相对于 /api 前缀）
# ============================================================
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user
from ..models import Course, Profile

router = APIRouter()


@router.get("/courses")
async def list_courses(
    db: AsyncSession = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    stmt = select(Course).order_by(Course.created_at, Course.code)
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]
