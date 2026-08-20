# ============================================================
# CAET 用户 / 权限管理路由（管理员）
# /admin/users              列表（含班级名）
# /admin/users              创建（指定角色 / 班级）
# /admin/users/{id}         更新（角色 / 班级 / 启用禁用）
# （以上均相对于 /api 前缀）
# ============================================================
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, row_to_dict
from ..deps import require_admin
from ..models import LearnerGroup, Profile, TaskAssignment
from ..schemas import UserAdminOut, UserCreateIn, UserUpdateIn
from ..security import get_password_hash

router = APIRouter()


async def _serialize(u: Profile, db: AsyncSession) -> dict:
    d = row_to_dict(u)
    if u.group_id:
        g = await db.get(LearnerGroup, u.group_id)
        d["group_name"] = g.name if g else None
    else:
        d["group_name"] = None
    return d


@router.get("/admin/users", response_model=list[UserAdminOut])
async def list_users(
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(Profile).order_by(Profile.role, Profile.display_name))
    ).scalars().all()
    return [await _serialize(u, db) for u in rows]


@router.post("/admin/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateIn,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.role not in ("admin", "instructor", "learner"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法角色")
    dup = (
        await db.execute(select(Profile).where(Profile.email == payload.email))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已存在")
    if payload.group_id:
        g = await db.get(LearnerGroup, payload.group_id)
        if g is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="班级不存在")
    u = Profile(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        display_name=payload.display_name,
        employee_no=payload.employee_no,
        role=payload.role,
        group_id=payload.group_id,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return await _serialize(u, db)


@router.put("/admin/users/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: UUID,
    payload: UserUpdateIn,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = await db.get(Profile, user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if payload.display_name is not None:
        u.display_name = payload.display_name
    if payload.employee_no is not None:
        u.employee_no = payload.employee_no
    if payload.role is not None:
        if payload.role not in ("admin", "instructor", "learner"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法角色")
        u.role = payload.role
    if payload.group_id is not None:
        if payload.group_id:
            g = await db.get(LearnerGroup, payload.group_id)
            if g is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="班级不存在")
        u.group_id = payload.group_id
    if payload.is_active is not None:
        u.is_active = payload.is_active
    await db.commit()
    return await _serialize(u, db)


@router.put("/admin/assignments/{assignment_id}/instructor", status_code=status.HTTP_204_NO_CONTENT)
async def set_assignment_instructor(
    assignment_id: UUID,
    instructor_id: UUID,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    a = await db.get(TaskAssignment, assignment_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务分配不存在")
    inst = await db.get(Profile, instructor_id)
    if inst is None or inst.role not in ("instructor", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指派的教员不存在或角色错误")
    a.instructor_id = instructor_id
    await db.commit()
