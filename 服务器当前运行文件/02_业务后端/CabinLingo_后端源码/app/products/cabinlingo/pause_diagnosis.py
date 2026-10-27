from __future__ import annotations

from typing import Any


INTERNAL_PAUSE_CANDIDATE_MS = 1_200
INTERNAL_PAUSE_CONFIRMED_MS = 2_000
LEADING_SILENCE_CONFIRMED_MS = 2_000
TRAILING_SILENCE_CONFIRMED_MS = 2_500
VAD_MERGE_GAP_MS = 250


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _milliseconds(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0:
        return None
    return int(round(number))


def _normalized_vad_segments(value: Any) -> list[dict[str, int]]:
    segments: list[dict[str, int]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        start_ms = _milliseconds(item.get("start_ms"))
        end_ms = _milliseconds(item.get("end_ms"))
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            continue
        segments.append({"start_ms": start_ms, "end_ms": end_ms})
    segments.sort(key=lambda item: (item["start_ms"], item["end_ms"]))

    merged: list[dict[str, int]] = []
    for segment in segments:
        if not merged or segment["start_ms"] - merged[-1]["end_ms"] > VAD_MERGE_GAP_MS:
            merged.append(dict(segment))
            continue
        merged[-1]["end_ms"] = max(merged[-1]["end_ms"], segment["end_ms"])
    return merged


def _granular_words(value: Any) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) else []
    words = [
        dict(item) for item in source if isinstance(item, dict)
        and item.get("detail_level") != "sentence"
        and item.get("char_type") != 1
        and str(item.get("word") or "").strip()
        and _milliseconds(item.get("start_ms")) is not None
        and _milliseconds(item.get("end_ms")) is not None
    ]
    words.sort(key=lambda item: (_milliseconds(item.get("start_ms")) or 0, _milliseconds(item.get("end_ms")) or 0))
    return words


def _timed_iat_tokens(value: Any) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) else []
    tokens = [
        dict(item) for item in source if isinstance(item, dict)
        and str(item.get("text") or "").strip()
        and _milliseconds(item.get("start_ms")) is not None
    ]
    tokens.sort(key=lambda item: _milliseconds(item.get("start_ms")) or 0)
    return tokens


def _surrounding_words(
    words: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    previous = None
    following = None
    for word in words:
        word_start = _milliseconds(word.get("start_ms"))
        word_end = _milliseconds(word.get("end_ms"))
        if word_start is None or word_end is None:
            continue
        if word_end <= start_ms + 300:
            previous = word
        if following is None and word_start >= end_ms - 300:
            following = word
    return previous, following


def _fluency_evidence(fluency_score: Any) -> list[dict[str, Any]]:
    score = _number(fluency_score)
    if score is None or score >= 80:
        return []
    return [{
        "kind": "suntone_fluency_score",
        "value": round(score, 2),
        "message": "Suntone 流畅度低于 80 分，与停顿时间证据相互支持。",
    }]


def _word_timing_evidence(
    previous: dict[str, Any] | None,
    following: dict[str, Any] | None,
    minimum_gap_ms: int,
) -> list[dict[str, Any]]:
    if previous is None or following is None:
        return []
    previous_end = _milliseconds(previous.get("end_ms"))
    following_start = _milliseconds(following.get("start_ms"))
    if previous_end is None or following_start is None:
        return []
    provider_gap_ms = following_start - previous_end
    if provider_gap_ms < max(minimum_gap_ms - 400, INTERNAL_PAUSE_CANDIDATE_MS):
        return []
    return [{
        "kind": "suntone_word_timing_gap",
        "value": provider_gap_ms,
        "previous_word": previous.get("word"),
        "following_word": following.get("word"),
        "message": f"Suntone 字词时间轴在「{previous.get('word')}」与「{following.get('word')}」之间也记录到明显间隔。",
    }]


def _iat_following_word_evidence(
    tokens: list[dict[str, Any]],
    following_word: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if following_word is None:
        return []
    following_start = _milliseconds(following_word.get("start_ms"))
    if following_start is None:
        return []
    closest = min(
        tokens,
        key=lambda item: abs((_milliseconds(item.get("start_ms")) or 0) - following_start),
        default=None,
    )
    token_start = _milliseconds(closest.get("start_ms")) if closest else None
    if token_start is None or abs(token_start - following_start) > 700:
        return []
    return [{
        "kind": "iat_word_start_timing",
        "value": token_start,
        "word": closest.get("text"),
        "message": f"IAT 词语时间在 {token_start / 1000:.1f} 秒恢复识别，与 Suntone 下一字词位置一致。",
    }]


def _pause_issue(
    *,
    issue_type: str,
    start_ms: int,
    end_ms: int,
    expected: str,
    confirmed: bool,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    duration_ms = max(end_ms - start_ms, 0)
    seconds = duration_ms / 1_000
    labels = {
        "long_pause": "长时间停顿",
        "leading_silence": "开头等待过长",
        "trailing_silence": "结尾空白过长",
    }
    label = labels[issue_type]
    return {
        "dimension": "fluency",
        "source": "iat_vad_analysis",
        "provider": "xfyun",
        "type": issue_type,
        "issue_status": "confirmed" if confirmed else "pending_review",
        "severity": "warning" if confirmed else "info",
        "word": expected,
        "expected": expected,
        "actual": f"停顿 {seconds:.1f} 秒",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": duration_ms,
        "question": "当前广播词",
        "evidence": evidence,
        "training_advice": (
            "从停顿前一句开始连续跟读，按意群换气，避免在词组中间中断。"
            if issue_type == "long_pause"
            else "录音前先准备好广播词，开始后保持自然衔接。"
            if issue_type == "leading_silence"
            else "读完后及时结束录音，避免保留过长空白。"
        ),
        "message": (
            f"检测到{label} {seconds:.1f} 秒，已定位到本次录音。"
            if confirmed
            else f"检测到疑似{label} {seconds:.1f} 秒，证据不足，已进入教员复核。"
        ),
    }


def diagnose_pause_patterns(
    vad_segments: list[dict[str, Any]] | None,
    *,
    iat_tokens: list[dict[str, Any]] | None = None,
    word_details: list[dict[str, Any]] | None = None,
    duration_seconds: float | int | None = None,
    fluency_score: float | int | None = None,
) -> dict[str, Any]:
    """Turn IAT VAD timing into auditable fluency findings.

    A learner-visible finding requires IAT VAD timing plus independent Suntone
    word timing or a low Suntone fluency score.  Single-source gaps remain in
    the instructor review queue.
    """
    segments = _normalized_vad_segments(vad_segments)
    words = _granular_words(word_details or [])
    tokens = _timed_iat_tokens(iat_tokens or [])
    confirmed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def add(issue: dict[str, Any]) -> None:
        (confirmed if issue["issue_status"] == "confirmed" else pending).append(issue)

    first_start = segments[0]["start_ms"] if segments else 0
    if segments and first_start >= LEADING_SILENCE_CONFIRMED_MS:
        first_word = words[0] if words else None
        evidence: list[dict[str, Any]] = [{
            "kind": "iat_vad_leading_silence",
            "value": first_start,
            "message": f"IAT VAD 在录音开始后 {first_start / 1000:.1f} 秒才检测到语音。",
        }]
        if first_word and (_milliseconds(first_word.get("start_ms")) or 0) >= LEADING_SILENCE_CONFIRMED_MS - 400:
            evidence.append({
                "kind": "suntone_first_word_timing",
                "value": _milliseconds(first_word.get("start_ms")),
                "message": "Suntone 首个字词时间也显示录音开始后存在等待。",
            })
        evidence.extend(_fluency_evidence(fluency_score))
        add(_pause_issue(
            issue_type="leading_silence",
            start_ms=0,
            end_ms=first_start,
            expected=str(first_word.get("word") or "开始朗读") if first_word else "开始朗读",
            confirmed=len({item["kind"] for item in evidence}) >= 2,
            evidence=evidence,
        ))

    internal_gaps: list[int] = []
    analyzed_ranges: list[tuple[int, int]] = []
    for previous_segment, following_segment in zip(segments, segments[1:]):
        start_ms = previous_segment["end_ms"]
        end_ms = following_segment["start_ms"]
        duration_ms = end_ms - start_ms
        if duration_ms < INTERNAL_PAUSE_CANDIDATE_MS:
            continue
        internal_gaps.append(duration_ms)
        analyzed_ranges.append((start_ms, end_ms))
        previous_word, following_word = _surrounding_words(words, start_ms, end_ms)
        expected = " → ".join(
            str(item.get("word")) for item in (previous_word, following_word) if item is not None
        ) or "句中连接处"
        evidence = [{
            "kind": "iat_vad_gap",
            "value": duration_ms,
            "message": f"IAT VAD 检测到连续 {duration_ms / 1000:.1f} 秒无有效语音。",
        }]
        evidence.extend(_word_timing_evidence(previous_word, following_word, duration_ms))
        evidence.extend(_fluency_evidence(fluency_score))
        corroborated = len({item["kind"] for item in evidence}) >= 2
        add(_pause_issue(
            issue_type="long_pause",
            start_ms=start_ms,
            end_ms=end_ms,
            expected=expected,
            confirmed=duration_ms >= INTERNAL_PAUSE_CONFIRMED_MS and corroborated,
            evidence=evidence,
        ))

    # IAT can occasionally return one broad VAD range for a whole sentence.
    # In that case, use Suntone's exact adjacent-word gap as the candidate and
    # require the IAT next-word timestamp as independent corroboration.
    for previous_word, following_word in zip(words, words[1:]):
        start_ms = _milliseconds(previous_word.get("end_ms"))
        end_ms = _milliseconds(following_word.get("start_ms"))
        if start_ms is None or end_ms is None:
            continue
        duration_ms = end_ms - start_ms
        if duration_ms < INTERNAL_PAUSE_CANDIDATE_MS:
            continue
        if any(max(start_ms, known_start) < min(end_ms, known_end) for known_start, known_end in analyzed_ranges):
            continue
        internal_gaps.append(duration_ms)
        evidence = _word_timing_evidence(previous_word, following_word, duration_ms)
        evidence.extend(_iat_following_word_evidence(tokens, following_word))
        evidence.extend(_fluency_evidence(fluency_score))
        add(_pause_issue(
            issue_type="long_pause",
            start_ms=start_ms,
            end_ms=end_ms,
            expected=f"{previous_word.get('word')} → {following_word.get('word')}",
            confirmed=(
                duration_ms >= INTERNAL_PAUSE_CONFIRMED_MS
                and len({item["kind"] for item in evidence}) >= 2
            ),
            evidence=evidence,
        ))

    total_ms = int(round(float(duration_seconds) * 1_000)) if _number(duration_seconds) is not None else None
    last_end = segments[-1]["end_ms"] if segments else 0
    if segments and total_ms is not None and total_ms > last_end:
        trailing_ms = total_ms - last_end
        if trailing_ms >= TRAILING_SILENCE_CONFIRMED_MS:
            last_word = words[-1] if words else None
            evidence = [{
                "kind": "iat_vad_trailing_silence",
                "value": trailing_ms,
                "message": f"IAT VAD 检测到朗读结束后保留 {trailing_ms / 1000:.1f} 秒空白。",
            }]
            last_word_end = _milliseconds(last_word.get("end_ms")) if last_word else None
            if last_word_end is not None and last_word_end <= last_end + 400:
                evidence.append({
                    "kind": "suntone_last_word_timing",
                    "value": last_word_end,
                    "message": "Suntone 末词时间与 IAT 检测到的语音结束位置一致。",
                })
            evidence.extend(_fluency_evidence(fluency_score))
            add(_pause_issue(
                issue_type="trailing_silence",
                start_ms=last_end,
                end_ms=total_ms,
                expected=str(last_word.get("word") or "朗读结束") if last_word else "朗读结束",
                confirmed=len({item["kind"] for item in evidence}) >= 2,
                evidence=evidence,
            ))

    return {
        "confirmed_issues": confirmed,
        "pending_review_issues": pending,
        "metrics": {
            "vad_segment_count": len(segments),
            "longest_internal_pause_ms": max(internal_gaps, default=0),
            "internal_pause_count": len(internal_gaps),
        },
        "thresholds": _thresholds(),
    }


def _thresholds() -> dict[str, int]:
    return {
        "internal_candidate_ms": INTERNAL_PAUSE_CANDIDATE_MS,
        "internal_confirmed_ms": INTERNAL_PAUSE_CONFIRMED_MS,
        "leading_silence_ms": LEADING_SILENCE_CONFIRMED_MS,
        "trailing_silence_ms": TRAILING_SILENCE_CONFIRMED_MS,
        "vad_merge_gap_ms": VAD_MERGE_GAP_MS,
    }
