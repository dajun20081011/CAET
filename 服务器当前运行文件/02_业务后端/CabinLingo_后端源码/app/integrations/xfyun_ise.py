from __future__ import annotations

import base64
import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from .ai_gateway import AIResult, AudioLoader
from .xfyun_iat import _prepare_audio, build_xfyun_auth_url


@dataclass(frozen=True)
class XfyunISEConfig:
    endpoint: str
    app_id: str
    api_key: str
    api_secret: str
    provider: str = "xfyun"
    version: str = "v2"
    timeout_seconds: float = 30
    max_retries: int = 1
    backoff_seconds: float = 0.25
    audio_max_bytes: int = 15 * 1024 * 1024
    ent: str = "en_vip"
    category: str = "read_chapter"
    sample_rate: int = 16000
    score_scale: float = 100
    frame_bytes: int = 1280
    frame_interval_seconds: float = 0.04
    reference_max_chars: int = 20000

    @property
    def configured(self) -> bool:
        return all((self.endpoint, self.app_id, self.api_key, self.api_secret))


class XfyunISEError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class XfyunISEAdapter:
    name = "ise"

    def __init__(
        self,
        config: XfyunISEConfig,
        audio_loader: AudioLoader,
        connector: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.audio_loader = audio_loader
        self.connector = connector
        self.sleeper = sleeper
        self.provider = config.provider
        self.version = config.version
        self.configured = config.configured

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult:
        request_id = uuid4().hex
        if not self.configured:
            return AIResult(
                self.provider,
                self.name,
                self.version,
                "pending_adapter",
                {"issues": [{"type": "provider_unconfigured", "message": "讯飞 ISE 尚未配置", "severity": "info"}]},
                request_id=request_id,
            )
        if not reference_text.strip() or len(reference_text) > self.config.reference_max_chars:
            return self._failed(request_id, "reference_text_invalid", 1)

        for attempt in range(1, self.config.max_retries + 2):
            try:
                blob = self.audio_loader(audio_ref)
                if len(blob.data) > self.config.audio_max_bytes:
                    return self._failed(request_id, "audio_too_large", attempt)
                audio, encoding, audio_format = _prepare_audio(blob, self.config.sample_rate)
                xml_result, session_id = self._evaluate(reference_text, audio, encoding, audio_format)
                normalized = parse_xfyun_ise_xml(xml_result, self.config.score_scale)
                normalized["provider_session_id"] = session_id
                normalized["provider_payload_version"] = self.version
                return AIResult(
                    self.provider,
                    self.name,
                    self.version,
                    "completed",
                    normalized,
                    request_id=request_id,
                    attempts=attempt,
                )
            except XfyunISEError as exc:
                if attempt <= self.config.max_retries and exc.retryable:
                    self.sleeper(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, exc.code, attempt)
            except Exception:
                if attempt <= self.config.max_retries:
                    self.sleeper(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, "xfyun_ise_transport_error", attempt)
        return self._failed(request_id, "xfyun_ise_transport_error", self.config.max_retries + 1)

    def _evaluate(self, reference_text: str, audio: bytes, encoding: str,
                  audio_format: str) -> tuple[str, str | None]:
        connector = self.connector
        if connector is None:
            try:
                from websockets.sync.client import connect
            except ImportError as exc:
                raise XfyunISEError("websockets_dependency_missing", retryable=False) from exc
            connector = connect

        url = build_xfyun_auth_url(self.config.endpoint, self.config.api_key, self.config.api_secret)
        chunks = [audio[offset:offset + self.config.frame_bytes]
                  for offset in range(0, len(audio), self.config.frame_bytes)]
        if not chunks:
            raise XfyunISEError("audio_empty", retryable=False)

        session_id: str | None = None
        encoded_result: str | None = None
        try:
            with connector(
                url,
                open_timeout=self.config.timeout_seconds,
                close_timeout=self.config.timeout_seconds,
                max_size=8 * 1024 * 1024,
            ) as socket:
                socket.send(json.dumps(self._initial_frame(reference_text, encoding, audio_format),
                                       ensure_ascii=False, separators=(",", ":")))
                for index, chunk in enumerate(chunks):
                    aus = 1 if index == 0 else 2
                    socket.send(json.dumps({
                        "business": {"cmd": "auw", "aus": aus, "aue": encoding},
                        "data": {
                            "status": 1,
                            "data": base64.b64encode(chunk).decode("ascii"),
                            "data_type": 1,
                            "encoding": encoding,
                        },
                    }, separators=(",", ":")))
                    if self.config.frame_interval_seconds:
                        self.sleeper(self.config.frame_interval_seconds)
                socket.send(json.dumps({
                    "business": {"cmd": "auw", "aus": 4, "aue": encoding},
                    "data": {"status": 2, "data": "", "data_type": 1, "encoding": encoding},
                }, separators=(",", ":")))

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
                        raise XfyunISEError(f"xfyun_ise_code_{code}", retryable=False)
                    session_id = str(payload.get("sid") or session_id or "") or None
                    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                    if isinstance(data.get("data"), str) and data["data"]:
                        encoded_result = data["data"]
                    if data.get("status") == 2:
                        break
        except XfyunISEError:
            raise
        except Exception as exc:
            raise XfyunISEError("xfyun_ise_transport_error", retryable=True) from exc

        if not encoded_result:
            raise XfyunISEError("xfyun_ise_result_missing", retryable=False)
        try:
            result_bytes = base64.b64decode(encoded_result, validate=True)
        except (ValueError, TypeError) as exc:
            raise XfyunISEError("xfyun_ise_result_invalid", retryable=False) from exc
        for codec in ("utf-8-sig", "gb18030"):
            try:
                return result_bytes.decode(codec), session_id
            except UnicodeDecodeError:
                continue
        raise XfyunISEError("xfyun_ise_result_invalid", retryable=False)

    def _initial_frame(self, reference_text: str, encoding: str,
                       audio_format: str) -> dict[str, Any]:
        text = reference_text.strip()
        if self.config.ent == "en_vip" and not text.lstrip().startswith("[content]"):
            text = "[content]\n" + text
        return {
            "common": {"app_id": self.config.app_id},
            "business": {
                "sub": "ise",
                "ent": self.config.ent,
                "category": self.config.category,
                "cmd": "ssb",
                "text": "\ufeff" + text,
                "tte": "utf-8",
                "ttp_skip": True,
                "auf": audio_format,
                "aue": encoding,
                "rst": "entirety",
                "ise_unite": "1",
                "extra_ability": "multi_dimension",
                "plev": "0",
            },
            "data": {"status": 0, "data": ""},
        }

    def _failed(self, request_id: str, code: str, attempts: int) -> AIResult:
        return AIResult(
            self.provider,
            self.name,
            self.version,
            "failed",
            {"issues": [{"type": code, "message": "讯飞语音评测暂时不可用，请稍后重试", "severity": "error"}]},
            request_id=request_id,
            attempts=attempts,
            error_code=code,
        )


def parse_xfyun_ise_xml(xml_text: str, score_scale: float = 100) -> dict[str, Any]:
    if not xml_text or len(xml_text.encode("utf-8")) > 8 * 1024 * 1024:
        raise XfyunISEError("xfyun_ise_result_invalid", retryable=False)
    lowered = xml_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise XfyunISEError("xfyun_ise_result_invalid", retryable=False)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise XfyunISEError("xfyun_ise_result_invalid", retryable=False) from exc

    score_attributes = {"accuracy_score", "phone_score", "fluency_score", "integrity_score", "standard_score", "total_score"}
    nodes = list(root.iter())
    scored = [node for node in nodes if score_attributes.intersection(node.attrib)]
    if not scored:
        raise XfyunISEError("xfyun_ise_result_missing_scores", retryable=False)
    summary = max(scored, key=lambda node: len(score_attributes.intersection(node.attrib)))

    scores: dict[str, float] = {}
    mappings = {
        "pronunciation": ("accuracy_score", "phone_score", "standard_score"),
        "fluency": ("fluency_score",),
        "completeness": ("integrity_score",),
    }
    for name, candidates in mappings.items():
        for candidate in candidates:
            value = _normalized_score(summary.attrib.get(candidate), score_scale)
            if value is not None:
                scores[name] = value
                break
    if not scores:
        total = _normalized_score(summary.attrib.get("total_score"), score_scale)
        if total is not None:
            scores["pronunciation"] = total

    issues: list[dict[str, Any]] = []
    rejected = str(summary.attrib.get("is_rejected", "")).strip().lower() in {"1", "true", "yes"}
    if rejected:
        issues.append({
            "type": "speech_rejected",
            "message": "朗读内容与标准文本不匹配，或录音质量不足，请重新录制。",
            "severity": "warning",
        })
    except_info = str(summary.attrib.get("except_info", "")).strip()
    if except_info and except_info not in {"0", "none", "null"}:
        issues.append({"type": "provider_exception", "message": "讯飞评测提示录音存在异常。", "severity": "warning"})

    for node in nodes:
        if len(issues) >= 100:
            break
        dp_message = _integer(node.attrib.get("dp_message"))
        werr_message = _integer(node.attrib.get("werr_msg"))
        if not dp_message and not werr_message:
            continue
        word = str(node.attrib.get("content", "")).strip()[:80]
        issue_type, message = _word_issue(dp_message or werr_message)
        issue: dict[str, Any] = {"type": issue_type, "message": message, "severity": "warning"}
        if word:
            issue["word"] = word
        start = _integer(node.attrib.get("beg_pos"))
        end = _integer(node.attrib.get("end_pos"))
        if start is not None:
            issue["start_ms"] = max(start, 0) * 10
        if end is not None:
            issue["end_ms"] = max(end, 0) * 10
        issues.append(issue)

    total_score = _normalized_score(summary.attrib.get("total_score"), score_scale)
    return {
        "scores": scores,
        "issues": issues,
        "total_score": total_score,
        "is_rejected": rejected,
    }


def _normalized_score(value: str | None, scale: float) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    normalized = number / max(scale, 0.0001) * 100
    return round(min(100, max(0, normalized)), 2)


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _word_issue(code: int | None) -> tuple[str, str]:
    value = code or 0
    if value & 16:
        return "word_omitted", "存在漏读，请对照广播词重新练习。"
    if value & 32:
        return "word_inserted", "存在增读，请按广播词原文朗读。"
    if value & 64:
        return "word_repeated", "存在回读，请保持连贯。"
    if value & 128:
        return "word_replaced", "存在错读，请注意该词发音。"
    return "pronunciation_error", "该词发音需要改进。"
