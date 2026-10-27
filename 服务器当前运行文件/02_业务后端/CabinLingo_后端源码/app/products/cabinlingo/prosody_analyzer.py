"""Rule-based prosody hints for CabinLingo TTS.

This module deliberately uses only Python's standard library so deploying V2 Core
does not change backend dependencies, environment variables, or persistent data.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


VERSION = "2.0.1"

SCENES: dict[str, dict[str, Any]] = {
    "general": {
        "label": "通用",
        "description": "自然、清晰、不过度表演",
        "rate": 1.0,
        "pitch": 0,
        "energy": 1.0,
    },
    "medical_help": {
        "label": "医疗求助",
        "description": "冷静、清晰，关键信息稍慢并增加停顿",
        "rate": 0.92,
        "pitch": -1,
        "energy": 1.08,
    },
    "emergency": {
        "label": "紧急情况",
        "description": "紧迫但保持可懂度，动作词突出",
        "rate": 0.96,
        "pitch": 1,
        "energy": 1.16,
    },
    "service": {
        "label": "服务沟通",
        "description": "礼貌、友好、节奏稳定",
        "rate": 0.98,
        "pitch": 1,
        "energy": 1.02,
    },
}

_SENTENCE_RE = re.compile(r".*?(?:[。！？!?；;]+|(?:\.{3,}|…{2,})|$)", re.S)
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_MEDICAL_TERMS = re.compile(
    r"(救护车|急救|医院|医生|护士|过敏|药物|出血|呼吸|疼痛|昏迷|地址|位置|"
    r"ambulance|emergency|hospital|doctor|allerg(?:y|ic)|bleeding|breath(?:e|ing)?|pain)",
    re.I,
)
_ACTION_TERMS = re.compile(
    r"(立即|马上|不要|停止|离开|报警|求救|call|stop|leave|now|immediately)", re.I
)


def list_scenes() -> list[dict[str, Any]]:
    """Return scene metadata without exposing mutable module state."""
    return [dict(id=scene_id, **deepcopy(profile)) for scene_id, profile in SCENES.items()]


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_RE.sub(" ", text)
    return re.sub(r" *\n+ *", "\n", text).strip()


def _sentences(text: str) -> list[str]:
    items = [match.group(0).strip() for match in _SENTENCE_RE.finditer(text)]
    return [item for item in items if item]


def _pause_after(sentence: str) -> int:
    if sentence.endswith(("。", "！", "!", "？", "?")):
        return 420
    if sentence.endswith(("；", ";")):
        return 320
    if sentence.endswith(("……", "...")):
        return 500
    return 220


def analyze_text(text: str, scene: str = "general") -> dict[str, Any]:
    """Analyze text into sentence-level TTS guidance.

    Raises:
        TypeError: if ``text`` or ``scene`` is not a string.
        ValueError: if text is empty or the scene is unknown.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(scene, str):
        raise TypeError("scene must be a string")

    normalized = _normalize(text)
    if not normalized:
        raise ValueError("text must not be empty")
    if len(normalized) > 10_000:
        raise ValueError("text exceeds 10000 characters")
    if scene not in SCENES:
        raise ValueError(f"unknown scene: {scene}")

    base = SCENES[scene]
    segments: list[dict[str, Any]] = []
    for index, sentence in enumerate(_sentences(normalized)):
        emphasis: list[str] = []
        emphasis.extend(match.group(0) for match in _MEDICAL_TERMS.finditer(sentence))
        emphasis.extend(match.group(0) for match in _ACTION_TERMS.finditer(sentence))
        # Preserve order while removing case-insensitive duplicates.
        seen: set[str] = set()
        emphasis = [
            item for item in emphasis
            if not (item.casefold() in seen or seen.add(item.casefold()))
        ]

        rate = float(base["rate"])
        energy = float(base["energy"])
        if emphasis and scene in {"medical_help", "emergency"}:
            rate = max(0.75, rate - 0.05)
            energy = min(1.25, energy + 0.04)

        segments.append(
            {
                "index": index,
                "text": sentence,
                "rate": round(rate, 2),
                "pitch": int(base["pitch"]),
                "energy": round(energy, 2),
                "pause_after_ms": _pause_after(sentence),
                "emphasis": emphasis,
            }
        )

    return {
        "version": VERSION,
        "scene": scene,
        "normalized_text": normalized,
        "sentence_count": len(segments),
        "segments": segments,
    }
