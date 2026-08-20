# ============================================================
# CAET 依赖 — 当前用户解析与管理员校验
# ============================================================
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import Profile
from .security import decode_token

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未登录或登录已失效",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    if not authorization or not authorization.startswith("Bearer "):
        raise _CREDENTIALS_EXC
    token = authorization[len("Bearer ") :]
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise _CREDENTIALS_EXC
        uid = UUID(sub)
    except (JWTError, ValueError):
        raise _CREDENTIALS_EXC

    user = await db.get(Profile, uid)
    if user is None:
        raise _CREDENTIALS_EXC
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


def require_admin(user: Profile = Depends(get_current_user)) -> Profile:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_instructor(user: Profile = Depends(get_current_user)) -> Profile:
    """教员或管理员可访问（测评、评分、反馈）。"""
    if user.role not in ("instructor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要教员或管理员权限")
    return user


def require_role(*roles: str):
    """工厂：返回校验指定角色的依赖。"""

    def _checker(user: Profile = Depends(get_current_user)) -> Profile:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return _checker
