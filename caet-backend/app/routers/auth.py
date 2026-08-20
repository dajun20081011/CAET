# ============================================================
# CAET 认证路由
# POST /auth/register, POST /auth/login, GET /auth/me, POST /auth/init-admin
# （以上均相对于 /api 前缀）
# ============================================================
from fastapi import APIRouter, Depends, HTTPException, Header, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Profile
from ..redis_client import session_delete, session_set
from ..schemas import InitAdminIn, LoginIn, RegisterIn, UserOut
from ..security import create_access_token, decode_token, get_password_hash, verify_password

router = APIRouter()


async def _create_admin(db: AsyncSession, email: str, password: str, name: str) -> Profile:
    existing = (
        await db.execute(select(Profile).where(Profile.email == email))
    ).scalar_one_or_none()
    if existing:
        return existing
    user = Profile(
        email=email,
        password_hash=get_password_hash(password),
        display_name=name,
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(select(Profile).where(Profile.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已注册")
    user = Profile(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        display_name=payload.display_name,
        employee_no=payload.employee_no,
        role="learner",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/auth/login")
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(Profile).where(Profile.email == payload.email))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    token = create_access_token(str(user.id), user.role)
    # 写入 Redis 会话（支持登出吊销；Redis 不可用时静默降级）
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        if jti:
            await session_set(jti, {"user_id": str(user.id), "role": user.role, "email": user.email})
    except JWTError:
        pass
    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.get("/auth/me", response_model=UserOut)
async def me(user: Profile = Depends(get_current_user)):
    return user


@router.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :]
        try:
            payload = decode_token(token)
            jti = payload.get("jti")
            if jti:
                await session_delete(jti)
        except JWTError:
            pass
    return {"ok": True}


@router.post("/auth/init-admin", response_model=UserOut)
async def init_admin(payload: InitAdminIn, db: AsyncSession = Depends(get_db)):
    user = await _create_admin(db, payload.email, payload.password, payload.display_name)
    return user
