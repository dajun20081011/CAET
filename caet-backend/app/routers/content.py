# ============================================================
# CAET 课程内容路由
# GET /content            — 按 course_id / chapter_no / day_no 过滤
# GET /weekly-test        — content_type='weekly_test' 专门端点
# （以上均相对于 /api 前缀）
# ============================================================
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import get_current_user
from ..models import CourseContent, Profile

router = APIRouter()


@router.get("/content")
async def get_content(
    course_id: UUID | None = Query(default=None),
    chapter_no: int | None = Query(default=None),
    day_no: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    stmt = select(CourseContent).order_by(
        CourseContent.chapter_no, CourseContent.day_no, CourseContent.content_order
    )
    if course_id is not None:
        stmt = stmt.where(CourseContent.course_id == course_id)
    if chapter_no is not None:
        stmt = stmt.where(CourseContent.chapter_no == chapter_no)
    if day_no is not None:
        stmt = stmt.where(CourseContent.day_no == day_no)
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]


@router.get("/weekly-test")
async def get_weekly_test(
    course_id: UUID | None = Query(default=None),
    chapter_no: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    stmt = select(CourseContent).where(CourseContent.content_type == "weekly_test")
    if course_id is not None:
        stmt = stmt.where(CourseContent.course_id == course_id)
    if chapter_no is not None:
        stmt = stmt.where(CourseContent.chapter_no == chapter_no)
    stmt = stmt.order_by(CourseContent.chapter_no, CourseContent.day_no, CourseContent.content_order)
    rows = (await db.execute(stmt)).scalars().all()
    return [row_to_dict(r) for r in rows]
