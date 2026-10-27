from __future__ import annotations

from hashlib import sha256
import io
import re
import wave
from typing import Any

from ...integrations.ai_gateway import AudioBlob
from ...integrations.audio_transcoder import AudioTranscodeError, normalize_speech_audio
from .text_alignment import align_text, tokenize_text


class CourseAudioAlignmentError(RuntimeError):
    pass


def annotation_segments(source: str) -> list[str]:
    """Return the same clickable units as the learner course page."""
    clean = (
        str(source or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    clean = re.sub(r"\[[^\]\n]+\][ \t]*", "", clean)
    clean = re.sub(r"[↘↗↙↖↓↑→←⌒‿]+", "", clean)
    segments: list[str] = []
    for line in re.split(r"(\n+)", clean):
        if not line or re.fullmatch(r"\n+", line):
            continue
        cursor = 0
        for match in re.finditer(r"/{2,3}", line):
            end = match.end()
            part = line[cursor:end]
            if part.strip():
                segments.append(part)
            cursor = end
        tail = line[cursor:]
        if tail.strip():
            segments.append(tail)
    return segments


def spoken_segment(value: str) -> str:
    value = re.sub(r"[【】＿_]", "", value)
    return re.sub(r"/{1,3}", " ", value).strip()


def alignment_fingerprint(source: str, language: str) -> str:
    normalized = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    return sha256(f"v1\0{language}\0{normalized}".encode("utf-8")).hexdigest()


def cached_alignment_is_current(cached: Any, source: str, language: str) -> bool:
    return (
        isinstance(cached, dict)
        and cached.get("status") == "ready"
        and cached.get("source_hash") == alignment_fingerprint(source, language)
        and isinstance(cached.get("sentences"), list)
        and len(cached["sentences"]) == len(annotation_segments(source))
    )


def _duration_ms(wav_data: bytes) -> int:
    with wave.open(io.BytesIO(wav_data), "rb") as audio:
        return round(audio.getnframes() / audio.getframerate() * 1000)


def _sentence_token_ranges(segments: list[str]) -> tuple[str, list[tuple[int, int]]]:
    spoken = [spoken_segment(segment) for segment in segments]
    ranges: list[tuple[int, int]] = []
    offset = 0
    for sentence in spoken:
        count = len(tokenize_text(sentence))
        ranges.append((offset, offset + count))
        offset += count
    return "\n".join(spoken), ranges


def _sentence_timings(
    ranges: list[tuple[int, int]],
    alignment: list[dict[str, Any]],
    duration_ms: int,
) -> list[dict[str, Any]]:
    timed_by_reference = {
        int(item["reference_index"]): int(item["start_ms"])
        for item in alignment
        if isinstance(item, dict)
        and isinstance(item.get("reference_index"), int)
        and not isinstance(item.get("reference_index"), bool)
        and isinstance(item.get("start_ms"), int)
        and not isinstance(item.get("start_ms"), bool)
    }
    starts: list[int | None] = []
    direct: list[bool] = []
    for first, last in ranges:
        candidates = [timed_by_reference[index] for index in range(first, last) if index in timed_by_reference]
        starts.append(min(candidates) if candidates else None)
        direct.append(bool(candidates))

    # Missing provider boundaries are rare. Interpolate only between the nearest
    # real boundaries so one missed token does not discard the whole audio map.
    weights = [max(1, last - first) for first, last in ranges]
    for index, value in enumerate(starts):
        if value is not None:
            continue
        previous = next((cursor for cursor in range(index - 1, -1, -1) if starts[cursor] is not None), None)
        following = next((cursor for cursor in range(index + 1, len(starts)) if starts[cursor] is not None), None)
        left_ms = int(starts[previous]) if previous is not None else 0
        right_ms = int(starts[following]) if following is not None else duration_ms
        left_index = previous if previous is not None else 0
        right_index = following if following is not None else len(starts)
        span_weights = weights[left_index:right_index]
        before_weight = sum(weights[left_index:index])
        starts[index] = left_ms + round((right_ms - left_ms) * before_weight / max(1, sum(span_weights)))

    safe_starts: list[int] = []
    for index, value in enumerate(starts):
        floor = safe_starts[-1] if safe_starts else 0
        safe_starts.append(max(floor, min(duration_ms, int(value or 0))))

    result: list[dict[str, Any]] = []
    for index, start_ms in enumerate(safe_starts):
        end_ms = safe_starts[index + 1] if index + 1 < len(safe_starts) else duration_ms
        result.append({
            "index": index,
            "start_ms": start_ms,
            "end_ms": max(start_ms + 1, min(duration_ms, end_ms)),
            "precision": "aligned" if direct[index] else "interpolated",
        })
    return result


def build_course_audio_alignment(
    *,
    source: str,
    language: str,
    blob: AudioBlob,
    effective_settings: Any,
) -> dict[str, Any]:
    segments = annotation_segments(source)
    if not segments:
        raise CourseAudioAlignmentError("annotation_empty")
    reference_text, ranges = _sentence_token_ranges(segments)
    if not any(last > first for first, last in ranges):
        raise CourseAudioAlignmentError("annotation_has_no_spoken_text")
    try:
        normalized = normalize_speech_audio(
            blob.data,
            blob.content_type,
            ffmpeg_binary=getattr(effective_settings, "audio_transcode_binary", "ffmpeg"),
            timeout_seconds=getattr(effective_settings, "audio_transcode_timeout_seconds", 30),
            max_seconds=getattr(effective_settings, "audio_transcode_max_seconds", 300),
            max_input_bytes=getattr(effective_settings, "audio_max_bytes", 25 * 1024 * 1024),
        )
    except AudioTranscodeError as exc:
        raise CourseAudioAlignmentError(exc.code) from exc

    prepared = AudioBlob(normalized.data, normalized.content_type, "course-standard.wav")
    from ...integrations.runtime import build_ai_gateway
    gateway = build_ai_gateway(effective_settings, lambda _audio_ref: prepared)
    results = gateway.analyze(
        reference_text=reference_text,
        audio_ref="course-standard-alignment",
        requested_adapters=["asr_iat"],
    )
    result = results[0] if results else None
    if result is None or result.status != "completed":
        raise CourseAudioAlignmentError(result.error_code if result else "alignment_unavailable")
    transcript = str(result.payload.get("transcript") or "")
    tokens = result.payload.get("tokens") if isinstance(result.payload.get("tokens"), list) else []
    aligned = align_text(reference_text, transcript, tokens)
    duration_ms = _duration_ms(normalized.data)
    sentences = _sentence_timings(ranges, aligned, duration_ms)
    if not sentences or not any(item["precision"] == "aligned" for item in sentences):
        raise CourseAudioAlignmentError("alignment_has_no_timestamps")
    return {
        "version": 1,
        "status": "ready",
        "source_hash": alignment_fingerprint(source, language),
        "provider": result.provider,
        "duration_ms": duration_ms,
        "sentence_count": len(sentences),
        "sentences": sentences,
    }
