from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .auth_repository import AuthRepository
from .config import settings
from .security import create_access_token, verify_password


router = APIRouter(prefix="/api/v1/core/auth", tags=["Authentication"])


class LoginIn(BaseModel):
    account: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn):
    # Password verification uses 600k PBKDF2 iterations and repository access is
    # synchronous. A sync FastAPI handler runs in the worker thread pool instead
    # of blocking the single Uvicorn event loop for every concurrent login.
    repository = AuthRepository(settings.database_url)
    user = repository.find_user_for_login(data.account.strip())
    if not user or not user["is_active"] or not verify_password(data.password, user["password_hash"] or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid account or password")
    identity = repository.get_identity(user["id"])
    if not identity:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid account or password")
    repository.touch_login(user["id"])
    token = create_access_token(
        user_id=user["id"], token_version=user["token_version"], secret=settings.jwt_secret,
        issuer=settings.jwt_issuer, audience=settings.jwt_audience, ttl_seconds=settings.jwt_ttl_seconds,
    )
    memberships = [
        {"product": code, "roles": sorted(item["roles"]), "permissions": sorted(item["permissions"])}
        for code, item in identity["memberships"].items()
    ]
    return LoginOut(
        access_token=token, expires_in=settings.jwt_ttl_seconds,
        user={"id": identity["id"], "display_name": identity["display_name"], "memberships": memberships},
    )
