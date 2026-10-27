from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def load_word_bank(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    words = payload.get("words", [])
    return {word["id"]: word for word in words}


def public_word(word: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": word["id"],
        "word": word["word"],
        "translation": word["translation"],
        "category": word["category"],
        "ipa": word["ipa"],
        "focus_phones": [focus["phone"] for focus in word.get("focus", [])],
    }

