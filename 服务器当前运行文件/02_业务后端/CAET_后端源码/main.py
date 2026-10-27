import os

import psycopg
import redis
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.admin import router as admin_router
from routers.courses import router as courses_router
from routers.imports import router as imports_router
from routers.lessons import router as lessons_router
from routers.projects import router as projects_router
from routers.training import router as training_router
from routers.training_upload import router as training_upload_router


app = FastAPI(title="CAET API", version="0.3.1")
app.include_router(projects_router)
app.include_router(courses_router)
app.include_router(lessons_router)
app.include_router(imports_router)
app.include_router(admin_router)
app.include_router(training_router)
app.include_router(training_upload_router)
app.mount("/uploads", StaticFiles(directory=os.getenv("UPLOAD_DIR", "/uploads"), check_dir=False), name="uploads")


@app.get("/health")
def health():
    result = {"status": "ok", "service": "caet-api", "postgres": "unknown", "redis": "unknown"}
    try:
        conn = psycopg.connect(
            host="postgres",
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            connect_timeout=3,
        )
        conn.close()
        result["postgres"] = "ok"
    except Exception as exc:
        result["postgres"] = f"error: {type(exc).__name__}"
    try:
        client = redis.Redis(host="redis", port=6379, decode_responses=True)
        if client.ping():
            result["redis"] = "ok"
    except Exception as exc:
        result["redis"] = f"error: {type(exc).__name__}"
    return result
