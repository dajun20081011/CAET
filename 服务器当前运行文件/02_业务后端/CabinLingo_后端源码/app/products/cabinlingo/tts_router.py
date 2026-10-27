import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ...core.config import settings
from ...core.rbac import Principal, assert_permission, get_principal
from ...integrations.xfyun_super_tts import (
    XfyunSuperTTSAdapter,
    XfyunSuperTTSConfig,
    XfyunSuperTTSError,
)


router = APIRouter(
    prefix="/api/v1/admin/tts",
    tags=["AI标准播音"],
)

_CACHE_KEY_RE = re.compile(r"^[a-f0-9]{64}$")


class TTSGenerateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    vcn: str = Field(default="x5_lingxiaoxuan_flow", min_length=1)
    speed: int = Field(default=50, ge=0, le=100)
    volume: int = Field(default=50, ge=0, le=100)
    pitch: int = Field(default=50, ge=0, le=100)
    rhy: int = Field(default=1, ge=0, le=1)
    force: bool = False
    oral_level: str | None = None


def _assert_admin(principal: Principal) -> None:
    assert_permission(
        principal,
        "cabinlingo",
        "cabinlingo:admin",
    )


def _build_adapter() -> XfyunSuperTTSAdapter:
    return XfyunSuperTTSAdapter(
        XfyunSuperTTSConfig(
            endpoint=settings.xfyun_super_tts_endpoint,
            app_id=settings.xfyun_super_tts_app_id,
            api_key=settings.xfyun_super_tts_api_key,
            api_secret=settings.xfyun_super_tts_api_secret,
            storage_dir=settings.xfyun_super_tts_storage_dir,
            timeout_seconds=settings.xfyun_super_tts_timeout_seconds,
            request_text_base64=settings.xfyun_super_tts_request_text_base64,
        )
    )


def _error_status(code: str) -> int:
    if code == "xfyun_super_tts_unconfigured":
        return 503

    if (
        code.endswith("_invalid")
        or code.endswith("_required")
        or code.endswith("_empty")
        or code.endswith("_too_large")
        or code.endswith("_contains_tab")
        or code.endswith("_contains_control_character")
        or code == "xfyun_super_tts_oral_requires_x4"
    ):
        return 422

    if code.endswith("_code_11201"):
        return 429

    return 502


@router.get("/status")
async def tts_status(
    principal: Principal = Depends(get_principal),
):
    _assert_admin(principal)

    adapter = _build_adapter()

    return {
        "provider": "xfyun_super_tts",
        "configured": adapter.config.configured,
        "storage_dir": adapter.config.storage_dir,
        "request_text_encoding": (
            "base64"
            if adapter.config.request_text_base64
            else "utf8"
        ),
    }


@router.post("/generate")
async def generate_tts(
    body: TTSGenerateRequest,
    principal: Principal = Depends(get_principal),
):
    _assert_admin(principal)

    adapter = _build_adapter()

    try:
        result = await run_in_threadpool(
            adapter.generate,
            text=body.text,
            vcn=body.vcn,
            speed=body.speed,
            volume=body.volume,
            pitch=body.pitch,
            rhy=body.rhy,
            force=body.force,
            oral_level=body.oral_level,
        )
    except XfyunSuperTTSError as exc:
        raise HTTPException(
            status_code=_error_status(exc.code),
            detail={
                "provider": "xfyun_super_tts",
                "code": exc.code,
                "sid": exc.sid,
            },
        ) from exc

    result["download_url"] = (
        f"/api/v1/admin/tts/"
        f"{result['cache_key']}/download"
    )

    return result


@router.get("/{cache_key}/download")
async def download_tts(
    cache_key: str,
    principal: Principal = Depends(get_principal),
):
    _assert_admin(principal)

    if not _CACHE_KEY_RE.fullmatch(cache_key):
        raise HTTPException(
            status_code=400,
            detail="Invalid TTS cache key",
        )

    root = Path(settings.xfyun_super_tts_storage_dir)
    path = root / cache_key / "standard.mp3"

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="TTS audio not found",
        )

    return FileResponse(
        path=str(path),
        media_type="audio/mpeg",
        filename=f"{cache_key}.mp3",
    )
