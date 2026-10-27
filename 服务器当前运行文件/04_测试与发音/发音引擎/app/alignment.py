from __future__ import annotations

from typing import Any

from .model import HeardPhone


NEAR_GROUPS = [
    {"ɪ", "i"},
    {"ʊ", "u"},
    {"ɛ", "æ"},
    {"ʌ", "ɑ", "ə"},
    {"ð", "z", "d"},
    {"θ", "s", "t"},
    {"b", "p"},
    {"d", "t"},
    {"ɡ", "k"},
    {"z", "s"},
    {"v", "f", "w"},
    {"ʒ", "ʃ"},
    {"d͡ʒ", "t͡ʃ"},
    {"n", "ŋ"},
    {"ɹ", "l"},
]
VOWELS = {"aɪ", "aʊ", "eɪ", "i", "oʊ", "u", "æ", "ɑ", "ɔ", "ɔɪ", "ə", "ɚ", "ɛ", "ɪ", "ʊ", "ʌ"}


def _near(left: str, right: str) -> bool:
    return any(left in group and right in group for group in NEAR_GROUPS)


def _in_consonant_cluster(expected: list[str], index: int) -> bool:
    if expected[index] in VOWELS:
        return False
    return (
        index > 0 and expected[index - 1] not in VOWELS
    ) or (
        index + 1 < len(expected) and expected[index + 1] not in VOWELS
    )


def align(expected: list[str], heard: list[HeardPhone]) -> list[dict[str, Any]]:
    rows, cols = len(expected) + 1, len(heard) + 1
    costs = [[0] * cols for _ in range(rows)]
    back: list[list[str | None]] = [[None] * cols for _ in range(rows)]
    for i in range(1, rows):
        costs[i][0], back[i][0] = i, "delete"
    for j in range(1, cols):
        costs[0][j], back[0][j] = j, "insert"
    for i in range(1, rows):
        for j in range(1, cols):
            same = expected[i - 1] == heard[j - 1].phone
            choices = [
                (costs[i - 1][j - 1] + (0 if same else 1), "match" if same else "substitute"),
                (costs[i - 1][j] + 1, "delete"),
                (costs[i][j - 1] + 1, "insert"),
            ]
            costs[i][j], back[i][j] = min(choices, key=lambda item: item[0])

    operations: list[dict[str, Any]] = []
    i, j = len(expected), len(heard)
    while i or j:
        operation = back[i][j]
        if operation in {"match", "substitute"}:
            operations.append(
                {
                    "status": "correct" if operation == "match" else "substitution",
                    "expected_index": i - 1,
                    "expected": expected[i - 1],
                    "heard": heard[j - 1].phone,
                    "confidence": heard[j - 1].confidence,
                }
            )
            i -= 1
            j -= 1
        elif operation == "delete":
            operations.append(
                {
                    "status": "deletion",
                    "expected_index": i - 1,
                    "expected": expected[i - 1],
                    "heard": None,
                    "confidence": None,
                }
            )
            i -= 1
        else:
            operations.append(
                {
                    "status": "insertion",
                    "expected_index": None,
                    "expected": None,
                    "heard": heard[j - 1].phone,
                    "confidence": heard[j - 1].confidence,
                }
            )
            j -= 1
    return list(reversed(operations))


def assess_alignment(
    word: dict[str, Any],
    heard: list[HeardPhone],
    target_confidence: list[float] | None = None,
) -> dict[str, Any]:
    expected = word["phonemes"]
    operations = align(expected, heard)
    target_confidence = target_confidence or []
    focus_by_index = {item["index"]: item for item in word.get("focus", [])}
    weighted_cost = 0.0
    target_errors: list[dict[str, Any]] = []

    for operation in operations:
        index = operation["expected_index"]
        forced_confidence = (
            target_confidence[index]
            if index is not None and index < len(target_confidence)
            else 0.0
        )
        operation["target_confidence"] = forced_confidence if index is not None else None
        if operation["status"] == "correct":
            operation["severity"] = "none"
            continue
        if operation["status"] == "insertion":
            # For a known single word, short extra decoder tokens are commonly caused by
            # coarticulation. They should not dominate the pronunciation score.
            weighted_cost += 0.05 if (operation["confidence"] or 0.0) >= 0.65 else 0.0
            operation["severity"] = "minor"
            continue

        # The text is known in advance. When forced CTC alignment finds convincing
        # evidence for the expected phone, prefer it over a noisy greedy decode.
        if forced_confidence >= 0.35:
            operation["status"] = "correct"
            operation["heard"] = operation["expected"]
            operation["confidence"] = forced_confidence
            operation["severity"] = "none"
            operation["recognized_by"] = "forced_alignment"
            continue

        heard_confidence = operation["confidence"] or 0.0
        uncertain = heard_confidence < 0.65 and (
            forced_confidence >= 0.08
            or (_in_consonant_cluster(expected, index) and forced_confidence >= 0.02)
        )
        if uncertain:
            weighted_cost += 0.2
            operation["severity"] = "minor"
            operation["tip"] = "这个音比较短，系统已按自然连读降低扣分。"
            continue

        focus = focus_by_index.get(index)
        if focus:
            weighted_cost += 1.0
            operation["severity"] = "target"
            operation["tip"] = focus["tip"]
            target_errors.append(operation)
        elif operation["status"] == "substitution" and _near(operation["expected"], operation["heard"]):
            weighted_cost += 0.3
            operation["severity"] = "minor"
        else:
            weighted_cost += 0.75
            operation["severity"] = "major"

    score = round(max(0.0, 100.0 * (1.0 - weighted_cost / max(1, len(expected)))))
    if target_errors:
        verdict = "needs_practice"
    elif score >= 85:
        verdict = "excellent"
    elif score >= 75:
        verdict = "good"
    else:
        verdict = "needs_practice"

    feedback = []
    for error in target_errors:
        heard_phone = error["heard"] or "漏读"
        feedback.append(
            {
                "type": "target_phone",
                "title": f"重点纠正 /{error['expected']}/",
                "message": f"目标音 /{error['expected']}/，本次听起来像 /{heard_phone}/。",
                "tip": error["tip"],
            }
        )
    if not feedback and verdict == "excellent":
        feedback.append({"type": "success", "title": "发音清晰", "message": "重点音已正确完成。", "tip": "保持当前口型和气流。"})
    elif not feedback:
        feedback.append({"type": "general", "title": "再慢一点", "message": "部分音素还不够稳定。", "tip": "先听示范，再按音节慢速读一遍。"})

    return {
        "score": score,
        "verdict": verdict,
        "phonemes": operations,
        "feedback": feedback,
        "target_error_count": len(target_errors),
    }

