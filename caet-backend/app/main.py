# ============================================================
# CAET 后端入口 — FastAPI 应用
# 所有子路由以相对路径定义，由 include_router(prefix='/api') 统一加 /api 前缀，
# 与前端 src/lib/api.ts 的 BASE='/api' 保持一致。
# ============================================================
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal
from .redis_client import ping as redis_ping
from .routers.admin import router as admin_router
from .routers.assessments import router as assessments_router
from .routers.auth import _create_admin, router as auth_router
from .routers.content import router as content_router
from .routers.courses import router as courses_router
from .routers.events import router as events_router
from .routers.groups import router as groups_router
from .routers.progress import router as progress_router
from .routers.record import router as record_router
from .routers.tasks import router as tasks_router
from .routers.upload import router as upload_router
from .routers.users import router as users_router

app = FastAPI(title="CAET 学练测平台后端", version="1.0.0")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- 路由（统一 /api 前缀） ----------------
app.include_router(auth_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(progress_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(record_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(groups_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(assessments_router, prefix="/api")

# ---------------- 静态文件（上传的音频） ----------------
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health():
    redis_ok = await redis_ping()
    return {"status": "ok", "redis": "up" if redis_ok else "down"}


@app.on_event("startup")
async def on_startup():
    # 确保上传目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # 若配置了 INIT_ADMIN_* 则用 bcrypt 创建/复用管理员
    if settings.INIT_ADMIN_EMAIL and settings.INIT_ADMIN_PASSWORD:
        async with SessionLocal() as db:
            await _create_admin(
                db,
                settings.INIT_ADMIN_EMAIL,
                settings.INIT_ADMIN_PASSWORD,
                settings.INIT_ADMIN_NAME,
            )
