# ============================================================
# CAET 班级管理路由（管理员）
# /admin/groups           列表（含学员数）
# /admin/groups           创建
# /admin/groups/{id}      详情（含学员列表）/ 改名 / 删除
# /admin/groups/{id}/members  增删学员
# （以上均相对于 /api 前缀）
# ============================================================
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import require_admin
from ..models import LearnerGroup, Profile, TaskAssignment
from ..schemas import GroupCreateIn, GroupOut, GroupUpdateIn, UserAdminOut

router = APIRouter()


async def _serialize_group(group: LearnerGroup, db: AsyncSession) -> dict:
    count = await db.scalar(
        select(func.count()).select_from(Profile).where(Profile.group_id == group.id)
    )
    return {**row_to_dict(group), "learner_count": count or 0}


@router.get("/admin/groups", response_model=list[GroupOut])
async def list_groups(
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(LearnerGroup).order_by(LearnerGroup.created_at))).scalars().all()
    return [await _serialize_group(g, db) for g in rows]


@router.post("/admin/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreateIn,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    dup = (
        await db.execute(select(LearnerGroup).where(LearnerGroup.name == payload.name))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="班级名称已存在")
    g = LearnerGroup(name=payload.name)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return await _serialize_group(g, db)


@router.get("/admin/groups/{group_id}")
async def group_detail(
    group_id: UUID,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    g = await db.get(LearnerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班级不存在")
    learners = (
        await db.execute(select(Profile).where(Profile.group_id == group_id).order_by(Profile.display_name))
    ).scalars().all()
    return {
        **(await _serialize_group(g, db)),
        "learners": [UserAdminOut.model_validate(u) for u in learners],
    }


@router.put("/admin/groups/{group_id}", response_model=GroupOut)
async def rename_group(
    group_id: UUID,
    payload: GroupUpdateIn,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    g = await db.get(LearnerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班级不存在")
    g.name = payload.name
    await db.commit()
    return await _serialize_group(g, db)


@router.delete("/admin/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    g = await db.get(LearnerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班级不存在")
    await db.execute(
        __import__("sqlalchemy").update(Profile).where(Profile.group_id == group_id).values(group_id=None)
    )
    await db.delete(g)
    await db.commit()


@router.post("/admin/groups/{group_id}/members/{learner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    group_id: UUID,
    learner_id: UUID,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    g = await db.get(LearnerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班级不存在")
    u = await db.get(Profile, learner_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学员不存在")
    u.group_id = group_id
    await db.commit()


@router.delete("/admin/groups/{group_id}/members/{learner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: UUID,
    learner_id: UUID,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = await db.get(Profile, learner_id)
    if u is None or u.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该学员不在本班级")
    u.group_id = None
    await db.commit()
