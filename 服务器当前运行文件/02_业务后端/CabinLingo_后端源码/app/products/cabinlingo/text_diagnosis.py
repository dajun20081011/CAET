from __future__ import annotations

import re
from typing import Any

from .text_alignment import build_alignment_payload, tokenize_text
from .text_normalization import (
    filler_tokens,
    normalize_for_comparison,
    pinyin_similarity,
    professional_terms,
    texts_are_equivalent,
)


DEFAULT_CONFIDENCE_THRESHOLD = 0.75
PIPELINE_ORDER = [
    "raw_asr_result",
    "text_cleanup",
    "traditional_to_simplified",
    "case_and_punctuation_normalization",
    "number_and_unit_normalization",
    "aviation_dictionary_correction",
    "configured_equivalence_mapping",
    "pinyin_or_phoneme_similarity",
    "asr_confidence_filter",
    "context_validation",
    "reference_alignment",
    "candidate_generation",
    "multi_evidence_confirmation",
    "presentation_filter",
]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _confidence(value: Any) -> float | None:
    result = _number(value)
    if result is None:
        return None
    if result > 1:
        result /= 100
    return round(result, 4) if 0 <= result <= 1 else None


def _professional_reference_indexes(reference_text: str) -> set[int]:
    tokens = tokenize_text(reference_text)
    indexes: set[int] = set()
    spans: list[tuple[int, int]] = []
    folded_reference = reference_text.casefold()
    for term in professional_terms():
        folded_term = term.casefold()
        start = 0
        while folded_term and (position := folded_reference.find(folded_term, start)) >= 0:
            spans.append((position, position + len(term)))
            start = position + max(len(term), 1)
    for match in re.finditer(r"(?<![A-Za-z0-9])[A-Za-z]{2,3}\s*-?\s*\d{2,5}(?![A-Za-z0-9])", reference_text):
        spans.append(match.span())
    for index, token in enumerate(tokens):
        if any(token["start_char"] < end and token["end_char"] > start for start, end in spans):
            indexes.add(index)
    return indexes


def _word_detail(reference_index: Any, word_details: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(reference_index, int) or reference_index < 0:
        return None
    indexed = next((
        item for item in word_details
        if isinstance(item, dict)
        and item.get("detail_level") != "sentence"
        and item.get("reference_index") == reference_index
    ), None)
    if indexed is not None:
        return indexed
    spoken = [
        item for item in word_details
        if isinstance(item, dict)
        and item.get("char_type") != 1
        and item.get("detail_level") != "sentence"
    ]
    return spoken[reference_index] if reference_index < len(spoken) else None


def _suntone_support(
    detail: dict[str, Any] | None,
    issue_type: str,
    provider_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not detail:
        return []
    result: list[dict[str, Any]] = []
    start_ms = detail.get("start_ms")
    compatible_provider_types = {issue_type}
    if issue_type == "word_repeated":
        # Paragraph mode reports an insertion before the current word.  IAT
        # alignment determines whether that inserted material repeats an
        # adjacent reference word, turning the combined evidence into reread.
        compatible_provider_types.add("word_inserted")
    matching_provider_issue = next((
        item for item in provider_issues
        if isinstance(item, dict)
        and item.get("type") in compatible_provider_types
        and (
            (isinstance(start_ms, int) and item.get("start_ms") == start_ms)
            or (detail.get("word") and item.get("word") == detail.get("word"))
        )
    ), None)
    if matching_provider_issue:
        result.append({
            "kind": "suntone_read_type",
            "value": matching_provider_issue.get("type"),
            "message": "Suntone 朗读类型在同一位置检测到异常。",
        })
    pronunciation = _number(detail.get("pronunciation"))
    overall = _number(detail.get("overall"))
    lowest_word_score = min(
        (value for value in (pronunciation, overall) if value is not None),
        default=None,
    )
    if lowest_word_score is not None and lowest_word_score < 70:
        result.append({
            "kind": "suntone_word_score",
            "value": round(lowest_word_score, 2),
            "message": "Suntone 同位置字词评分低于 70 分。",
        })
    phonemes = detail.get("phonemes") if isinstance(detail.get("phonemes"), list) else []
    low_phonemes = [
        item for item in phonemes
        if isinstance(item, dict)
        and _number(item.get("pronunciation")) is not None
        and float(item["pronunciation"]) < 70
    ]
    if low_phonemes:
        result.append({
            "kind": "suntone_phoneme_score",
            "value": min(float(item["pronunciation"]) for item in low_phonemes),
            "phonemes": [str(item.get("phoneme") or item.get("phone") or "") for item in low_phonemes[:8]],
            "message": "Suntone 同位置音素评分异常。",
        })
    return result


def _issue_type(alignment_type: str) -> str:
    return {
        "omission": "word_omitted",
        "insertion": "word_inserted",
        "substitution": "word_replaced",
    }.get(alignment_type, "recognition_difference")


def _neighbor_entry(
    alignment: list[dict[str, Any]],
    position: int,
    direction: int,
) -> dict[str, Any] | None:
    index = position + direction
    while 0 <= index < len(alignment):
        entry = alignment[index]
        if isinstance(entry.get("reference_index"), int):
            return entry
        index += direction
    return None


def _insertion_context(
    alignment: list[dict[str, Any]],
    position: int,
) -> tuple[bool, int | None]:
    entry = alignment[position]
    inserted = str(entry.get("normalized_recognized") or "")
    previous = _neighbor_entry(alignment, position, -1)
    following = _neighbor_entry(alignment, position, 1)
    adjacent_reference = {
        str(item.get("normalized_reference") or "")
        for item in (previous, following)
        if item is not None
    }
    repeated = bool(inserted and inserted in adjacent_reference)
    # Suntone paragraph readType=1 is attached to the reference word after
    # the inserted speech, so prefer that word for cross-provider matching.
    anchor = following or previous
    reference_index = anchor.get("reference_index") if anchor else None
    return repeated, reference_index if isinstance(reference_index, int) else None


def _neighbor_confidence(
    alignment: list[dict[str, Any]],
    position: int,
) -> float | None:
    values = [
        _confidence(item.get("confidence"))
        for item in (
            _neighbor_entry(alignment, position, -1),
            _neighbor_entry(alignment, position, 1),
        )
        if item is not None
    ]
    available = [value for value in values if value is not None]
    return min(available) if available else None


def _advice(issue_type: str) -> str:
    return {
        "word_omitted": "回听该时间段，对照标准广播词确认是否完整朗读。",
        "word_inserted": "回听该时间段，确认是否出现额外内容或重复起读。",
        "word_replaced": "回听该时间段，并结合标准发音核对实际读音。",
        "word_repeated": "回听该时间段，练习连续朗读并减少重复起读。",
    }.get(issue_type, "回听原录音后由教员结合上下文复核。")


def _status_message(status: str, issue_type: str, expected: str, actual: str) -> str:
    display_expected = expected or "未识别内容"
    display_actual = actual or "未识别"
    if status == "confirmed":
        return f"检测到标准文本「{display_expected}」与识别文本「{display_actual}」存在差异，并有同位置评分证据支持。"
    if status == "filtered":
        return "识别文本与标准文本存在差异，系统已过滤，不计入测评结果。"
    if issue_type == "word_omitted":
        return f"IAT 未识别到「{display_expected}」，证据不足，已进入教员复核。"
    return f"检测到「{display_expected}」与「{display_actual}」疑似存在表达差异，已进入教员复核。"


def analyze_common_phoneme_patterns(
    word_details: list[dict[str, Any]] | None,
    provider_issues: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Require repeated, cross-word evidence before naming a shared phoneme issue."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for detail in word_details or []:
        if (
            not isinstance(detail, dict)
            or detail.get("detail_level") == "sentence"
            or not str(detail.get("word") or "").strip()
        ):
            continue
        word_score = _number(detail.get("pronunciation"))
        phonemes = detail.get("phonemes") if isinstance(detail.get("phonemes"), list) else []
        for phoneme in phonemes:
            if not isinstance(phoneme, dict):
                continue
            score = _number(phoneme.get("pronunciation"))
            start_ms = phoneme.get("start_ms")
            name = str(phoneme.get("phoneme") or phoneme.get("phone") or "").strip().casefold()
            if not name or score is None or score >= 70 or not isinstance(start_ms, int):
                continue
            groups.setdefault(name, []).append({
                "word": str(detail["word"]),
                "score": score,
                "word_score": word_score,
                "start_ms": start_ms,
                "end_ms": phoneme.get("end_ms"),
            })

    has_audio_warning = any(
        isinstance(item, dict) and str(item.get("type") or "").startswith("provider_warning_")
        for item in provider_issues or []
    )
    confirmed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for phoneme, occurrences in groups.items():
        words = sorted({item["word"] for item in occurrences})
        corroborated = (
            len(occurrences) >= 3
            and len(words) >= 2
            and all(item["word_score"] is not None and item["word_score"] < 70 for item in occurrences)
            and not has_audio_warning
        )
        issue = {
            "dimension": "pronunciation",
            "source": "suntone_phoneme_pattern",
            "provider": "xfyun_suntone",
            "type": "common_phoneme_problem" if corroborated else "possible_phoneme_deviation",
            "issue_status": "confirmed" if corroborated else "pending_review",
            "severity": "warning" if corroborated else "info",
            "word": phoneme,
            "expected": phoneme,
            "actual": "音素评分异常",
            "start_ms": occurrences[0]["start_ms"],
            "end_ms": occurrences[0].get("end_ms"),
            "question": "当前广播词",
            "occurrence_count": len(occurrences),
            "affected_words": words,
            "evidence": [
                {
                    "kind": "suntone_phoneme_repetition",
                    "value": len(occurrences),
                    "message": f"音素 /{phoneme}/ 出现 {len(occurrences)} 次低分。",
                },
                {
                    "kind": "cross_word_coverage",
                    "value": len(words),
                    "message": f"涉及 {len(words)} 个不同英文单词。",
                },
                {
                    "kind": "audio_timestamps",
                    "value": [item["start_ms"] for item in occurrences],
                    "message": "每次异常均保留原录音定位。",
                },
            ],
            "training_advice": f"针对 /{phoneme}/ 进行最小对立词和广播句跟读训练。",
            "message": (
                f"检测到音素 /{phoneme}/ 出现 {len(occurrences)} 次明显偏差，涉及 {len(words)} 个英文单词。"
                if corroborated
                else (
                    "本次录音中检测到一次疑似发音偏差，证据不足，已进入教员复核。"
                    if len(occurrences) == 1
                    else f"本次录音中检测到 {len(occurrences)} 次疑似发音偏差，尚未满足共性问题条件，已进入教员复核。"
                )
            ),
        }
        (confirmed if corroborated else pending).append(issue)
    return {"confirmed": confirmed, "pending_review": pending}


def diagnose_text_recognition(
    reference_text: str,
    transcript: str | None,
    *,
    iat_tokens: list[dict[str, Any]] | None = None,
    word_details: list[dict[str, Any]] | None = None,
    suntone_issues: list[dict[str, Any]] | None = None,
    source: str = "iat_text_alignment",
    provider: str | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    raw_transcript = transcript if isinstance(transcript, str) else ""
    reference_normalization = normalize_for_comparison(reference_text)
    transcript_normalization = normalize_for_comparison(raw_transcript)
    details = [
        dict(item) for item in (word_details or [])
        if isinstance(item, dict) and item.get("detail_level") != "sentence"
    ]
    provider_issues = [dict(item) for item in (suntone_issues or []) if isinstance(item, dict)]
    built = build_alignment_payload(reference_text, raw_transcript, iat_tokens or [])
    raw_alignment = built["alignment"]
    protected_indexes = _professional_reference_indexes(reference_text)
    confirmed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    enriched_alignment: list[dict[str, Any]] = []

    canonical_equal = (
        bool(reference_normalization["tokens"] or transcript_normalization["tokens"])
        and reference_normalization["tokens"] == transcript_normalization["tokens"]
    )
    if canonical_equal and reference_text.strip() != raw_transcript.strip():
        filtered.append({
            "dimension": "text_alignment",
            "source": source,
            "provider": provider,
            "type": "recognition_difference",
            "issue_status": "filtered",
            "message": _status_message("filtered", "recognition_difference", reference_text, raw_transcript),
            "expected": reference_text,
            "actual": raw_transcript,
            "filter_reason": "normalized_equivalent",
            "evidence": [{"kind": "normalization", "message": "规范化后的文本一致。"}],
            "inferred": True,
        })

    for alignment_position, entry in enumerate(raw_alignment):
        current = {**entry, "source": source, "provider": provider}
        if entry.get("type") == "matched":
            current["issue_status"] = "matched"
            enriched_alignment.append(current)
            continue

        alignment_type = str(entry.get("type") or "difference")
        issue_type = _issue_type(alignment_type)
        expected = str(entry.get("reference") or "")
        actual = str(entry.get("recognized") or "")
        reference_index = entry.get("reference_index")
        if alignment_type == "insertion":
            repeated, insertion_anchor = _insertion_context(raw_alignment, alignment_position)
            if repeated:
                issue_type = "word_repeated"
            if insertion_anchor is not None:
                reference_index = insertion_anchor
        detail = _word_detail(reference_index, details)
        start_ms = entry.get("start_ms")
        end_ms = None
        if not isinstance(start_ms, int) and detail and isinstance(detail.get("start_ms"), int):
            start_ms = detail["start_ms"]
        if detail and isinstance(detail.get("end_ms"), int):
            end_ms = detail["end_ms"]
        confidence = _confidence(entry.get("confidence"))
        confidence_source = "word"
        if confidence is None and alignment_type == "omission":
            confidence = _neighbor_confidence(raw_alignment, alignment_position)
            confidence_source = "adjacent_context"
        evidence: list[dict[str, Any]] = [{
            "kind": "asr_text_difference",
            "expected": expected,
            "actual": actual,
            "message": "ASR 文本与标准文本存在差异。",
        }]
        if confidence is not None:
            evidence.append({
                "kind": "asr_confidence",
                "value": confidence,
                "threshold": confidence_threshold,
                "source": confidence_source,
                "message": (
                    "漏读位置无识别词，采用相邻 IAT 词的最低置信度校验上下文。"
                    if confidence_source == "adjacent_context"
                    else "保留 IAT 明确返回的词级置信度。"
                ),
            })
        suntone_support = _suntone_support(detail, issue_type, provider_issues)
        evidence.extend(suntone_support)

        status = "pending_review"
        filter_reason: str | None = None
        pinyin_score = pinyin_similarity(expected, actual)
        local_equivalent = bool(expected or actual) and texts_are_equivalent(expected, actual)
        actual_normalized = normalize_for_comparison(actual)["normalized_text"]
        if canonical_equal or local_equivalent:
            status, filter_reason = "filtered", "configured_or_normalized_equivalence"
        elif issue_type == "word_inserted" and actual_normalized in filler_tokens():
            status, filter_reason = "filtered", "filler_or_non_semantic_sound"
        elif pinyin_score == 1:
            status, filter_reason = "filtered", "chinese_homophone"
            evidence.append({"kind": "pinyin_similarity", "value": pinyin_score, "message": "字形不同但读音相同。"})
        elif pinyin_score is not None and pinyin_score >= 0.86:
            status, filter_reason = "pending_review", "chinese_near_homophone_requires_review"
            evidence.append({"kind": "pinyin_similarity", "value": pinyin_score, "message": "读音高度接近，不能仅按字形判错。"})
        elif isinstance(reference_index, int) and reference_index in protected_indexes:
            status, filter_reason = "pending_review", "aviation_or_proper_name_requires_review"
        elif confidence is not None and confidence < confidence_threshold:
            status, filter_reason = "filtered", "low_asr_confidence"
        elif confidence is None:
            status, filter_reason = "pending_review", "asr_confidence_unavailable"
        elif not isinstance(start_ms, int):
            status, filter_reason = "pending_review", "audio_timestamp_unavailable"
        elif not suntone_support:
            status, filter_reason = "pending_review", "single_source_evidence_only"
        else:
            status = "confirmed"

        issue = {
            "dimension": "text_alignment",
            "source": source,
            "provider": provider,
            "type": issue_type,
            "alignment_type": alignment_type,
            "issue_status": status,
            "message": _status_message(status, issue_type, expected, actual),
            "severity": "warning" if status == "confirmed" else "info",
            "word": expected or actual,
            "expected": expected,
            "actual": actual,
            "reference_index": reference_index,
            "recognized_index": entry.get("recognized_index"),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "confidence": confidence,
            "filter_reason": filter_reason,
            "evidence": evidence,
            "training_advice": _advice(issue_type),
            "question": "当前广播词",
            "inferred": True,
        }
        current["issue_status"] = status
        current["filter_reason"] = filter_reason
        current["confidence"] = confidence
        enriched_alignment.append(current)
        if status == "confirmed":
            confirmed.append(issue)
        elif status == "pending_review":
            pending.append(issue)
        else:
            filtered.append(issue)

    phoneme_patterns = analyze_common_phoneme_patterns(details, provider_issues)
    confirmed.extend(phoneme_patterns["confirmed"])
    pending.extend(phoneme_patterns["pending_review"])
    return {
        "pipeline_version": "text-diagnosis-v1",
        "pipeline_order": PIPELINE_ORDER,
        "confidence_threshold": confidence_threshold,
        "standard_text": reference_text,
        "normalized_standard_text": reference_normalization["normalized_text"],
        "raw_asr_text": raw_transcript,
        "normalized_asr_text": transcript_normalization["normalized_text"],
        "asr_tokens": [dict(item) for item in (iat_tokens or []) if isinstance(item, dict)],
        "alignment": enriched_alignment,
        "confirmed_issues": confirmed,
        "pending_review_issues": pending,
        "filtered_issues": filtered,
        "common_phoneme_issues": phoneme_patterns["confirmed"],
        "counts": {
            "confirmed": len(confirmed),
            "pending_review": len(pending),
            "filtered": len(filtered),
        },
    }
