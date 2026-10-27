from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .http_client import HTTPClient, HTTPClientError


class QwenTTSError(RuntimeError):
    pass


_SYSTEM_VOICES: dict[str, tuple[dict[str, Any], ...]] = {
    "qwen-audio-3.0-tts-flash": (
        {"id": "longanfengyue", "label": "龙安风悦", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "自然亲切音", "age": 30},
        {"id": "longanyuanfei", "label": "龙安元妃", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "高傲妃子音", "age": 30},
        {"id": "longanlingxi", "label": "龙安灵希", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "可爱甜美音", "age": 25},
        {"id": "longanxiaoxin", "label": "龙安小昕", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "亲切活泼音", "age": 22},
        {"id": "longanhuan_v3.6", "label": "龙安欢", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "自然女声", "age": 25},
        {"id": "longjielidou_v3.6", "label": "龙杰力豆", "languages": ["zh", "en"],
         "gender": "male", "category": "儿童陪伴", "trait": "天真男童", "age": 5},
        {"id": "longpaopao_v3.6", "label": "龙泡泡", "languages": ["zh", "en"],
         "gender": "female", "category": "儿童陪伴", "trait": "软糯可爱音", "age": 5},
        {"id": "longhuohuo_v3.6", "label": "龙火火", "languages": ["zh", "en"],
         "gender": "male", "category": "角色音", "trait": "顽皮少年音", "age": 8},
        {"id": "longchuanshu_v3.6", "label": "龙川叔", "languages": ["zh", "en"],
         "gender": "male", "category": "角色音", "trait": "川普大叔音", "age": 40},
        {"id": "loongmary", "label": "Mary", "languages": ["en"],
         "gender": "female", "category": "英文音色", "trait": "温暖英音", "age": 20},
        {"id": "loongeva_v3.6", "label": "Eva", "languages": ["en"],
         "gender": "female", "category": "英文音色", "trait": "高智美音", "age": 28},
        {"id": "loongjohn", "label": "John", "languages": ["en"],
         "gender": "male", "category": "英文音色", "trait": "沉稳亲切美音", "age": 28},
    ),
    "qwen-audio-3.0-tts-plus": (
        {"id": "longanlingxin", "label": "龙安灵心", "languages": ["zh", "en"],
         "gender": "female", "category": "社交陪伴", "trait": "知心温暖音", "age": 25},
        {"id": "longanlufeng", "label": "龙安鲁风", "languages": ["zh", "en"],
         "gender": "male", "category": "社交陪伴", "trait": "明亮开朗音", "age": 25},
    ),
}

_BASIC_CATALOG_FILES = {
    "qwen-audio-3.0-tts-flash": "qwen_audio_3_tts_flash_basic_voices.json",
}


@dataclass(frozen=True)
class QwenTTSAudio:
    data: bytes
    content_type: str
    request_id: str | None


def parse_voice_catalog(raw: str) -> list[dict[str, Any]]:
    voices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw.split(";"):
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 3 or not parts[0] or parts[0] in seen:
            continue
        languages = [item for item in parts[2].split("+") if item in {"zh", "en"}]
        if not languages:
            continue
        seen.add(parts[0])
        voices.append({"id": parts[0], "label": parts[1] or parts[0], "languages": languages})
    return voices


@lru_cache(maxsize=4)
def _basic_voice_catalog(model: str) -> tuple[dict[str, Any], ...]:
    filename = _BASIC_CATALOG_FILES.get(model)
    if not filename:
        return ()
    path = Path(__file__).resolve().parents[1] / "data" / filename
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ()
    if payload.get("model") != model or not isinstance(payload.get("voices"), list):
        return ()
    voices = []
    for item in payload["voices"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        languages = item.get("languages")
        if not isinstance(languages, list) or not languages or any(value not in {"zh", "en"} for value in languages):
            continue
        voices.append({**item, "source": "basic"})
    return tuple(voices)


def build_voice_catalog(model: str, configured: str) -> list[dict[str, Any]]:
    """Return model-safe system voices merged with administrator-defined voices."""
    voices: list[dict[str, Any]] = [
        {**item, "source": "system"} for item in _SYSTEM_VOICES.get(model, ())
    ]
    voices.extend(dict(item) for item in _basic_voice_catalog(model))
    indexes = {item["id"]: index for index, item in enumerate(voices)}
    for item in parse_voice_catalog(configured):
        if item["id"] in indexes:
            current = voices[indexes[item["id"]]]
            voices[indexes[item["id"]]] = {**current, **item}
            continue
        indexes[item["id"]] = len(voices)
        voices.append({
            **item,
            "gender": "unknown",
            "category": "自定义音色",
            "trait": "管理员配置",
            "age": None,
            "source": "custom",
        })
    return voices


class QwenTTSClient:
    def __init__(self, *, endpoint: str, api_key: str, model: str, timeout_seconds: float,
                 max_audio_bytes: int, http: HTTPClient | None = None) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.http = http or HTTPClient(timeout_seconds=timeout_seconds, max_retries=1,
                                       max_response_bytes=max_audio_bytes)
        self.max_audio_bytes = max_audio_bytes

    def synthesize(self, *, text: str, voice: str, language: str, rate: float,
                   audio_format: str, pronunciations: list[dict[str, str]] | None = None) -> QwenTTSAudio:
        try:
            input_payload: dict[str, Any] = {
                "text": text,
                "voice": voice,
                "format": audio_format,
                "sample_rate": 24000,
                "rate": rate,
                "language_hints": [language],
            }
            if language == "zh" and pronunciations:
                input_payload["hot_fix"] = {"pronunciation": pronunciations}
            result, _ = self.http.request_json(
                "POST", self.endpoint,
                payload={
                    "model": self.model,
                    "input": input_payload,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            output = result.get("output") if isinstance(result.get("output"), dict) else {}
            audio = output.get("audio") if isinstance(output.get("audio"), dict) else {}
            url = audio.get("url")
            if not isinstance(url, str) or not url:
                raise QwenTTSError("provider_audio_url_missing")
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"} or not (host == "aliyuncs.com" or host.endswith(".aliyuncs.com")):
                raise QwenTTSError("provider_audio_url_rejected")
            downloaded = self.http.request("GET", url, headers={"Accept": "audio/*"})
            if not downloaded.body or len(downloaded.body) > self.max_audio_bytes:
                raise QwenTTSError("provider_audio_invalid")
            content_type = downloaded.headers.get("content-type", "").split(";", 1)[0]
            expected = {"mp3": "audio/mpeg", "wav": "audio/wav"}[audio_format]
            if content_type and not (content_type.startswith("audio/") or content_type == "application/octet-stream"):
                raise QwenTTSError("provider_audio_content_type_invalid")
            request_id = result.get("request_id")
            return QwenTTSAudio(downloaded.body, expected, request_id if isinstance(request_id, str) else None)
        except HTTPClientError as exc:
            raise QwenTTSError(exc.code) from exc
