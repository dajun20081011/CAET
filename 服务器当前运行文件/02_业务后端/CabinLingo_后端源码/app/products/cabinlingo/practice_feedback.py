from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .pause_diagnosis import diagnose_pause_patterns
from .text_diagnosis import analyze_common_phoneme_patterns, diagnose_text_recognition


_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+(?:[.:]\d+)?|[\u3400-\u9fff]")
_MAX_TRANSCRIPT_CHARS = 12_000


def learner_visible_issues(value: Any) -> list[dict[str, Any]]:
    """Expose only explicitly confirmed findings, including for legacy rows."""
    if not isinstance(value, list):
        return []
    return [
        dict(issue) for issue in value
        if isinstance(issue, dict) and issue.get("issue_status") == "confirmed"
    ][:300]


def instructor_review_issues(value: Any) -> list[dict[str, Any]]:
    """Keep legacy findings available to instructors without presenting them as fact."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw_issue in value[:300]:
        if not isinstance(raw_issue, dict):
            continue
        issue = dict(raw_issue)
        if issue.get("issue_status") not in {"confirmed", "pending_review"}:
            issue["original_message"] = issue.get("message")
            issue["issue_status"] = "pending_review"
            issue["filter_reason"] = "legacy_unclassified_result"
            issue["severity"] = "info"
            issue["message"] = "该历史识别结果未经过当前多证据规则，已进入教员复核，不在学员成绩中扣分。"
        result.append(issue)
    return result


def normalize_transcript(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized[:_MAX_TRANSCRIPT_CHARS] or None


def _tokens(value: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for match in _TOKEN_RE.finditer(value or ""):
        text = match.group(0)
        result.append({
            "text": text,
            "normalized": text.lower().replace("’", "'"),
            "start_char": match.start(),
            "end_char": match.end(),
        })
    return result


def _looks_like_reread(extra: list[str], expected: list[str], position: int) -> bool:
    if not extra:
        return False
    width = len(extra)
    if position >= width and expected[position - width:position] == extra:
        return True
    if expected[position:position + width] == extra:
        return True
    nearby_start = max(0, position - max(width, 4))
    nearby_end = min(len(expected), position + max(width, 4))
    nearby = expected[nearby_start:nearby_end]
    return any(nearby[offset:offset + width] == extra for offset in range(max(len(nearby) - width + 1, 0)))


def analyze_browser_transcript(reference_text: str, recognized_text: str | None) -> list[dict[str, Any]]:
    transcript = normalize_transcript(recognized_text)
    if not transcript:
        return []
    expected_tokens = _tokens(reference_text)
    actual_tokens = _tokens(transcript)
    if not expected_tokens or not actual_tokens:
        return []

    expected = [item["normalized"] for item in expected_tokens]
    actual = [item["normalized"] for item in actual_tokens]
    matcher = SequenceMatcher(a=expected, b=actual, autojunk=False)
    issues: list[dict[str, Any]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for reference_index in range(i1, i2):
                word = expected_tokens[reference_index]["text"]
                issues.append({
                    "dimension": "browser_speech",
                    "source": "browser_speech_alignment",
                    "type": "word_omitted",
                    "message": f"浏览器转写未识别到「{word}」，疑似漏读。",
                    "severity": "warning",
                    "word": word,
                    "expected": word,
                    "actual": "",
                    "reference_index": reference_index,
                    "inferred": True,
                })
        elif tag == "insert":
            inserted = actual[j1:j2]
            actual_text = " ".join(item["text"] for item in actual_tokens[j1:j2])
            reread = _looks_like_reread(inserted, expected, i1)
            anchor = min(max(i1 - 1 if i1 else i1, 0), len(expected_tokens) - 1)
            issues.append({
                "dimension": "browser_speech",
                "source": "browser_speech_alignment",
                "type": "word_repeated" if reread else "word_inserted",
                "message": (
                    f"浏览器转写发现重复内容「{actual_text}」，疑似回读。"
                    if reread else f"浏览器转写多出「{actual_text}」，疑似增读。"
                ),
                "severity": "warning",
                "word": actual_text,
                "expected": "",
                "actual": actual_text,
                "reference_index": anchor,
                "inferred": True,
            })
        elif tag == "replace":
            heard = [item["text"] for item in actual_tokens[j1:j2]]
            for offset, reference_index in enumerate(range(i1, i2)):
                expected_word = expected_tokens[reference_index]["text"]
                actual_word = heard[offset] if offset < len(heard) else " ".join(heard)
                issues.append({
                    "dimension": "browser_speech",
                    "source": "browser_speech_alignment",
                    "type": "word_replaced",
                    "message": f"「{expected_word}」被识别为「{actual_word or '未识别'}」，疑似错读或识别偏差。",
                    "severity": "warning",
                    "word": expected_word,
                    "expected": expected_word,
                    "actual": actual_word,
                    "reference_index": reference_index,
                    "inferred": True,
                })

    return issues[:200]


def suntone_evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw_details = source.get("word_details") if isinstance(source.get("word_details"), list) else []
    details = [dict(item) for item in raw_details[:500] if isinstance(item, dict)]
    return {
        "overall_score": source.get("overall_score") if isinstance(source.get("overall_score"), (int, float)) else None,
        "speed": source.get("speed") if isinstance(source.get("speed"), int) else None,
        "duration_seconds": source.get("duration_seconds") if isinstance(source.get("duration_seconds"), (int, float)) else None,
        "rear_tone": str(source.get("rear_tone"))[:20] if source.get("rear_tone") else None,
        "word_details": details,
        "word_detail_level": (
            str(source.get("word_detail_level"))[:20]
            if source.get("word_detail_level") in {"word", "sentence"} else None
        ),
        "word_detail_count": (
            source.get("word_detail_count")
            if isinstance(source.get("word_detail_count"), int)
            else sum(1 for item in details if item.get("detail_level") == "word")
        ),
    }


def _attach_word_timing(issues: list[dict[str, Any]], word_details: list[dict[str, Any]]) -> None:
    words = [
        item for item in word_details
        if item.get("word") and item.get("char_type") != 1 and item.get("detail_level") != "sentence"
    ]
    for issue in issues:
        index = issue.get("reference_index")
        if not isinstance(index, int) or index < 0 or index >= len(words):
            continue
        detail = words[index]
        if isinstance(detail.get("start_ms"), int):
            issue["start_ms"] = detail["start_ms"]
        if isinstance(detail.get("end_ms"), int):
            issue["end_ms"] = detail["end_ms"]


def _iat_alignment(
    ai_results: list[dict[str, Any]],
    reference_text: str,
    word_details: list[dict[str, Any]],
    suntone_issues: list[dict[str, Any]],
    duration_seconds: float | int | None,
    fluency_score: float | int | None,
) -> tuple[
    str | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """Build auditable text-difference evidence from the completed IAT result."""
    for item in ai_results:
        if item.get("adapter") != "asr_iat" or item.get("status") != "completed":
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        transcript_value = payload.get("transcript")
        if not isinstance(transcript_value, str):
            return None, [], [], None, None
        transcript = normalize_transcript(transcript_value) or ""
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), list) else []
        provider = str(item.get("provider") or "asr_iat")
        diagnosis = diagnose_text_recognition(
            reference_text,
            transcript_value,
            iat_tokens=tokens,
            word_details=word_details,
            suntone_issues=suntone_issues,
            source="iat_text_alignment",
            provider=provider,
        )
        pause_diagnosis = diagnose_pause_patterns(
            payload.get("vad_segments") if isinstance(payload.get("vad_segments"), list) else [],
            iat_tokens=tokens,
            word_details=word_details,
            duration_seconds=duration_seconds,
            fluency_score=fluency_score,
        )
        audit_alignment = diagnosis["alignment"]
        display_alignment = [
            entry for entry in audit_alignment
            if entry.get("issue_status") in {"matched", "confirmed"}
        ]

        # Mutating the result payload is deliberate: save_learner_practice_attempt
        # persists this exact JSON object in cl_ai_results.payload.
        payload["tokens"] = tokens
        payload["vad_segments"] = (
            payload.get("vad_segments") if isinstance(payload.get("vad_segments"), list) else []
        )
        payload["alignment"] = audit_alignment
        payload["alignment_source"] = "iat_text_alignment"
        payload["reference_text"] = reference_text
        payload["normalized_reference_text"] = diagnosis["normalized_standard_text"]
        payload["normalized_transcript"] = diagnosis["normalized_asr_text"]
        payload["text_diagnosis"] = diagnosis
        payload["pause_diagnosis"] = pause_diagnosis
        item["payload"] = payload
        confirmed_issues = diagnosis["confirmed_issues"] + pause_diagnosis["confirmed_issues"]
        return transcript, display_alignment, confirmed_issues, provider, diagnosis, pause_diagnosis
    return None, [], [], None, None, None


def collect_practice_feedback(
    ai_results: list[dict[str, Any]],
    reference_text: str,
    recognized_text: str | None,
) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    evidence = suntone_evidence(None)
    suntone_payload: dict[str, Any] = {}
    system_issues: list[dict[str, Any]] = []

    for item in ai_results:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        payload_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        if item.get("status") != "completed" and not payload_issues:
            system_issues.append({
                "dimension": item.get("adapter", "ai"),
                "type": "provider_unconfigured" if item.get("status") == "pending_adapter" else "provider_failed",
                "message": "AI 服务暂不可用，请稍后重试。",
                "error_code": item.get("error_code"),
            })
        if item.get("status") == "completed" and isinstance(payload.get("scores"), dict):
            scores.update(payload["scores"])
        if item.get("adapter") == "suntone" and item.get("status") == "completed":
            evidence = suntone_evidence(payload)
            suntone_payload = payload

    browser_transcript = normalize_transcript(recognized_text)
    raw_suntone_issues = (
        suntone_payload.get("issues") if isinstance(suntone_payload.get("issues"), list) else []
    )
    confirmed_tone_issues = [
        dict(issue) for issue in raw_suntone_issues
        if isinstance(issue, dict)
        and issue.get("type") == "chinese_tone_error"
        and issue.get("issue_status") == "confirmed"
    ]
    fluency_score = scores.get("fluency")
    iat_transcript, alignment, confirmed_issues, iat_provider, diagnosis, pause_diagnosis = _iat_alignment(
        ai_results,
        reference_text,
        evidence["word_details"],
        raw_suntone_issues,
        evidence["duration_seconds"],
        fluency_score,
    )
    if iat_transcript is not None:
        pass
    elif browser_transcript:
        diagnosis = diagnose_text_recognition(
            reference_text,
            browser_transcript,
            word_details=evidence["word_details"],
            suntone_issues=raw_suntone_issues,
            source="browser_speech_alignment",
            provider="browser_speech",
        )
        pause_diagnosis = None
        confirmed_issues = diagnosis["confirmed_issues"]
        alignment = [
            entry for entry in diagnosis["alignment"]
            if entry.get("issue_status") in {"matched", "confirmed"}
        ]
    else:
        phoneme_patterns = analyze_common_phoneme_patterns(
            evidence["word_details"],
            raw_suntone_issues,
        )
        confirmed_issues = phoneme_patterns["confirmed"]
        diagnosis = None
        pause_diagnosis = None
    existing_issue_keys = {
        (issue.get("type"), issue.get("reference_index"), issue.get("start_ms"))
        for issue in confirmed_issues
        if isinstance(issue, dict)
    }
    confirmed_issues.extend(
        issue for issue in confirmed_tone_issues
        if (issue.get("type"), issue.get("reference_index"), issue.get("start_ms"))
        not in existing_issue_keys
    )
    statuses = {item.get("status") for item in ai_results}
    ai_status = (
        "completed" if statuses == {"completed"}
        else "partial" if "completed" in statuses
        else "failed" if "failed" in statuses
        else "pending_adapter"
    )
    return {
        "ai_status": ai_status,
        "score_summary": scores,
        # Learner-facing issues contain confirmed findings only. Pending and
        # filtered candidates remain server-side for review and audit.
        "issues": confirmed_issues[:300],
        "pending_review_issues": ((
            (diagnosis or {}).get("pending_review_issues", [])
            if diagnosis is not None else phoneme_patterns["pending_review"]
        ) + (pause_diagnosis or {}).get("pending_review_issues", []))[:300],
        "filtered_issues": (diagnosis or {}).get("filtered_issues", [])[:300],
        "text_diagnosis": diagnosis,
        "pause_diagnosis": pause_diagnosis,
        "system_issues": system_issues,
        "recognized_text": iat_transcript if iat_transcript is not None else browser_transcript,
        "browser_transcript": browser_transcript,
        "iat_transcript": iat_transcript,
        "transcript_source": "iat" if iat_transcript is not None else (
            "browser_speech" if browser_transcript else None
        ),
        "alignment": alignment,
        "alignment_source": "iat_text_alignment" if iat_transcript is not None else (
            "browser_speech_alignment" if browser_transcript else None
        ),
        "alignment_provider": iat_provider or ("browser_speech" if browser_transcript else None),
        "normalized_transcript": (diagnosis or {}).get("normalized_asr_text"),
        "normalized_reference_text": (diagnosis or {}).get("normalized_standard_text"),
        **evidence,
    }
