import json
import re
from functools import lru_cache
from pathlib import Path

from app.core.errors import UnknownWordError
from app.schemas import WordEntry

WORD_BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "aviation_words.json"


@lru_cache
def load_word_bank() -> tuple[WordEntry, ...]:
    payload = json.loads(WORD_BANK_PATH.read_text(encoding="utf-8"))
    return tuple(WordEntry.model_validate(item) for item in payload)


def get_word(word_id: str) -> WordEntry:
    normalized = word_id.lower().strip()
    for item in load_word_bank():
        if item.id == normalized:
            return item
    raise UnknownWordError(f"词库中不存在 word_id={word_id!r}。")


def normalize_expected_text(value: str) -> str:
    return " ".join(re.findall(r"[A-Za-z']+", value)).lower()
