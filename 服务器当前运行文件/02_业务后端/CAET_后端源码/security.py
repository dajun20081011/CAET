import hmac
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException

from db.connection import get_connection


def require_admin(x_caet_admin_token: str | None = Header(default=None)):
    expected = os.getenv("CAET_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    if not x_caet_admin_token or not hmac.compare_digest(x_caet_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="密码至少需要 10 位")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if name != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: UUID) -> str:
    secret = os.getenv("CAET_JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="JWT authentication is not configured")
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=12)}, secret, algorithm="HS256")


def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    secret = os.getenv("CAET_JWT_SECRET", "")
    try:
        payload = jwt.decode(authorization[7:], secret, algorithms=["HS256"])
        user_id = UUID(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,email,display_name,employee_no,role,group_id,is_active,created_at,updated_at "
                "FROM training_users WHERE id=%s",
                (user_id,),
            )
            user = cur.fetchone()
    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号不可用")
    return user


def require_training_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_instructor(user=Depends(get_current_user)):
    if user["role"] not in {"instructor", "admin"}:
        raise HTTPException(status_code=403, detail="需要测评员权限")
    return user
