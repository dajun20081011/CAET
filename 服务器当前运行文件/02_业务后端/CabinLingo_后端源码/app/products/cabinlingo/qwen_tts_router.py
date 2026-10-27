from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID

from ...core.rbac import Principal, assert_permission, get_principal
from ...integrations.qwen_tts import QwenTTSClient, QwenTTSError, build_voice_catalog
from ...integrations.pronunciation import (
    PronunciationError,
    PronunciationRepository,
    builtin_pronunciations,
    merge_pronunciations,
    normalize_pronunciation_text,
    provider_pronunciations,
    resolve_pronunciations,
)
from .ai_runtime import provider_settings
from .prosody_analyzer import analyze_text as analyze_prosody_text, list_scenes as list_prosody_scenes
from .prosody_tts import ProsodyError, combine_wavs, preview_script, synthesize_script
from .storage import build_store
from .standard_pronunciation import (
    choose_standard_token,
    pronunciation_snapshot,
    resolve_standard_tokens,
    standard_audio,
    warm_standard_audio_cache,
)


router = APIRouter(prefix="/api/v1/cabinlingo", tags=["CabinLingo Qwen TTS"])
logger = logging.getLogger("uvicorn.error")
course_store = build_store()


class TTSPronunciationInput(BaseModel):
    phrase: str = Field(min_length=1, max_length=40)
    pinyin: str = Field(min_length=3, max_length=400)
    applied: bool = True


class TTSGenerateRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Literal["zh", "en"]
    voice: str = Field(min_length=1, max_length=200)
    rate: float = Field(ge=0.5, le=2.0)
    format: Literal["mp3", "wav"] = "mp3"
    pronunciations: list[TTSPronunciationInput] | None = Field(default=None, max_length=80)


class TTSPronunciationPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: Literal["zh", "en"] = "zh"


class TTSPronunciationUpsertRequest(BaseModel):
    phrase: str = Field(min_length=1, max_length=40)
    pinyin: str = Field(min_length=3, max_length=400)
    note: str = Field(default="", max_length=1000)
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)


class StandardPronunciationWarmRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: Literal["zh", "en"] = "zh"
    voice: str | None = Field(default=None, max_length=200)
    rate: float = Field(default=0.9, ge=0.5, le=2.0)


class LearnerStandardPronunciationRequest(BaseModel):
    attempt_id: UUID
    text: str = Field(min_length=1, max_length=80)
    reference_index: int | None = Field(default=None, ge=0)


class LearnerCoursePronunciationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    language: Literal["zh", "en"]


class ProsodyPreviewRequest(BaseModel):
    script: str = Field(min_length=1, max_length=12000)
    language: Literal["zh", "en"] = "zh"


class ProsodyGenerateRequest(ProsodyPreviewRequest):
    voice: str = Field(min_length=1, max_length=200)
    base_rate: float = Field(default=1.0, ge=0.5, le=2.0)


class ProsodyAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    scene: str = Field(default="general", min_length=1, max_length=80)


class ProsodyAssembleItem(BaseModel):
    index: int = Field(ge=0)
    pause_after_ms: int = Field(default=0, ge=0, le=3000)


def _admin(principal: Principal) -> None:
    assert_permission(principal, "cabinlingo", "cabinlingo:course.manage")


def _endpoint(settings) -> str:
    if settings.qwen_tts_workspace_id:
        return (
            f"https://{settings.qwen_tts_workspace_id}.cn-beijing.maas.aliyuncs.com"
            "/api/v1/services/audio/tts/SpeechSynthesizer"
        )
    return settings.qwen_tts_endpoint


def _client(settings) -> QwenTTSClient:
    return QwenTTSClient(
        endpoint=_endpoint(settings), api_key=settings.qwen_tts_api_key,
        model=settings.qwen_tts_model, timeout_seconds=settings.qwen_tts_timeout_seconds,
        max_audio_bytes=settings.qwen_tts_max_audio_bytes,
    )


def _pronunciation_repository(settings) -> PronunciationRepository:
    return PronunciationRepository(settings.database_url)


def _pronunciation_entries(settings) -> list[dict]:
    try:
        overrides = _pronunciation_repository(settings).list()
    except Exception as exc:
        raise HTTPException(503, "发音词典读取失败，请确认数据库迁移已经执行") from exc
    return merge_pronunciations(overrides)


def _standard_voice(settings, language: str, requested: str | None = None) -> str:
    voices = build_voice_catalog(settings.qwen_tts_model, settings.qwen_tts_voices)
    voice = next((item for item in voices if item["id"] == requested and language in item["languages"]), None)
    voice = voice or next((item for item in voices if language in item["languages"]), None)
    if not voice:
        raise HTTPException(422, "没有支持当前语言的千问音色")
    return str(voice["id"])


def _standard_cache_root(settings) -> Path:
    return Path(settings.upload_dir) / "standard-pronunciations"


def _attempt_context(settings, attempt_id: str, learner_id: str) -> str:
    import psycopg
    from psycopg.rows import dict_row
    from .html_sanitizer import extract_text

    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(standard.standard_text,'') AS standard_text,
                              COALESCE(content.sanitized_html,'') AS sanitized_html,
                              COALESCE(attempt.feedback->>'normalized_reference_text','') AS feedback_text
                       FROM cl_practice_attempts attempt
                       JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
                       LEFT JOIN cl_content_items content ON content.id=attempt.content_item_id
                       LEFT JOIN LATERAL (
                         SELECT standard_text FROM cl_course_standards item
                         WHERE item.content_item_id=content.id ORDER BY item.created_at DESC LIMIT 1
                       ) standard ON true
                       WHERE attempt.id=%s AND assignment.user_id=%s""", (attempt_id, learner_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "训练记录不存在")
    return (row["standard_text"] or "").strip() or extract_text(row["sanitized_html"] or "") or (row["feedback_text"] or "").strip()


def _run_standard_warmup(settings, data: StandardPronunciationWarmRequest, entries: list[dict], voice: str) -> None:
    try:
        warm_standard_audio_cache(
            text=data.text, language=data.language, entries=entries,
            model=settings.qwen_tts_model, voice=voice, rate=data.rate,
            cache_root=_standard_cache_root(settings), synthesize=_client(settings).synthesize,
        )
    except Exception:
        logger.exception("standard_pronunciation_warmup_failed")


@router.get("/admin/tts/options")
def tts_options(principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    voices = build_voice_catalog(settings.qwen_tts_model, settings.qwen_tts_voices)
    return {
        "enabled": settings.qwen_tts_enabled,
        "model": settings.qwen_tts_model,
        "languages": [{"id": "zh", "label": "中文"}, {"id": "en", "label": "English"}],
        "voices": voices,
        "voice_count": len(voices),
        "voice_source_counts": {
            source: sum(item.get("source") == source for item in voices)
            for source in ("system", "basic", "custom")
        },
        "rates": [0.75, 0.9, 1.0, 1.1, 1.25],
        "rate_control": {
            "min": 0.5, "max": 2.0, "step": 0.05, "default": 1.0,
            "recommended_min": 0.85, "recommended_max": 1.15,
        },
        "formats": ["mp3", "wav"],
        "max_text_chars": settings.qwen_tts_max_text_chars,
        "pronunciation": {
            "enabled": True,
            "dictionary_version": builtin_pronunciations()[0]["dictionary_version"],
            "builtin_count": len(builtin_pronunciations()),
            "automatic_context": True,
        },
    }


@router.post("/admin/tts/pronunciation-preview")
def pronunciation_preview(data: TTSPronunciationPreviewRequest,
                          principal: Principal = Depends(get_principal)):
    _admin(principal)
    if data.language != "zh":
        return {"items": [], "confirmed_count": 0, "predicted_count": 0, "requires_review": False}
    settings = provider_settings.effective_settings()
    normalized_text = normalize_pronunciation_text(data.text)
    items = [item.as_dict() for item in resolve_pronunciations(normalized_text, _pronunciation_entries(settings))]
    return {
        "items": items,
        "normalized_text": normalized_text,
        "confirmed_count": sum(item["confidence"] == "confirmed" for item in items),
        "predicted_count": sum(item["confidence"] == "predicted" for item in items),
        "requires_review": any(item["confidence"] == "predicted" for item in items),
    }


@router.get("/admin/tts/pronunciations")
def pronunciation_dictionary(principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    items = _pronunciation_entries(settings)
    return {
        "items": items,
        "total": len(items),
        "builtin_count": sum(item["source"] == "builtin" for item in items),
        "manual_count": sum(item["source"] == "manual" for item in items),
    }


@router.put("/admin/tts/pronunciations")
def save_pronunciation(data: TTSPronunciationUpsertRequest,
                       principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    try:
        saved = _pronunciation_repository(settings).upsert(
            phrase=data.phrase, numbered_pinyin=data.pinyin, note=data.note,
            enabled=data.enabled, priority=data.priority, actor_id=principal.user_id,
        )
        return {**saved, "source": "manual", "editable": True}
    except PronunciationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "发音词典保存失败，请确认数据库迁移已经执行") from exc


@router.delete("/admin/tts/pronunciations/{entry_id}", status_code=204)
def delete_pronunciation(entry_id: UUID, principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    try:
        if not _pronunciation_repository(settings).delete(str(entry_id), principal.user_id):
            raise HTTPException(404, "发音词典记录不存在")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "发音词典删除失败") from exc


@router.post("/admin/tts/standard-pronunciations/warm", status_code=202)
def warm_standard_pronunciations(
    data: StandardPronunciationWarmRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_principal),
):
    _admin(principal)
    settings = provider_settings.effective_settings()
    if not settings.qwen_tts_enabled:
        raise HTTPException(503, "千问语音合成尚未在服务器启用")
    entries = _pronunciation_entries(settings) if data.language == "zh" else []
    voice = _standard_voice(settings, data.language, data.voice)
    normalized, tokens = resolve_standard_tokens(data.text, entries)
    dictionary_version, dictionary_signature = pronunciation_snapshot(entries)
    unique_token_count = len({(item.text.casefold(), item.pinyin) for item in tokens})
    background_tasks.add_task(_run_standard_warmup, settings, data, entries, voice)
    return {
        "status": "queued", "context_length": len(normalized),
        "token_count": len(tokens), "unique_token_count": unique_token_count,
        "queued_token_count": min(unique_token_count, 500), "truncated": unique_token_count > 500,
        "dictionary_version": dictionary_version, "dictionary_signature": dictionary_signature,
        "voice": voice, "rate": data.rate,
    }


@router.post("/learner/tts/standard-pronunciation")
def learner_standard_pronunciation(
    data: LearnerStandardPronunciationRequest,
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:learn")
    settings = provider_settings.effective_settings()
    if not settings.qwen_tts_enabled:
        raise HTTPException(503, "标准发音服务暂不可用")
    context = _attempt_context(settings, str(data.attempt_id), principal.user_id)
    if not context:
        raise HTTPException(422, "当前训练记录没有可用的标准文本")
    language = "zh" if any("\u3400" <= char <= "\u9fff" for char in data.text) else "en"
    entries = _pronunciation_entries(settings) if language == "zh" else []
    normalized, tokens = resolve_standard_tokens(context, entries)
    if data.text.casefold() not in normalized.casefold():
        raise HTTPException(422, "请求的词语不属于当前训练文本")
    token = choose_standard_token(tokens, data.text, data.reference_index)
    _, dictionary_signature = pronunciation_snapshot(entries)
    voice = _standard_voice(settings, language)
    try:
        cached = standard_audio(
            token=token, language=language, model=settings.qwen_tts_model,
            voice=voice, rate=0.9, dictionary_signature=dictionary_signature,
            cache_root=_standard_cache_root(settings), synthesize=_client(settings).synthesize,
        )
    except PronunciationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QwenTTSError as exc:
        raise HTTPException(502, "千问标准发音生成失败") from exc
    return Response(cached.data, media_type=cached.content_type, headers={
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": 'inline; filename="standard-pronunciation.mp3"',
        "X-Standard-Pronunciation-Source": token.source,
        "X-Standard-Pronunciation-Cache": "hit" if cached.cache_hit else "generated",
    })


@router.post("/learner/course-v23/{course_version_id}/pronunciation")
def learner_course_pronunciation(
    course_version_id: str,
    data: LearnerCoursePronunciationRequest,
    principal: Principal = Depends(get_principal),
):
    assert_permission(principal, "cabinlingo", "cabinlingo:read")
    settings = provider_settings.effective_settings()
    if not settings.qwen_tts_enabled:
        raise HTTPException(503, "标准发音服务暂不可用")
    course = course_store.get_published_course_v23_for_user(course_version_id, principal.user_id)
    if not course:
        raise HTTPException(404, "已发布课程不存在")
    requested = data.text.strip()
    mistake = next((
        item for item in (course.get("mistake_words") or [])
        if str(item.get("language") or "") == data.language
        and str(item.get("term") or "").strip().casefold() == requested.casefold()
    ), None)
    if not mistake:
        raise HTTPException(422, "请求的词语不属于当前课程的易错词")
    text = str(mistake.get("term") or "").strip()
    entries = _pronunciation_entries(settings) if data.language == "zh" else []
    _, tokens = resolve_standard_tokens(text, entries)
    token = choose_standard_token(tokens, text)
    _, dictionary_signature = pronunciation_snapshot(entries)
    voice = _standard_voice(settings, data.language)
    try:
        cached = standard_audio(
            token=token, language=data.language, model=settings.qwen_tts_model,
            voice=voice, rate=0.9, dictionary_signature=dictionary_signature,
            cache_root=_standard_cache_root(settings), synthesize=_client(settings).synthesize,
        )
    except PronunciationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QwenTTSError as exc:
        raise HTTPException(502, "千问标准发音生成失败") from exc
    return Response(cached.data, media_type=cached.content_type, headers={
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": 'inline; filename="course-pronunciation.mp3"',
        "X-Standard-Pronunciation-Cache": "hit" if cached.cache_hit else "generated",
    })


@router.post("/admin/tts/generate")
def generate_tts(data: TTSGenerateRequest, principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    if not settings.qwen_tts_enabled:
        raise HTTPException(503, "千问语音合成尚未在服务器启用")
    raw_text = data.text.strip()
    text = normalize_pronunciation_text(raw_text) if data.language == "zh" else raw_text
    if not text or len(text) > settings.qwen_tts_max_text_chars:
        raise HTTPException(422, f"合成文本必须为 1–{settings.qwen_tts_max_text_chars} 个字符")
    voice = next((item for item in build_voice_catalog(settings.qwen_tts_model, settings.qwen_tts_voices)
                  if item["id"] == data.voice), None)
    if not voice or data.language not in voice["languages"]:
        raise HTTPException(422, "当前音色不支持所选语种")
    try:
        requested_pronunciations = (
            [item.model_dump() for item in data.pronunciations]
            if data.pronunciations is not None
            else [item.as_dict() for item in resolve_pronunciations(text, _pronunciation_entries(settings))]
        )
        hot_fixes = provider_pronunciations(text, requested_pronunciations) if data.language == "zh" else []
        final_payload = {
            "model": settings.qwen_tts_model,
            "input": {
                "text": text, "voice": data.voice, "format": data.format,
                "sample_rate": 24000, "rate": data.rate, "language_hints": [data.language],
                **({"hot_fix": {"pronunciation": hot_fixes}} if hot_fixes else {}),
            },
        }
        logger.info("tts_pronunciation_audit=%s", json.dumps({
            "raw_text": raw_text,
            "normalized_text": text,
            "pronunciation_hits": [f"{phrase} -> {pinyin}" for item in hot_fixes for phrase, pinyin in item.items()],
            "final_tts_payload": final_payload,
        }, ensure_ascii=False, separators=(",", ":")))
        audio = _client(settings).synthesize(text=text, voice=data.voice, language=data.language,
                                     rate=data.rate, audio_format=data.format,
                                     pronunciations=hot_fixes)
    except PronunciationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QwenTTSError as exc:
        raise HTTPException(502, "千问语音生成失败，请检查模型、音色、地域和服务额度") from exc
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'inline; filename="qwen-tts.{data.format}"',
        "X-Qwen-Request-Id": audio.request_id or "",
        "X-Pronunciation-Fix-Count": str(len(hot_fixes)),
    }
    return Response(audio.data, media_type=audio.content_type, headers=headers)


@router.get("/admin/tts/prosody/options")
def prosody_options(principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    return {
        "model": settings.qwen_tts_model,
        "languages": [{"id": "zh", "label": "中文"}, {"id": "en", "label": "English"}],
        "voices": build_voice_catalog(settings.qwen_tts_model, settings.qwen_tts_voices),
        "rates": [0.9, 1.0, 1.1],
        "notation": {
            "emphasis": "【文字】",
            "pauses": {"/": 200, "//": 400, "///": 700},
            "paces": ["稍慢", "中速", "稍快"],
            "tones": ["亲切", "平稳", "提醒", "关切", "严肃", "紧迫", "明确"],
            "intonation": {"↑": "上扬", "↓": "下降", "→": "平稳"},
        },
    }


@router.get("/admin/tts/prosody/scenes")
def prosody_scenes(principal: Principal = Depends(get_principal)):
    _admin(principal)
    return {"version": "2.1.0", "scenes": list_prosody_scenes()}


@router.post("/admin/tts/prosody/analyze")
def prosody_analyze(data: ProsodyAnalyzeRequest, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return analyze_prosody_text(data.text, data.scene)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/admin/tts/prosody/preview")
def prosody_preview(data: ProsodyPreviewRequest, principal: Principal = Depends(get_principal)):
    _admin(principal)
    try:
        return preview_script(data.script, data.language)
    except ProsodyError as exc:
        raise HTTPException(422, str(exc)) from exc


def _prosody_voice(settings, voice_id: str, language: str) -> None:
    voice = next((item for item in build_voice_catalog(settings.qwen_tts_model, settings.qwen_tts_voices) if item["id"] == voice_id), None)
    if not voice or language not in voice["languages"]:
        raise HTTPException(422, "音色不存在或不支持当前语言")


@router.post("/admin/tts/prosody/generate")
def prosody_generate(data: ProsodyGenerateRequest, principal: Principal = Depends(get_principal)):
    _admin(principal)
    settings = provider_settings.effective_settings()
    _prosody_voice(settings, data.voice, data.language)
    try:
        entries = _pronunciation_entries(settings) if data.language == "zh" else []
        audio, meta = synthesize_script(
            settings, script=data.script, voice=data.voice, language=data.language,
            base_rate=data.base_rate, pronunciation_entries=entries,
        )
    except ProsodyError as exc:
        raise HTTPException(502, str(exc)) from exc
    return Response(audio, media_type="audio/wav", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": 'inline; filename="qwen-prosody-tts.wav"',
        "X-CabinLingo-Prosody-Segments": str(meta["summary"]["segment_count"]),
        "X-Pronunciation-Fix-Count": str(meta["summary"]["pronunciation_hit_count"]),
        "X-CabinLingo-Opening-Processed": str(meta["summary"]["opening_processed"]).lower(),
        "X-CabinLingo-Closing-Processed": str(meta["summary"]["closing_processed"]).lower(),
    })


@router.post("/admin/tts/prosody/assemble")
async def prosody_assemble(
    manifest: str = Form(...),
    clips: list[UploadFile] = File(...),
    principal: Principal = Depends(get_principal),
):
    """Join the exact accepted sentence WAV files without invoking TTS again."""
    _admin(principal)
    if not 1 <= len(clips) <= 100:
        raise HTTPException(422, "音频片段数量必须为 1–100")
    try:
        raw_items = json.loads(manifest)
        if not isinstance(raw_items, list):
            raise ValueError("manifest must be a list")
        items = [ProsodyAssembleItem.model_validate(item) for item in raw_items]
    except Exception as exc:
        raise HTTPException(422, "合成清单格式无效") from exc
    if len(items) != len(clips):
        raise HTTPException(422, "合成清单与音频片段数量不一致")
    if [item.index for item in items] != list(range(len(items))):
        raise HTTPException(422, "音频片段顺序必须从 0 连续编号")

    parts: list[tuple[bytes, int]] = []
    total_bytes = 0
    for upload, item in zip(clips, items, strict=True):
        blob = await upload.read(16 * 1024 * 1024 + 1)
        await upload.close()
        if not blob or len(blob) > 16 * 1024 * 1024:
            raise HTTPException(422, f"第 {item.index + 1} 个片段为空或超过 16 MB")
        total_bytes += len(blob)
        if total_bytes > 100 * 1024 * 1024:
            raise HTTPException(422, "音频片段总大小不能超过 100 MB")
        parts.append((blob, item.pause_after_ms))
    try:
        audio = combine_wavs(parts)
    except ProsodyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(audio, media_type="audio/wav", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="cabinlingo-prosody.wav"',
        "X-CabinLingo-Prosody-Segments": str(len(parts)),
    })
