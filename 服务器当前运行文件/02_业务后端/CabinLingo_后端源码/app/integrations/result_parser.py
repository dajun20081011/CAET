from __future__ import annotations

from typing import Any


def _find(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in names and item is not None:
                return item
        for item in value.values():
            found = _find(item, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find(item, names)
            if found is not None:
                return found
    return None


def _score(payload: dict[str, Any], names: set[str], scale: float) -> float | None:
    value = _find(payload, names)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value) / max(scale, 0.0001) * 100
    return round(min(100, max(0, normalized)), 2)


def _issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _find(payload, {"issues", "errors", "mistakes", "problems"})
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:200]:
        if isinstance(item, str):
            result.append({"type": "provider_issue", "message": item, "severity": "warning"})
        elif isinstance(item, dict):
            safe = {key: value for key, value in item.items() if key in {
                "type", "message", "severity", "word", "expected", "actual",
                "start_ms", "end_ms", "phoneme", "position"
            }}
            if safe:
                result.append(safe)
    return result


def parse_asr(payload: dict[str, Any], score_scale: float) -> dict[str, Any]:
    transcript = _find(payload, {"transcript", "recognized_text", "recognised_text", "text"})
    scores = {}
    completeness = _score(payload, {"completeness", "completeness_score", "integrity_score"}, score_scale)
    if completeness is not None:
        scores["completeness"] = completeness
    return {"transcript": transcript if isinstance(transcript, str) else None, "scores": scores, "issues": _issues(payload)}


def parse_ise(payload: dict[str, Any], score_scale: float) -> dict[str, Any]:
    candidates = {
        "pronunciation": {"pronunciation", "pronunciation_score", "accuracy_score"},
        "fluency": {"fluency", "fluency_score"},
        "completeness": {"completeness", "completeness_score", "integrity_score"},
    }
    scores = {name: value for name, keys in candidates.items() if (value := _score(payload, keys, score_scale)) is not None}
    return {"scores": scores, "issues": _issues(payload)}


def parse_suntone(payload: dict[str, Any], score_scale: float) -> dict[str, Any]:
    candidates = {
        "expression": {"expression", "expression_score", "delivery_score"},
        "semantic": {"semantic", "semantic_score", "semantic_match"},
        "professionalism": {"professionalism", "professional_score", "professional_expression"},
    }
    scores = {name: value for name, keys in candidates.items() if (value := _score(payload, keys, score_scale)) is not None}
    return {"scores": scores, "issues": _issues(payload)}

