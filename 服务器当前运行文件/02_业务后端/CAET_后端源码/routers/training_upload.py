import asyncio
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from security import get_current_user


router = APIRouter(tags=["broadcast-training"])
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/uploads"))
ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".aac", ".flac"}
MAX_BYTES = 50 * 1024 * 1024


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


@router.post("/upload/recording", status_code=201)
async def upload_recording(file: UploadFile = File(...), user=Depends(get_current_user)):
    ext = Path(file.filename or "recording").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="不支持的音频格式")
    content = await file.read(MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="音频文件不能为空")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="音频文件不能超过 50MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"training_{str(user['id'])[:8]}_{uuid4().hex}{ext}"
    await asyncio.to_thread(_write, UPLOAD_DIR / filename, content)
    return {"url": f"/media/{filename}", "filename": filename}
