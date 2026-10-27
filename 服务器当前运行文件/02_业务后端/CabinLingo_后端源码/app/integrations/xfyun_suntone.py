from __future__ import annotations

import base64
import gzip
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from pypinyin import Style, pinyin

from .ai_gateway import AIResult, AudioLoader
from .audio_transcoder import AudioTranscodeError, encode_suntone_mp3
from .xfyun_iat import build_xfyun_auth_url, select_reference_language


_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]+")
_REFERENCE_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+(?:[.:]\d+)?|[\u3400-\u9fff]")
_EXPLICIT_PINYIN_RE = re.compile(r"[\u3400-\u9fff]\{[a-zA-ZvV:]+[1-5]\}")
_TONE_RE = re.compile(r"(?:tone)?([1-5])$", re.IGNORECASE)
_TONE_CONFIRM_THRESHOLD = 70.0


@dataclass(frozen=True)
class XfyunSuntoneConfig:
    endpoint: str
    app_id: str
    api_key: str
    api_secret: str
    provider: str = "xfyun_suntone"
    version: str = "v1"
    timeout_seconds: float = 30
    max_retries: int = 1
    backoff_seconds: float = 0.25
    audio_max_bytes: int = 15 * 1024 * 1024
    encoded_audio_max_bytes: int = 7 * 1024 * 1024
    reference_max_chars: int = 4096
    language: str = "en"
    core: str = "para"
    dialect: str = "en_us"
    score_scale: int = 100
    score_precision: float = 1
    frame_bytes: int = 122
    frame_interval_seconds: float = 0.04
    ffmpeg_binary: str = "ffmpeg"
    transcode_timeout_seconds: float = 30
    transcode_max_seconds: int = 300

    @property
    def configured(self) -> bool:
        return all((self.endpoint, self.app_id, self.api_key, self.api_secret))


class XfyunSuntoneError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class XfyunSuntoneAdapter:
    name = "suntone"

    def __init__(
        self,
        config: XfyunSuntoneConfig,
        audio_loader: AudioLoader,
        connector: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        encoder: Callable[..., Any] = encode_suntone_mp3,
    ) -> None:
        self.config = config
        self.audio_loader = audio_loader
        self.connector = connector
        self.sleeper = sleeper
        self.encoder = encoder
        self.provider = config.provider
        self.version = config.version
        self.configured = config.configured

    def analyze(self, *, reference_text: str, audio_ref: str) -> AIResult:
        request_id = uuid4().hex
        reference = reference_text.strip()
        if not self.configured:
            return AIResult(
                self.provider,
                self.name,
                self.version,
                "pending_adapter",
                {"issues": [{"type": "provider_unconfigured", "message": "讯飞 Suntone 尚未配置", "severity": "info"}]},
                request_id=request_id,
            )
        if not reference or len(reference) > self.config.reference_max_chars:
            return self._failed(request_id, "reference_text_invalid", 1)

        for attempt in range(1, self.config.max_retries + 2):
            try:
                assessment_language = select_reference_language(
                    reference,
                    chinese="cn",
                    english="en",
                    fallback=self.config.language,
                )
                assessment_reference, pronunciation_hints = build_suntone_reference(
                    reference,
                    assessment_language,
                )
                if len(assessment_reference) > self.config.reference_max_chars:
                    assessment_reference, pronunciation_hints = reference, []
                blob = self.audio_loader(audio_ref)
                if len(blob.data) > self.config.audio_max_bytes:
                    return self._failed(request_id, "audio_too_large", attempt)
                encoded = self.encoder(
                    blob.data,
                    ffmpeg_binary=self.config.ffmpeg_binary,
                    timeout_seconds=self.config.transcode_timeout_seconds,
                    max_seconds=self.config.transcode_max_seconds,
                    max_input_bytes=self.config.audio_max_bytes,
                    max_output_bytes=self.config.encoded_audio_max_bytes,
                )
                if 4 * math.ceil(len(encoded.data) / 3) > 10 * 1024 * 1024:
                    return self._failed(request_id, "audio_too_large", attempt)
                provider_result, session_id = self._evaluate(
                    assessment_reference,
                    encoded.data,
                    assessment_language,
                )
                normalized = parse_xfyun_suntone_result(provider_result, self.config.score_scale, self.config.core)
                _attach_reference_pronunciations(normalized, pronunciation_hints)
                normalized["provider_session_id"] = session_id
                normalized["provider_payload_version"] = self.version
                normalized["assessment_language"] = assessment_language
                normalized["reference_text"] = reference
                normalized["assessment_reference_text"] = assessment_reference
                normalized["reference_pronunciations"] = pronunciation_hints
                return AIResult(
                    self.provider,
                    self.name,
                    self.version,
                    "completed",
                    normalized,
                    request_id=request_id,
                    attempts=attempt,
                )
            except AudioTranscodeError as exc:
                return self._failed(request_id, exc.code, attempt)
            except XfyunSuntoneError as exc:
                if attempt <= self.config.max_retries and exc.retryable:
                    self.sleeper(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, exc.code, attempt)
            except Exception:
                if attempt <= self.config.max_retries:
                    self.sleeper(self.config.backoff_seconds)
                    continue
                return self._failed(request_id, "xfyun_suntone_transport_error", attempt)
        return self._failed(request_id, "xfyun_suntone_transport_error", self.config.max_retries + 1)

    def _evaluate(
        self,
        reference_text: str,
        audio: bytes,
        language: str | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        connector = self.connector
        if connector is None:
            try:
                from websockets.sync.client import connect
            except ImportError as exc:
                raise XfyunSuntoneError("websockets_dependency_missing", retryable=False) from exc
            connector = connect

        url = build_xfyun_auth_url(self.config.endpoint, self.config.api_key, self.config.api_secret)
        chunks = [audio[offset:offset + self.config.frame_bytes]
                  for offset in range(0, len(audio), self.config.frame_bytes)]
        if not chunks:
            raise XfyunSuntoneError("audio_empty", retryable=False)

        session_id: str | None = None
        result_chunks: list[tuple[int, bytes, int]] = []
        try:
            with connector(
                url,
                open_timeout=self.config.timeout_seconds,
                close_timeout=self.config.timeout_seconds,
                max_size=12 * 1024 * 1024,
            ) as socket:
                for index, chunk in enumerate(chunks):
                    status = 2 if index == len(chunks) - 1 else 0 if index == 0 else 1
                    socket.send(json.dumps(
                        self._audio_frame(reference_text, chunk, index, status, language),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ))
                    if self.config.frame_interval_seconds and status != 2:
                        self.sleeper(self.config.frame_interval_seconds)

                deadline = time.monotonic() + self.config.timeout_seconds
                while time.monotonic() < deadline:
                    try:
                        raw = socket.recv(timeout=max(0.1, deadline - time.monotonic()))
                    except TimeoutError:
                        break
                    if not raw:
                        break
                    payload = json.loads(raw)
                    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
                    code = int(header.get("code", 0) or 0)
                    if code:
                        raise XfyunSuntoneError(f"xfyun_suntone_code_{code}", retryable=False)
                    session_id = str(header.get("sid") or session_id or "") or None
                    result = ((payload.get("payload") or {}).get("result") or {})
                    if isinstance(result, dict) and isinstance(result.get("text"), str) and result["text"]:
                        try:
                            decoded = base64.b64decode(result["text"], validate=True)
                        except (ValueError, TypeError) as exc:
                            raise XfyunSuntoneError("xfyun_suntone_result_invalid", retryable=False) from exc
                        if str(result.get("compress", "raw")).lower() == "gzip":
                            try:
                                decoded = gzip.decompress(decoded)
                            except OSError as exc:
                                raise XfyunSuntoneError("xfyun_suntone_result_invalid", retryable=False) from exc
                        result_chunks.append((int(result.get("seq", len(result_chunks)) or 0), decoded,
                                              int(result.get("status", header.get("status", 0)) or 0)))
                    if int(header.get("status", 0) or 0) == 2:
                        break
        except XfyunSuntoneError:
            raise
        except Exception as exc:
            raise XfyunSuntoneError("xfyun_suntone_transport_error", retryable=True) from exc

        return _decode_provider_result(result_chunks), session_id

    def _audio_frame(
        self,
        reference_text: str,
        chunk: bytes,
        seq: int,
        status: int,
        language: str | None = None,
    ) -> dict[str, Any]:
        assessment_language = language or select_reference_language(
            reference_text,
            chinese="cn",
            english="en",
            fallback=self.config.language,
        )
        business: dict[str, Any] = {
            "lang": assessment_language,
            "core": self.config.core,
            "refText": reference_text,
            "scale": self.config.score_scale,
            "precision": self.config.score_precision,
            "output_rawtext": 1,
            "paragraph_need_word_score": 1 if self.config.core == "para" else 0,
            # Suntone only includes word/character phoneme details when this is
            # requested.  The learner report needs those details for the
            # score colour, phoneme diagnosis and recording seek position.
            "phoneme_output": 1,
            "result": {"encoding": "utf8", "compress": "raw", "format": "plain"},
        }
        if assessment_language == "en" and self.config.dialect:
            business["dict_dialect"] = self.config.dialect
        return {
            "header": {"app_id": self.config.app_id, "status": status},
            "parameter": {"st": business},
            "payload": {"data": {
                "encoding": "lame",
                "sample_rate": 16000,
                "channels": 1,
                "bit_depth": 16,
                "status": status,
                "seq": seq,
                "audio": base64.b64encode(chunk).decode("ascii"),
                "frame_size": 0,
            }},
        }

    def _failed(self, request_id: str, code: str, attempts: int) -> AIResult:
        return AIResult(
            self.provider,
            self.name,
            self.version,
            "failed",
            {"issues": [{"type": code, "message": "讯飞 Suntone 评测暂时不可用，请稍后重试", "severity": "error"}]},
            request_id=request_id,
            attempts=attempts,
            error_code=code,
        )


def _decode_provider_result(chunks: list[tuple[int, bytes, int]]) -> dict[str, Any]:
    if not chunks:
        raise XfyunSuntoneError("xfyun_suntone_result_missing", retryable=False)
    ordered = sorted(chunks, key=lambda item: item[0])
    candidates = [item[1] for item in reversed(ordered) if item[2] == 2]
    candidates.extend([item[1] for item in reversed(ordered)])
    if len(ordered) > 1:
        candidates.append(b"".join(item[1] for item in ordered))
    for raw in candidates:
        if len(raw) > 8 * 1024 * 1024:
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    raise XfyunSuntoneError("xfyun_suntone_result_invalid", retryable=False)


def build_suntone_reference(
    reference_text: str,
    language: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Add a pinyin hint only when the current phrase resolves a polyphone."""
    if language != "cn" or not reference_text:
        return reference_text, []

    explicit_positions = {match.start() for match in _EXPLICIT_PINYIN_RE.finditer(reference_text)}
    token_indexes = {
        match.start(): index
        for index, match in enumerate(_REFERENCE_TOKEN_RE.finditer(reference_text))
    }
    replacements: dict[int, str] = {}
    hints: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}

    for run_match in _CJK_RUN_RE.finditer(reference_text):
        run = run_match.group(0)
        contextual = pinyin(
            run,
            style=Style.TONE3,
            heteronym=True,
            neutral_tone_with_five=True,
            strict=False,
        )
        for offset, character in enumerate(run):
            absolute_position = run_match.start() + offset
            occurrences[character] = occurrences.get(character, 0) + 1
            if absolute_position in explicit_positions or offset >= len(contextual):
                continue
            standalone = pinyin(
                character,
                style=Style.TONE3,
                heteronym=True,
                neutral_tone_with_five=True,
                strict=False,
            )
            standalone_readings = {
                _normalize_pinyin(item)
                for item in (standalone[0] if standalone else [])
                if _normalize_pinyin(item)
            }
            contextual_readings = {
                _normalize_pinyin(item)
                for item in contextual[offset]
                if _normalize_pinyin(item)
            }
            if len(standalone_readings) <= 1 or len(contextual_readings) != 1:
                continue
            expected_pinyin = next(iter(contextual_readings))
            tone_match = _TONE_RE.search(expected_pinyin)
            if tone_match is None:
                continue
            expected_tone = f"tone{tone_match.group(1)}"
            replacements[absolute_position] = f"{character}{{{expected_pinyin}}}"
            hints.append({
                "word": character,
                "occurrence": occurrences[character],
                "reference_index": token_indexes.get(absolute_position),
                "expected_pinyin": expected_pinyin,
                "expected_tone": expected_tone,
                "source": "contextual_pinyin",
            })

    if not replacements:
        return reference_text, []
    annotated = "".join(replacements.get(index, character) for index, character in enumerate(reference_text))
    return annotated, hints


def _normalize_pinyin(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("u:", "v").replace("ü", "v")
    return normalized if re.fullmatch(r"[a-zv]+[1-5]", normalized) else ""


def _attach_reference_pronunciations(
    normalized: dict[str, Any],
    hints: list[dict[str, Any]],
) -> None:
    if not hints:
        return
    details = normalized.get("word_details")
    issues = normalized.get("issues")
    if not isinstance(details, list) or not isinstance(issues, list):
        return

    used: set[int] = set()
    for hint in hints:
        expected_word = str(hint.get("word") or "")
        expected_index = hint.get("reference_index")
        match_index: int | None = None
        if isinstance(expected_index, int):
            match_index = next((
                index for index, detail in enumerate(details)
                if index not in used
                and isinstance(detail, dict)
                and detail.get("detail_level") == "word"
                and detail.get("reference_index") == expected_index
                and str(detail.get("word") or "") == expected_word
            ), None)
        if match_index is None:
            match_index = next((
                index for index, detail in enumerate(details)
                if index not in used
                and isinstance(detail, dict)
                and detail.get("detail_level") == "word"
                and str(detail.get("word") or "") == expected_word
            ), None)
        if match_index is None:
            continue
        used.add(match_index)
        detail = details[match_index]
        detail["expected_pinyin"] = hint["expected_pinyin"]
        detail["expected_tone"] = hint["expected_tone"]

        expected_tone = str(hint["expected_tone"])
        detected_tone = str(detail.get("detected_tone") or "")
        tone_score = detail.get("tone")
        mismatched_tone = bool(detected_tone and detected_tone != expected_tone)
        low_tone_score = isinstance(tone_score, (int, float)) and tone_score < _TONE_CONFIRM_THRESHOLD
        if not mismatched_tone and not low_tone_score:
            continue

        actual = _tone_description(detected_tone) if mismatched_tone else f"声调得分 {tone_score:g}"
        issues.append({
            "dimension": "pronunciation",
            "source": "suntone_tone_assessment",
            "provider": "xfyun_suntone",
            "type": "chinese_tone_error",
            "issue_status": "confirmed",
            "severity": "warning",
            "word": expected_word,
            "expected": f"{expected_word}（{hint['expected_pinyin']}，{_tone_description(expected_tone)}）",
            "actual": actual,
            "reference_index": detail.get("reference_index", expected_index),
            "start_ms": detail.get("start_ms", 0),
            "end_ms": detail.get("end_ms", 0),
            "message": f"「{expected_word}」在当前语境应读作 {hint['expected_pinyin']}，Suntone 检测到声调偏差。",
            "evidence": [
                {
                    "kind": "contextual_pronunciation",
                    "message": f"结合上下文确定标准读音为 {hint['expected_pinyin']}（{_tone_description(expected_tone)}）。",
                    "value": hint["expected_pinyin"],
                },
                {
                    "kind": "suntone_tone_score",
                    "message": f"Suntone 声调得分为 {tone_score:g}。" if isinstance(tone_score, (int, float)) else f"Suntone 检测声调为 {_tone_description(detected_tone)}。",
                    "value": tone_score if isinstance(tone_score, (int, float)) else detected_tone,
                },
            ],
            "training_advice": f"定位播放该字，按 {hint['expected_pinyin']}（{_tone_description(expected_tone)}）跟读后再练。",
        })
    normalized["issues"] = issues[:200]


def parse_xfyun_suntone_result(
    payload: dict[str, Any],
    score_scale: float = 100,
    core: str = "para",
) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if not isinstance(result, dict):
        raise XfyunSuntoneError("xfyun_suntone_result_invalid", retryable=False)

    scores: dict[str, float] = {}
    mappings = {
        "pronunciation": "pronunciation",
        "fluency": "fluency",
        "completeness": "integrity",
        "expression": "rhythm",
        "tone": "tone",
    }
    for target, source in mappings.items():
        value = _score(result.get(source), score_scale)
        if value is not None:
            scores[target] = value
    overall = _score(result.get("overall"), score_scale)
    if not scores and overall is None:
        raise XfyunSuntoneError("xfyun_suntone_result_missing_scores", retryable=False)

    issues: list[dict[str, Any]] = []
    warnings = result.get("warning") if isinstance(result.get("warning"), list) else []
    for warning in warnings[:20]:
        if not isinstance(warning, dict):
            continue
        issues.append({
            "type": f"provider_warning_{str(warning.get('code', 'unknown'))[:20]}",
            "message": "讯飞评测提示录音质量可能影响结果。",
            "severity": "warning",
        })

    details: list[dict[str, Any]] = []
    reference_index = 0
    flattened_nodes = _flatten_score_nodes(result)
    for node, detail_level in flattened_nodes[:500]:
        if not isinstance(node, dict):
            continue
        word = str(
            node.get("word")
            or node.get("content")
            or node.get("text")
            or node.get("sentence")
            or ""
        ).strip()[:200]
        read_type = _integer(node.get("readType") if "readType" in node else node.get("read_type"))
        span = node.get("span") if isinstance(node.get("span"), dict) else {}
        start = _integer(span.get("start"))
        end = _integer(span.get("end"))
        if start is None:
            start = _integer(node.get("start"))
        if end is None:
            end = _integer(node.get("end"))
        detail: dict[str, Any] = {
            "word": word,
            "read_type": read_type,
            "start_ms": max(start or 0, 0) * 10,
            "end_ms": max(end or 0, 0) * 10,
            "detail_level": detail_level,
        }
        char_type = _integer(node.get("charType") if "charType" in node else node.get("char_type"))
        if char_type is not None:
            detail["char_type"] = char_type
        if detail_level == "word" and char_type != 1 and word:
            detail["reference_index"] = reference_index
            reference_index += 1
        if node.get("pinyin"):
            detail["pinyin"] = str(node["pinyin"])[:80]
        detected_tone = node.get("tone")
        detected_match = _TONE_RE.fullmatch(detected_tone.strip()) if isinstance(detected_tone, str) else None
        if detected_match:
            detail["detected_tone"] = f"tone{detected_match.group(1)}"
        elif detail.get("pinyin"):
            pinyin_tone = _TONE_RE.search(str(detail["pinyin"]))
            if pinyin_tone:
                detail["detected_tone"] = f"tone{pinyin_tone.group(1)}"
        if isinstance(node.get("pause"), dict):
            pause_type = _integer(node["pause"].get("type"))
            pause_duration = _integer(node["pause"].get("duration"))
            detail["pause"] = {
                "type": pause_type,
                "duration_ms": max(pause_duration or 0, 0) * 10,
            }
        node_scores = node.get("scores") if isinstance(node.get("scores"), dict) else {}
        for name in ("overall", "pronunciation", "tone"):
            raw_score = node_scores.get(name) if name in node_scores else node.get(name)
            normalized_score = _score(raw_score, score_scale)
            if normalized_score is not None:
                detail[name] = normalized_score
        prominence = node_scores.get("prominence") if "prominence" in node_scores else node.get("prominence")
        if _integer(prominence) is not None:
            detail["prominence"] = _integer(prominence)
        phonemes: list[dict[str, Any]] = []
        raw_phonemes = node.get("phonemes")
        if not isinstance(raw_phonemes, list):
            raw_phonemes = node.get("phones") if isinstance(node.get("phones"), list) else []
        for phoneme in raw_phonemes[:50]:
            if not isinstance(phoneme, dict):
                continue
            phoneme_span = phoneme.get("span") if isinstance(phoneme.get("span"), dict) else {}
            phoneme_item: dict[str, Any] = {
                "phoneme": str(phoneme.get("phoneme") or "")[:40],
                "phone": str(phoneme.get("phone") or "")[:40],
                "start_ms": max(_integer(phoneme_span.get("start")) or 0, 0) * 10,
                "end_ms": max(_integer(phoneme_span.get("end")) or 0, 0) * 10,
            }
            phoneme_score = _score(phoneme.get("pronunciation"), score_scale)
            if phoneme_score is not None:
                phoneme_item["pronunciation"] = phoneme_score
            tone_index = _integer(phoneme.get("tone_index"))
            if tone_index is not None:
                phoneme_item["tone_index"] = tone_index
            phonemes.append(phoneme_item)
        if phonemes:
            detail["phonemes"] = phonemes
        details.append(detail)
        issue_type, message = _read_issue(read_type, core)
        if issue_type:
            issue: dict[str, Any] = {"type": issue_type, "message": message, "severity": "warning"}
            if word:
                issue["word"] = word
            issue["start_ms"], issue["end_ms"] = detail["start_ms"], detail["end_ms"]
            issues.append(issue)

    return {
        "scores": scores,
        "overall_score": overall,
        "speed": _integer(result.get("speed")),
        "rear_tone": str(result.get("rear_tone", ""))[:20] or None,
        "duration_seconds": _duration(result.get("duration")),
        "issues": issues[:200],
        "word_details": details,
        "word_detail_level": (
            "word" if any(item.get("detail_level") == "word" for item in details)
            else "sentence" if details else None
        ),
        "word_detail_count": sum(1 for item in details if item.get("detail_level") == "word"),
        "assessment_core": core,
        # Preserve the provider assessment payload for audit/reprocessing. It
        # contains scores and timing only; oversized responses are summarized
        # so an unexpected provider payload cannot grow the database without a
        # bound. Credentials and the uploaded audio are never part of this data.
        "provider_result": _bounded_provider_result(result),
    }


def _flatten_score_nodes(result: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Return provider score nodes in reading order without inventing word scores.

    Suntone responses observed in production have two paragraph layouts: a flat
    ``sentences`` array whose members are word score nodes, and sentence objects
    that contain a nested ``words``/``wordDetails`` array.  Older parsing treated
    each containing sentence as one word, which made every token in the report
    lose its score.  Sentence-only results remain sentence-level so the UI can
    clearly say that granular scores are unavailable instead of duplicating a
    sentence score across its words.
    """
    words = result.get("words")
    if isinstance(words, list):
        return [(item, "word") for item in words if isinstance(item, dict)]

    sentences = result.get("sentences")
    if not isinstance(sentences, list):
        return []

    flattened: list[tuple[dict[str, Any], str]] = []
    # The production Suntone paragraph response groups tokens under
    # ``sentences[].details[]``.  Other documented/observed variants use the
    # remaining keys below.  Each child is still parsed only when the provider
    # supplies its own score/timing fields; no sentence score is copied to it.
    child_keys = ("words", "wordDetails", "word_details", "details", "tokens", "items")
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        children: list[Any] | None = None
        for key in child_keys:
            value = sentence.get(key)
            if isinstance(value, list):
                children = value
                break
        if children is not None:
            flattened.extend((item, "word") for item in children if isinstance(item, dict))
            continue
        if sentence.get("word") or sentence.get("content") or sentence.get("text"):
            flattened.append((sentence, "word"))
        elif sentence.get("sentence"):
            flattened.append((sentence, "sentence"))
    return flattened


def _bounded_provider_result(result: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return {"retained": False, "reason": "not_json_serializable"}
    if len(encoded) <= 1024 * 1024:
        return result
    return {
        "retained": False,
        "reason": "provider_result_exceeds_1mb",
        "byte_size": len(encoded),
        "top_level_fields": sorted(str(key)[:80] for key in result)[:100],
    }


def _score(value: Any, scale: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(min(100, max(0, float(value) / max(scale, 0.0001) * 100)), 2)


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _duration(value: Any) -> float | None:
    try:
        return round(max(0, float(value)), 3) if value is not None else None
    except (TypeError, ValueError):
        return None


def _tone_description(value: str) -> str:
    match = _TONE_RE.search(value or "")
    return {
        "1": "第一声",
        "2": "第二声",
        "3": "第三声",
        "4": "第四声",
        "5": "轻声",
    }.get(match.group(1) if match else "", "未返回明确声调")


def _read_issue(value: int | None, core: str = "para") -> tuple[str | None, str]:
    if core in {"para", "sent"}:
        return {
            1: ("word_inserted", "存在增读，请按广播词原文朗读。"),
            2: ("word_omitted", "存在漏读，请对照广播词重新练习。"),
        }.get(value, (None, ""))
    return {
        1: ("word_inserted", "存在增读，请按广播词原文朗读。"),
        3: ("word_repeated", "存在回读，请保持连贯。"),
        4: ("word_replaced", "存在错读，请注意该词发音。"),
    }.get(value, (None, ""))
