from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from opencc import OpenCC
from pypinyin import Style, lazy_pinyin


_TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:[.:]\d+)?|[\u3400-\u9fff]")
_CHINESE_NUMBER_RE = re.compile(r"[零〇一二两三四五六七八九十百千]+")
_CHINESE_TIME_RE = re.compile(
    r"([零〇一二两三四五六七八九十百千]+)点"
    r"([零〇一二两三四五六七八九十百千]+)分?"
)
_PUNCTUATION_RE = re.compile(r"[^a-z0-9\u3400-\u9fff:.]+")
_SPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"^[\u3400-\u9fff]+$")
_OPENCC = OpenCC("t2s")


@lru_cache(maxsize=1)
def equivalence_dictionary() -> dict[str, Any]:
    path = Path(__file__).with_name("text_equivalences.json")
    with path.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise RuntimeError("Invalid text equivalence dictionary")
    return value


def _chinese_number(value: str) -> int | None:
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    if not value or any(character not in digits and character not in units for character in value):
        return None
    if not any(character in units for character in value):
        return int("".join(str(digits[character]) for character in value))
    total = 0
    current = 0
    for character in value:
        if character in digits:
            current = digits[character]
        else:
            total += (current or 1) * units[character]
            current = 0
    return total + current


def _replace_numbers(value: str, english_numbers: dict[str, str]) -> str:
    def time_replacement(match: re.Match[str]) -> str:
        hour = _chinese_number(match.group(1))
        minute = _chinese_number(match.group(2))
        if hour is None or minute is None:
            return match.group(0)
        return f"{hour}:{minute:02d}"

    value = _CHINESE_TIME_RE.sub(time_replacement, value)

    def number_replacement(match: re.Match[str]) -> str:
        number = _chinese_number(match.group(0))
        return str(number) if number is not None else match.group(0)

    value = _CHINESE_NUMBER_RE.sub(number_replacement, value)
    if english_numbers:
        pattern = re.compile(
            r"(?<![a-z])(" + "|".join(re.escape(item) for item in sorted(english_numbers, key=len, reverse=True)) + r")(?![a-z])"
        )
        value = pattern.sub(lambda match: english_numbers[match.group(1)], value)
    return value


def _replace_equivalences(value: str, groups: list[list[str]]) -> tuple[str, bool]:
    changed = False
    for index, raw_group in enumerate(groups):
        variants = [
            unicodedata.normalize("NFKC", _OPENCC.convert(str(item))).casefold()
            for item in raw_group if str(item).strip()
        ]
        if not variants:
            continue
        canonical = f" eqv{index} "
        for variant in sorted(set(variants), key=len, reverse=True):
            boundary_start = r"(?<![a-z0-9])" if variant[0].isascii() and variant[0].isalnum() else ""
            boundary_end = r"(?![a-z0-9])" if variant[-1].isascii() and variant[-1].isalnum() else ""
            pattern = re.compile(boundary_start + re.escape(variant) + boundary_end)
            value, count = pattern.subn(canonical, value)
            changed = changed or count > 0
    return value, changed


def _join_flight_identifiers(value: str) -> str:
    # IAT commonly expands CA1234 into "C A one two three four". Number words
    # are normalized before this step; joining is deliberately limited to an
    # airline-letter prefix followed by at least two digits.
    pattern = re.compile(r"(?<![a-z0-9])((?:[a-z]\s+){1,3})((?:\d\s*){2,})(?![a-z0-9:.])")
    return pattern.sub(
        lambda match: "".join(match.group(1).split()) + "".join(match.group(2).split()),
        value,
    )


def normalize_for_comparison(value: str | None) -> dict[str, Any]:
    raw_text = value if isinstance(value, str) else ""
    nfkc_text = unicodedata.normalize("NFKC", raw_text)
    simplified_text = _OPENCC.convert(nfkc_text)
    folded = simplified_text.casefold().replace("’", "'")
    dictionary = equivalence_dictionary()
    groups = dictionary.get("equivalence_groups") if isinstance(dictionary.get("equivalence_groups"), list) else []
    canonical, dictionary_changed = _replace_equivalences(folded, groups)
    english_numbers = dictionary.get("english_number_words")
    canonical = _replace_numbers(canonical, english_numbers if isinstance(english_numbers, dict) else {})
    canonical = _join_flight_identifiers(canonical)
    canonical = _PUNCTUATION_RE.sub(" ", canonical)
    canonical = _SPACE_RE.sub(" ", canonical).strip()
    tokens = _TOKEN_RE.findall(canonical)
    reasons: list[str] = []
    if nfkc_text != raw_text:
        reasons.append("width_or_format_normalized")
    if simplified_text != nfkc_text:
        reasons.append("traditional_chinese_normalized")
    if folded != simplified_text:
        reasons.append("case_normalized")
    if dictionary_changed:
        reasons.append("configured_equivalence_mapped")
    if canonical != folded.strip():
        reasons.append("punctuation_spacing_or_number_normalized")
    return {
        "raw_text": raw_text,
        "simplified_text": simplified_text,
        "normalized_text": canonical,
        "tokens": tokens,
        "normalization_reasons": list(dict.fromkeys(reasons)),
    }


def texts_are_equivalent(left: str | None, right: str | None) -> bool:
    return normalize_for_comparison(left)["tokens"] == normalize_for_comparison(right)["tokens"]


def pinyin_similarity(left: str | None, right: str | None) -> float | None:
    left_value = unicodedata.normalize("NFKC", left or "").strip()
    right_value = unicodedata.normalize("NFKC", right or "").strip()
    if not left_value or not right_value or not _CJK_RE.fullmatch(left_value + right_value):
        return None
    left_pinyin = " ".join(lazy_pinyin(_OPENCC.convert(left_value), style=Style.NORMAL, errors="default"))
    right_pinyin = " ".join(lazy_pinyin(_OPENCC.convert(right_value), style=Style.NORMAL, errors="default"))
    if not left_pinyin or not right_pinyin:
        return None
    if left_pinyin == right_pinyin:
        return 1.0
    from difflib import SequenceMatcher
    return round(SequenceMatcher(a=left_pinyin, b=right_pinyin, autojunk=False).ratio(), 4)


def filler_tokens() -> set[str]:
    raw = equivalence_dictionary().get("filler_tokens")
    return {str(item).casefold() for item in raw} if isinstance(raw, list) else set()


def professional_terms() -> list[str]:
    raw = equivalence_dictionary().get("professional_terms")
    return [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []
