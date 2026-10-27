from __future__ import annotations

import base64
import email.utils
import hashlib
import hmac
import io
import json
import re
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from .ai_gateway import AIResult, AudioBlob, AudioLoader


def select_reference_language(
    reference_text: str,
    *,
    chinese: str,
    english: str,
    fallback: str,
) -> str:
    """Choose the provider language from the current reference text.

    Digits and punctuation do not affect the decision. English is counted by
    words rather than letters so short airline codes do not overpower Chinese
    content. On a mixed-script tie Chinese wins because IAT zh_cn can retain
    simple English; script-free input keeps the configured fallback.
    """
    chinese_count = sum(1 for character in reference_text if "\u3400" <= character <= "\u9fff")
    english_count = len(re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", reference_text))
    if chinese_count > english_count:
        return chinese
    if english_count > chinese_count:
        return english
    if chinese_count:
        return chinese
    return fallback


def build_xfyun_auth_url(endpoint: str, api_key: str, api_secret: str,
                         now: datetime | None = None) -> str:
    """Build the signed WebSocket URL required by Xfyun IAT v2."""
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc or not parsed.path:
        raise ValueError("ASR_IAT_ENDPOINT must be a ws(s) URL with a path")
    date = email.utils.format_datetime(now or datetime.now(timezone.utc), usegmt=True)
    request_line = f"GET {parsed.path} HTTP/1.1"
    origin = f"host: {parsed.netloc}\ndate: {date}\n{request_line}"
    digest = hmac.new(api_secret.encode("utf-8"), origin.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("ascii")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"authorization": authorization, "date": date, "host": parsed.netloc})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


@dataclass(frozen=True)
class XfyunIATConfig:
    endpoint: str
    app_id: str
    api_key: str
    api_secret: str
    provider: str = "xfyun"
    version: str = "v2"
    timeout_seconds: float = 15
    max_retries: int = 1
    backoff_seconds: float = 0.25
    audio_max_bytes: int = 15 * 1024 * 1024
    language: str = "en_us"
    domain: str = "iat"
    accent: str = "mandarin"
    sample_rate: int = 16000
    frame_bytes: int = 1280
    frame_interval_seconds: float = 0.04

    @property
    def configured(self) -> bool:
        return all((self.endpoint, self.app_id, self.api_key, self.api_secret))


class XfyunIATAdapter:
    name = "asr_iat"

    def __init__(self, config: XfyunIATConfig, audio_loader: AudioLoader) -> None:
        self.config = config
        self.audio_loader = audio_loader
        self.provider = config.provider
        self.version = config.version
        self.configured = config.configured

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult:
        request_id = uuid4().hex
        if not self.configured:
            return AIResult(self.provider, self.name, self.version, "pending_adapter",
                            {"issues": [{"type": "provider_unconfigured", "message": "讯飞 IAT 尚未配置", "severity": "info"}]},
                            request_id=request_id)
        for attempt in range(1, self.config.max_retries + 2):
            try:
                assessment_language = select_reference_language(
                    reference_text,
                    chinese="zh_cn",
                    english="en_us",
                    fallback=self.config.language,
                )
                blob = self.audio_loader(audio_ref)
                if len(blob.data) > self.config.audio_max_bytes:
                    return self._failed(request_id, "audio_too_large", attempt)
                audio, encoding, fmt = _prepare_audio(blob, self.config.sample_rate)
                transcription = self._transcribe(audio, encoding, fmt, assessment_language)
                # Keep compatibility with tests/custom adapters that still return the
                # pre-V2 ``(transcript, session_id)`` tuple.
                if isinstance(transcription, tuple):
                    transcript, session_id = transcription
                    transcription = {
                        "transcript": transcript,
                        "tokens": [],
                        "vad_segments": [],
                        "session_id": session_id,
                    }
                transcript = str(transcription.get("transcript") or "")
                session_id = transcription.get("session_id")
                return AIResult(self.provider, self.name, self.version, "completed", {
                    "transcript": transcript,
                    "tokens": transcription.get("tokens") if isinstance(transcription.get("tokens"), list) else [],
                    "vad_segments": (
                        transcription.get("vad_segments")
                        if isinstance(transcription.get("vad_segments"), list) else []
                    ),
                    "scores": {},
                    "issues": [],
                    "session_id": session_id,
                    "provider_session_id": session_id,
                    "reference_text": reference_text,
                    "assessment_language": assessment_language,
                }, request_id=request_id, attempts=attempt)
            except XfyunIATError as exc:
                if attempt <= self.config.max_retries and exc.retryable:
                    time.sleep(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, exc.code, attempt)
            except Exception:
                if attempt <= self.config.max_retries:
                    time.sleep(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, "xfyun_transport_error", attempt)
        return self._failed(request_id, "xfyun_transport_error", self.config.max_retries + 1)

    def _transcribe(
        self,
        audio: bytes,
        encoding: str,
        audio_format: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        try:
            from websockets.sync.client import connect
        except ImportError as exc:
            raise XfyunIATError("websockets_dependency_missing", retryable=False) from exc

        url = build_xfyun_auth_url(self.config.endpoint, self.config.api_key, self.config.api_secret)
        chunks = [audio[offset:offset + self.config.frame_bytes]
                  for offset in range(0, len(audio), self.config.frame_bytes)] or [b""]
        segments: dict[int, str] = {}
        token_segments: dict[int, list[dict[str, Any]]] = {}
        vad_segment_groups: dict[int, list[dict[str, Any]]] = {}
        session_id: str | None = None
        try:
            with connect(url, open_timeout=self.config.timeout_seconds,
                         close_timeout=self.config.timeout_seconds,
                         max_size=4 * 1024 * 1024) as socket:
                for index, chunk in enumerate(chunks):
                    status = 0 if index == 0 else 1
                    frame: dict[str, Any] = {"data": {"status": status, "format": audio_format,
                                                        "encoding": encoding,
                                                        "audio": base64.b64encode(chunk).decode("ascii")}}
                    if index == 0:
                        frame["common"] = {"app_id": self.config.app_id}
                        frame["business"] = self._business(language)
                    socket.send(json.dumps(frame, ensure_ascii=False, separators=(",", ":")))
                    if self.config.frame_interval_seconds:
                        time.sleep(self.config.frame_interval_seconds)
                socket.send(json.dumps({"data": {"status": 2}}, separators=(",", ":")))
                deadline = time.monotonic() + self.config.timeout_seconds
                while time.monotonic() < deadline:
                    try:
                        raw = socket.recv(timeout=max(0.1, deadline - time.monotonic()))
                    except TimeoutError:
                        break
                    if not raw:
                        break
                    payload = json.loads(raw)
                    code = int(payload.get("code", 0) or 0)
                    if code:
                        raise XfyunIATError(f"xfyun_code_{code}", retryable=False)
                    session_id = str(payload.get("sid") or session_id or "") or None
                    _append_result(segments, payload, token_segments, vad_segment_groups)
                    result = ((payload.get("data") or {}).get("result") or {})
                    if (payload.get("data") or {}).get("status") == 2 or result.get("ls") is True:
                        break
        except XfyunIATError:
            raise
        except Exception as exc:
            raise XfyunIATError("xfyun_transport_error", retryable=True) from exc
        ordered_serials = sorted(segments)
        return {
            "transcript": "".join(segments[index] for index in ordered_serials),
            "tokens": [
                token
                for serial in ordered_serials
                for token in token_segments.get(serial, [])
            ],
            "vad_segments": [
                segment
                for serial in sorted(vad_segment_groups)
                for segment in vad_segment_groups[serial]
            ],
            "session_id": session_id,
        }

    def _business(self, language: str | None = None) -> dict[str, Any]:
        return {"language": language or self.config.language, "domain": self.config.domain,
                "accent": self.config.accent, "ptt": 1, "pcm": 1, "vinfo": 1}

    def _failed(self, request_id: str, code: str, attempts: int) -> AIResult:
        return AIResult(self.provider, self.name, self.version, "failed", {
            "issues": [{"type": code, "message": "讯飞语音听写暂时不可用，请稍后重试", "severity": "error"}]
        }, request_id=request_id, attempts=attempts, error_code=code)


class XfyunIATError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def _prepare_audio(blob: AudioBlob, default_rate: int) -> tuple[bytes, str, str]:
    content_type = (blob.content_type or "").lower()
    suffix = blob.filename.lower().rsplit(".", 1)[-1] if "." in blob.filename else ""
    if content_type in {"audio/wav", "audio/x-wav", "audio/wave"} or suffix == "wav":
        try:
            with wave.open(io.BytesIO(blob.data), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() not in {8000, 16000}:
                    raise XfyunIATError("audio_format_unsupported", retryable=False)
                return wav.readframes(wav.getnframes()), "raw", f"audio/L16;rate={wav.getframerate()}"
        except (wave.Error, EOFError) as exc:
            raise XfyunIATError("audio_format_unsupported", retryable=False) from exc
    if content_type in {"audio/mpeg", "audio/mp3"} or suffix == "mp3":
        return blob.data, "lame", f"audio/L16;rate={default_rate}"
    if content_type in {"audio/l16", "audio/pcm", "application/octet-stream"} or suffix in {"pcm", "raw"}:
        return blob.data, "raw", f"audio/L16;rate={default_rate}"
    raise XfyunIATError("audio_format_unsupported", retryable=False)


def _frame_to_ms(value: Any) -> int | None:
    """Convert an Xfyun 10 ms frame offset without inventing missing timings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        frame = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return frame * 10 if frame >= 0 else None


def _confidence(value: Any) -> float | None:
    """Normalize an explicit provider confidence without treating ``sc`` as one.

    Xfyun documents ``cw.sc`` as a reserved field, so it is retained as raw
    provider evidence but never promoted to confidence.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if normalized > 1:
        normalized /= 100
    if not 0 <= normalized <= 1:
        return None
    return round(normalized, 4)


def _append_result(
    segments: dict[int, str],
    payload: dict[str, Any],
    token_segments: dict[int, list[dict[str, Any]]] | None = None,
    vad_segment_groups: dict[int, list[dict[str, Any]]] | None = None,
) -> None:
    """Append one IAT result while preserving ``sn``/``rpl`` semantics.

    The optional timing collections keep the old two-argument call compatible.
    ``ws[].cw`` contains alternatives; only the first candidate contributes to
    the recognized transcript and token stream.
    """
    result = ((payload.get("data") or {}).get("result") or {})
    if not isinstance(result, dict):
        return
    try:
        serial = int(result.get("sn", max(segments, default=0) + 1))
    except (TypeError, ValueError):
        serial = max(segments, default=0) + 1
    if result.get("pgs") == "rpl" and isinstance(result.get("rg"), list) and len(result["rg"]) == 2:
        try:
            start, end = int(result["rg"][0]), int(result["rg"][1])
            for index in range(start, end + 1):
                segments.pop(index, None)
                if token_segments is not None:
                    token_segments.pop(index, None)
                if vad_segment_groups is not None:
                    vad_segment_groups.pop(index, None)
        except (TypeError, ValueError):
            pass

    text_parts: list[str] = []
    parsed_tokens: list[dict[str, Any]] = []
    raw_words = result.get("ws") if isinstance(result.get("ws"), list) else []
    for item in raw_words:
        if not isinstance(item, dict):
            continue
        candidates = item.get("cw") if isinstance(item.get("cw"), list) else []
        selected = next((candidate for candidate in candidates if isinstance(candidate, dict)), None)
        if selected is None:
            continue
        token_text = str(selected.get("w") or "")
        text_parts.append(token_text)
        provider_bg = item.get("bg")
        parsed_token: dict[str, Any] = {
            "text": token_text,
            "start_ms": _frame_to_ms(provider_bg),
            "provider_bg": provider_bg,
            "serial": serial,
        }
        explicit_confidence = next(
            (_confidence(selected.get(key)) for key in ("confidence", "confidence_score", "probability")
             if selected.get(key) is not None),
            None,
        )
        if explicit_confidence is not None:
            parsed_token["confidence"] = explicit_confidence
        provider_fields = {
            key: selected[key]
            for key in ("sc", "wb", "wc", "we", "wp")
            if key in selected
        }
        if provider_fields:
            parsed_token["provider_fields"] = provider_fields
        parsed_tokens.append(parsed_token)

    parsed_vad: list[dict[str, Any]] = []
    vad = result.get("vad") if isinstance(result.get("vad"), dict) else {}
    raw_vad = vad.get("ws") if isinstance(vad.get("ws"), list) else []
    for item in raw_vad:
        if not isinstance(item, dict):
            continue
        provider_bg = item.get("bg")
        provider_ed = item.get("ed")
        parsed_vad.append({
            "start_ms": _frame_to_ms(provider_bg),
            "end_ms": _frame_to_ms(provider_ed),
            "provider_bg": provider_bg,
            "provider_ed": provider_ed,
            "serial": serial,
        })

    text = "".join(text_parts)
    segments[serial] = text
    if token_segments is not None:
        token_segments[serial] = parsed_tokens
    if vad_segment_groups is not None:
        vad_segment_groups[serial] = parsed_vad
