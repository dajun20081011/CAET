"""Prosody parsing, pronunciation injection and deterministic WAV post-processing."""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from array import array
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from ...integrations.pronunciation import (
    normalize_pronunciation_text,
    provider_pronunciations,
    resolve_pronunciations,
)


logger = logging.getLogger("uvicorn.error")

PAUSE_MAP = {"/": 200, "//": 400, "///": 700}
PACE_RATE = {"稍慢": 0.90, "中速": 1.00, "稍快": 1.10}
TONE_TAGS = {"亲切", "平稳", "提醒", "关切", "严肃", "紧迫", "明确"}
INTONATION_MAP = {"↑": "rise", "↓": "fall", "→": "level"}
INTONATION_CN = {"rise": "句尾自然上扬", "fall": "句尾自然下降并收束", "level": "句尾保持平稳"}
OPENING_RE = re.compile(r"^\s*女士们\s*[、，,]?\s*先生们\s*[：:，,。！？!?]?\s*")
CLOSING_RE = re.compile(r"\s*谢谢\s*[。！!]?\s*$")


class ProsodyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProsodySegment:
    source: str
    text: str
    tone: str | None
    pace: str | None
    emphasis: list[str]
    intonation: str | None
    pause_after_ms: int


@dataclass(frozen=True)
class VoiceProfile:
    opening_speed_ratio: float = 0.88
    opening_inner_pause_ms: int = 300
    opening_after_pause_ms: int = 500
    closing_speed_ratio: float = 0.85
    closing_after_pause_ms: int = 500


@dataclass(frozen=True)
class BroadcastPart:
    role: str
    segment: ProsodySegment
    pause_after_ms: int


DEFAULT_VOICE_PROFILE = VoiceProfile()


def _strip_end_controls(line: str) -> tuple[str, str | None, int]:
    line, intonation, pause_after_ms = line.rstrip(), None, 0
    changed = True
    while changed:
        changed = False
        line = line.rstrip()
        if line and line[-1] in INTONATION_MAP and intonation is None:
            intonation, line, changed = INTONATION_MAP[line[-1]], line[:-1], True
            continue
        match = re.search(r"(///|//|/)\s*$", line)
        if match and pause_after_ms == 0:
            pause_after_ms, line, changed = PAUSE_MAP[match.group(1)], line[:match.start()], True
    return line.rstrip(), intonation, pause_after_ms


def parse_line(raw_line: str) -> ProsodySegment | None:
    source, line = raw_line.rstrip("\n"), raw_line.strip()
    if not line:
        return None
    tags: list[str] = []
    while match := re.match(r"^\[([^\]]+)\]\s*", line):
        tags.append(match.group(1).strip())
        line = line[match.end():]
    unknown = [tag for tag in tags if tag not in TONE_TAGS and tag not in PACE_RATE]
    if unknown:
        raise ProsodyError(f"不支持的播音标签：{', '.join(unknown)}")
    line, intonation, pause_after_ms = _strip_end_controls(line)
    emphasis = [item.strip() for item in re.findall(r"【([^【】]+)】", line) if item.strip()]
    clean_text = re.sub(r"【([^【】]+)】", r"\1", line).strip()
    if "【" in clean_text or "】" in clean_text:
        raise ProsodyError(f"重音标记未成对：{source}")
    if not clean_text:
        raise ProsodyError(f"标注行没有可合成文本：{source}")
    return ProsodySegment(
        source=source,
        text=clean_text,
        tone=next((tag for tag in tags if tag in TONE_TAGS), None),
        pace=next((tag for tag in tags if tag in PACE_RATE), None),
        emphasis=emphasis,
        intonation=intonation,
        pause_after_ms=pause_after_ms,
    )


def parse_script(script: str) -> list[ProsodySegment]:
    segments: list[ProsodySegment] = []
    for line_no, line in enumerate(script.splitlines(), start=1):
        try:
            item = parse_line(line)
        except ProsodyError as exc:
            raise ProsodyError(f"第 {line_no} 行：{exc}") from exc
        if item:
            segments.append(item)
    if not segments:
        raise ProsodyError("没有检测到可合成的播音文本")
    return segments


def build_instruction(segment: ProsodySegment, language: str = "zh") -> str:
    if language != "zh":
        parts = ["Read as a professional airline cabin announcement. Keep the delivery natural, clear, and controlled."]
        parts.append({"稍慢": "Use a slightly slower pace.", "稍快": "Use a slightly faster pace."}.get(segment.pace, "Use a medium pace."))
        if segment.emphasis:
            parts.append("Naturally emphasize: " + ", ".join(segment.emphasis) + ".")
        if segment.intonation:
            parts.append({"rise": "Use a natural rising intonation at the end.", "fall": "Use a natural falling intonation at the end.", "level": "Keep the ending level and steady."}[segment.intonation])
        return " ".join(parts)
    tone = {
        "亲切": "语气亲切自然、有服务感", "平稳": "语气平稳、清楚、克制", "提醒": "语气明确，起到自然提醒作用，不生硬",
        "关切": "语气体现关切和专业感，不煽情", "严肃": "语气严肃、明确，但保持专业克制", "紧迫": "体现适度紧迫感，但不得喊叫、慌张或戏剧化",
        "明确": "表达明确、指向清楚，重点信息易被旅客识别",
    }.get(segment.tone, "保持专业、清晰、自然、克制")
    pace = {"稍慢": "本句语速稍慢，给重要信息留出理解时间", "中速": "本句保持自然的中等语速", "稍快": "本句语速稍快但保持清晰，不要赶读"}.get(segment.pace, "保持自然中等语速")
    parts = ["使用专业民航客舱乘务员的广播方式进行播报。", "避免新闻播音腔、朗诵腔和逐字平均用力。", tone + "。", pace + "。"]
    if segment.emphasis:
        parts.append(f"自然突出{'、'.join(f'“{item}”' for item in segment.emphasis)}，通过语义重音体现重点，不要喊叫或刻意拖长。")
    if segment.intonation:
        parts.append(INTONATION_CN[segment.intonation] + "。")
    parts.append("保持自然呼吸感和连贯的意群表达。")
    return "".join(parts)


def preview_script(script: str, language: str = "zh") -> dict[str, Any]:
    segments = parse_script(script)
    items = []
    for index, segment in enumerate(segments, start=1):
        row = asdict(segment)
        row.update(index=index, instruction=build_instruction(segment, language))
        items.append(row)
    return {
        "segments": items,
        "summary": {
            "segment_count": len(segments),
            "emphasis_count": sum(len(item.emphasis) for item in segments),
            "pause_count": sum(item.pause_after_ms > 0 for item in segments),
            "tone_count": sum(bool(item.tone) for item in segments),
            "pace_count": sum(bool(item.pace) for item in segments),
            "intonation_count": sum(bool(item.intonation) for item in segments),
        },
    }


def _bounded_ratio(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if 0.80 <= parsed <= 1.00 else default


def _bounded_pause(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if 0 <= parsed <= 3000 else default


def resolve_voice_profile(settings: Any, voice: str) -> VoiceProfile:
    raw = getattr(settings, "qwen_tts_voice_profiles", "") or ""
    if not raw:
        return DEFAULT_VOICE_PROFILE
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict):
            raise ValueError("voice profiles must be an object")
        merged: dict[str, Any] = {}
        for key in ("default", voice):
            item = payload.get(key)
            if isinstance(item, dict):
                merged.update(item)
        return VoiceProfile(
            opening_speed_ratio=_bounded_ratio(merged.get("opening_speed_ratio"), DEFAULT_VOICE_PROFILE.opening_speed_ratio),
            opening_inner_pause_ms=_bounded_pause(merged.get("opening_inner_pause_ms"), DEFAULT_VOICE_PROFILE.opening_inner_pause_ms),
            opening_after_pause_ms=_bounded_pause(merged.get("opening_after_pause_ms"), DEFAULT_VOICE_PROFILE.opening_after_pause_ms),
            closing_speed_ratio=_bounded_ratio(merged.get("closing_speed_ratio"), DEFAULT_VOICE_PROFILE.closing_speed_ratio),
            closing_after_pause_ms=_bounded_pause(merged.get("closing_after_pause_ms"), DEFAULT_VOICE_PROFILE.closing_after_pause_ms),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("invalid_qwen_tts_voice_profiles voice=%s error=%s", voice, exc)
        return DEFAULT_VOICE_PROFILE


def split_broadcast_parts(segments: list[ProsodySegment], language: str, profile: VoiceProfile) -> list[BroadcastPart]:
    if language != "zh":
        return [BroadcastPart("body", item, item.pause_after_ms) for item in segments]
    parts: list[BroadcastPart] = []
    for index, original in enumerate(segments):
        text = original.text
        opening: ProsodySegment | None = None
        if index == 0 and (match := OPENING_RE.match(text)):
            opening = replace(original, text="女士们，先生们。", emphasis=[], pace="中速", intonation=None, pause_after_ms=0)
            text = text[match.end():].strip()
        closing: ProsodySegment | None = None
        if index == len(segments) - 1 and (match := CLOSING_RE.search(text)):
            closing = replace(original, text="谢谢。", emphasis=[], pace="中速", intonation="fall", pause_after_ms=0)
            text = text[:match.start()].strip()
        if opening:
            opening_pause = profile.opening_after_pause_ms
            if not text and not closing:
                opening_pause = max(opening_pause, original.pause_after_ms)
            parts.append(BroadcastPart("opening", opening, opening_pause))
        if text:
            parts.append(BroadcastPart("body", replace(original, text=text, pause_after_ms=0), original.pause_after_ms if not closing else 0))
        if closing:
            parts.append(BroadcastPart("closing", closing, max(profile.closing_after_pause_ms, original.pause_after_ms)))
    return parts


def _endpoint(settings: Any) -> str:
    workspace_id = str(getattr(settings, "qwen_tts_workspace_id", "") or "").strip()
    if workspace_id:
        return f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
    return str(settings.qwen_tts_endpoint)


def _post_json(url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise ProsodyError(f"Qwen TTS HTTP {exc.code}: {detail[:1200]}") from exc
    except Exception as exc:
        raise ProsodyError(f"Qwen TTS 请求失败：{exc!r}") from exc


def _download(url: str, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        raise ProsodyError(f"下载 Qwen 音频失败：{exc!r}") from exc


def _pronunciation_audit(raw_text: str, normalized_text: str, hits: list[Any], payload: dict[str, Any]) -> None:
    logger.info("tts_pronunciation_audit=%s", json.dumps({
        "raw_text": raw_text,
        "normalized_text": normalized_text,
        "pronunciation_hits": [f"{item.phrase} -> {item.pinyin}" for item in hits],
        "final_tts_payload": payload,
    }, ensure_ascii=False, separators=(",", ":")))


def synthesize_segment(settings: Any, *, segment: ProsodySegment, voice: str, language: str,
                       base_rate: float = 1.0, pronunciation_entries: Iterable[dict[str, Any]] = ()) -> tuple[bytes, int]:
    if not getattr(settings, "qwen_tts_enabled", False):
        raise ProsodyError("Qwen TTS 当前未启用")
    if not settings.qwen_tts_api_key:
        raise ProsodyError("Qwen TTS API Key 未配置")
    normalized_text = normalize_pronunciation_text(segment.text)
    hits = resolve_pronunciations(normalized_text, pronunciation_entries) if language == "zh" else []
    hot_fixes = provider_pronunciations(normalized_text, [item.as_dict() for item in hits]) if hits else []
    rate = max(0.5, min(2.0, float(base_rate) * PACE_RATE.get(segment.pace, 1.0)))
    input_payload: dict[str, Any] = {
        "text": normalized_text,
        "voice": voice,
        "format": "wav",
        "sample_rate": 24000,
        "rate": rate,
        "language_hints": [language],
        "instruction": build_instruction(segment, language),
    }
    if hot_fixes:
        input_payload["hot_fix"] = {"pronunciation": hot_fixes}
    payload = {"model": str(settings.qwen_tts_model), "input": input_payload}
    _pronunciation_audit(segment.source, normalized_text, hits, payload)
    timeout = float(getattr(settings, "qwen_tts_timeout_seconds", 90))
    data = _post_json(_endpoint(settings), str(settings.qwen_tts_api_key), payload, timeout)
    output = data.get("output") or {}
    audio = output.get("audio") if isinstance(output, dict) else None
    url = audio.get("url") if isinstance(audio, dict) else output.get("audio_url") or output.get("url")
    if not url:
        raise ProsodyError("Qwen TTS 未返回音频 URL")
    return _download(str(url), timeout), len(hot_fixes)


def _read_wav(blob: bytes) -> tuple[tuple[int, int, int, str, str], bytes]:
    try:
        with wave.open(io.BytesIO(blob), "rb") as audio:
            params = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype(), audio.getcompname())
            return params, audio.readframes(audio.getnframes())
    except Exception as exc:
        raise ProsodyError(f"WAV 音频无法解析：{exc!r}") from exc


def _crossfade_pcm16(left: bytes, right: bytes, sample_count: int) -> bytes:
    left_samples, right_samples = array("h"), array("h")
    left_samples.frombytes(left)
    right_samples.frombytes(right)
    if sys.byteorder == "big":
        left_samples.byteswap()
        right_samples.byteswap()
    mixed = array("h")
    for index in range(sample_count):
        alpha = (index + 1) / (sample_count + 1)
        value = round(left_samples[index] * (1.0 - alpha) + right_samples[index] * alpha)
        mixed.append(max(-32768, min(32767, value)))
    if sys.byteorder == "big":
        mixed.byteswap()
    return mixed.tobytes()


def _edge_silence_ms(blob: bytes, *, leading: bool, threshold_db: float = -45.0) -> int:
    params, frames = _read_wav(blob)
    channels, sample_width, frame_rate, compression, _ = params
    if sample_width != 2 or compression != "NONE" or not frames:
        return 0
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    window_frames = max(1, frame_rate // 100)
    window_samples = window_frames * channels
    threshold = 32767.0 * (10.0 ** (threshold_db / 20.0))
    indexes = range(0, len(samples), window_samples)
    if not leading:
        indexes = range(max(0, len(samples) - window_samples), -1, -window_samples)
    silent_frames = 0
    for start in indexes:
        block = samples[start:start + window_samples]
        if not block:
            continue
        rms = (sum(int(value) * int(value) for value in block) / len(block)) ** 0.5
        if rms > threshold:
            break
        silent_frames += len(block) // channels
    return round(silent_frames * 1000 / frame_rate)


def _top_up_pause_parts(parts: list[tuple[bytes, int]], *, measurement_margin_ms: int = 0) -> list[tuple[bytes, int]]:
    adjusted: list[tuple[bytes, int]] = []
    for index, (blob, target_pause_ms) in enumerate(parts):
        if target_pause_ms <= 0:
            adjusted.append((blob, 0))
            continue
        natural_ms = _edge_silence_ms(blob, leading=False)
        if index + 1 < len(parts):
            natural_ms += _edge_silence_ms(parts[index + 1][0], leading=True)
        adjusted.append((blob, max(0, target_pause_ms + measurement_margin_ms - natural_ms)))
    return adjusted


def combine_wavs(parts: list[tuple[bytes, int]], *, crossfade_ms: int = 0) -> bytes:
    if not parts:
        raise ProsodyError("没有可拼接的音频片段")
    base_params: tuple[int, int, int, str, str] | None = None
    combined = bytearray()
    previous_pause_ms = 0
    for part_index, (blob, pause_ms) in enumerate(parts):
        params, frames = _read_wav(blob)
        if base_params is None:
            base_params = params
        elif params != base_params:
            raise ProsodyError(f"音频片段参数不一致：{params} != {base_params}")
        channels, sample_width, frame_rate, compression, _ = params
        if compression != "NONE":
            raise ProsodyError("暂不支持压缩 WAV 的静音拼接")
        if part_index and previous_pause_ms == 0 and crossfade_ms > 0 and sample_width == 2:
            fade_frames = min(int(frame_rate * crossfade_ms / 1000), len(combined) // (channels * sample_width), len(frames) // (channels * sample_width))
            fade_samples = fade_frames * channels
            fade_bytes = fade_samples * sample_width
            if fade_bytes:
                combined[-fade_bytes:] = _crossfade_pcm16(bytes(combined[-fade_bytes:]), frames[:fade_bytes], fade_samples)
                frames = frames[fade_bytes:]
        combined.extend(frames)
        if pause_ms:
            combined.extend(b"\x00" * int(frame_rate * pause_ms / 1000) * channels * sample_width)
        previous_pause_ms = pause_ms
    assert base_params is not None
    channels, sample_width, frame_rate, compression, compression_name = base_params
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(sample_width)
        audio.setframerate(frame_rate)
        audio.setcomptype(compression, compression_name)
        audio.writeframes(bytes(combined))
    return output.getvalue()


def _run_ffmpeg_wav(settings: Any, blob: bytes, filters: list[str]) -> bytes:
    if not blob:
        raise ProsodyError("待处理音频为空")
    binary = str(getattr(settings, "audio_transcode_binary", "ffmpeg") or "ffmpeg")
    timeout = float(getattr(settings, "audio_transcode_timeout_seconds", 30))
    max_bytes = int(getattr(settings, "qwen_tts_max_audio_bytes", 25 * 1024 * 1024))
    with TemporaryDirectory(prefix="cabinlingo-prosody-") as directory:
        output_path = Path(directory) / "processed.wav"
        command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1", "-i", "pipe:0", "-map", "0:a:0", "-vn", "-sn", "-dn"]
        if filters:
            command.extend(["-filter:a", ",".join(filters)])
        command.extend(["-ac", "1", "-ar", "24000", "-sample_fmt", "s16", "-f", "wav", str(output_path)])
        try:
            completed = subprocess.run(command, input=blob, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ProsodyError("音频后处理超时") from exc
        except (FileNotFoundError, OSError) as exc:
            raise ProsodyError("服务器音频后处理工具不可用") from exc
        if completed.returncode != 0 or not output_path.is_file():
            detail = completed.stderr.decode(errors="replace")[-800:]
            raise ProsodyError(f"音频后处理失败：{detail}")
        output = output_path.read_bytes()
        if not output or len(output) > max_bytes:
            raise ProsodyError("音频后处理结果为空或超过大小限制")
        _read_wav(output)
        return output


def _synthesize_opening(settings: Any, segment: ProsodySegment, voice: str, language: str,
                        base_rate: float, entries: Iterable[dict[str, Any]], profile: VoiceProfile) -> tuple[bytes, int]:
    clips: list[tuple[bytes, int]] = []
    hit_count = 0
    for text, pause in (("女士们。", profile.opening_inner_pause_ms), ("先生们。", 0)):
        clip, hits = synthesize_segment(settings, segment=replace(segment, text=text), voice=voice, language=language, base_rate=base_rate, pronunciation_entries=entries)
        clip = _run_ffmpeg_wav(settings, clip, [f"atempo={profile.opening_speed_ratio:.6f}"])
        clips.append((clip, pause))
        hit_count += hits
    return combine_wavs(_top_up_pause_parts(clips, measurement_margin_ms=30)), hit_count


def _synthesize_closing(settings: Any, segment: ProsodySegment, voice: str, language: str,
                        base_rate: float, entries: Iterable[dict[str, Any]], profile: VoiceProfile) -> tuple[bytes, int]:
    clip, hits = synthesize_segment(settings, segment=segment, voice=voice, language=language, base_rate=base_rate, pronunciation_entries=entries)
    return _run_ffmpeg_wav(settings, clip, [f"atempo={profile.closing_speed_ratio:.6f}"]), hits


def synthesize_script(settings: Any, *, script: str, voice: str, language: str = "zh", base_rate: float = 1.0,
                      pronunciation_entries: Iterable[dict[str, Any]] = ()) -> tuple[bytes, dict[str, Any]]:
    segments = parse_script(script)
    profile = resolve_voice_profile(settings, voice)
    parts = split_broadcast_parts(segments, language, profile)
    # Prosody Studio generates one sentence per request and adds the sentence
    # pause later in /assemble. Avoid adding the opening boundary twice there.
    if len(segments) == 1 and len(parts) == 1 and parts[0].role == "opening":
        parts = [replace(parts[0], pause_after_ms=0)]
    entries = list(pronunciation_entries)
    audio_parts: list[tuple[bytes, int]] = []
    details: list[dict[str, Any]] = []
    total_hits = 0
    for index, part in enumerate(parts, start=1):
        if part.role == "opening":
            audio, hits = _synthesize_opening(settings, part.segment, voice, language, base_rate, entries, profile)
        elif part.role == "closing":
            audio, hits = _synthesize_closing(settings, part.segment, voice, language, base_rate, entries, profile)
        else:
            audio, hits = synthesize_segment(settings, segment=part.segment, voice=voice, language=language, base_rate=base_rate, pronunciation_entries=entries)
        total_hits += hits
        audio_parts.append((audio, part.pause_after_ms))
        row = asdict(part.segment)
        row.update(index=index, role=part.role, pause_after_ms=part.pause_after_ms, instruction=build_instruction(part.segment, language), audio_bytes=len(audio), pronunciation_hit_count=hits)
        details.append(row)
    adjusted_audio_parts = _top_up_pause_parts(audio_parts, measurement_margin_ms=30)
    for detail, (_, inserted_pause_ms) in zip(details, adjusted_audio_parts, strict=True):
        detail["inserted_pause_after_ms"] = inserted_pause_ms
    combined = combine_wavs(adjusted_audio_parts, crossfade_ms=30)
    combined = _run_ffmpeg_wav(settings, combined, ["loudnorm=I=-18:TP=-2:LRA=7"])
    summary = preview_script(script, language)["summary"]
    summary.update({
        "rendered_part_count": len(parts),
        "pronunciation_hit_count": total_hits,
        "opening_processed": any(item.role == "opening" for item in parts),
        "closing_processed": any(item.role == "closing" for item in parts),
        "voice_profile": asdict(profile),
        "crossfade_ms": 30,
        "loudness_target_lufs": -18,
    })
    return combined, {"segments": details, "summary": summary}
