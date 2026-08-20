# ============================================================
# CAET 上传路由（管理员）
# POST /upload/audio — 上传音频到 UPLOAD_DIR，返回可访问 URL
# （以上均相对于 /api 前缀）
# ============================================================
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..config import settings
from ..deps import get_current_user, require_admin
from ..models import Profile
from ..schemas import UploadOut

router = APIRouter()
ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".aac", ".flac"}


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


@router.post("/upload/audio", response_model=UploadOut)
async def upload_audio(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    original = file.filename or "audio"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的音频格式")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid4().hex}{ext}"
    dest = os.path.join(settings.UPLOAD_DIR, filename)

    content = await file.read()
    # 在事件循环中用线程写文件，避免阻塞
    import asyncio

    await asyncio.to_thread(_write_file, dest, content)

    return UploadOut(url=f"/uploads/{filename}", filename=filename)


@router.post("/upload/recording", response_model=UploadOut)
async def upload_recording(
    file: UploadFile = File(...),
    user: Profile = Depends(get_current_user),
):
    """学员/教员上传录音（测评用），任何已登录用户可用，文件隔离在 uploads/ 下。"""
    original = file.filename or "recording"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的音频格式")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # 前缀区分用户，避免文件名冲突
    filename = f"rec_{user.id.hex[:8]}_{uuid4().hex}{ext}"
    dest = os.path.join(settings.UPLOAD_DIR, filename)

    content = await file.read()
    import asyncio

    await asyncio.to_thread(_write_file, dest, content)

    return UploadOut(url=f"/uploads/{filename}", filename=filename)


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
