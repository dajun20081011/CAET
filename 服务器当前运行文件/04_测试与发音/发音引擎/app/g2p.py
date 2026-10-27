from __future__ import annotations

import re
import subprocess
import unicodedata
from functools import lru_cache


SUPPORTED_PHONES = {
    "aɪ", "aʊ", "b", "d", "d͡ʒ", "eɪ", "f", "h", "i", "j", "k", "l", "m", "n",
    "oʊ", "p", "s", "t", "t͡ʃ", "u", "v", "w", "z", "æ", "ð", "ŋ", "ɑ", "ɔ", "ɔɪ",
    "ə", "ɚ", "ɛ", "ɡ", "ɪ", "ɹ", "ʃ", "ʊ", "ʌ", "ʒ", "θ",
}
MULTI_PHONES = tuple(sorted((phone for phone in SUPPORTED_PHONES if len(phone) > 1), key=len, reverse=True))


def normalize_word(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9']+", value.lower()))[:64]


def parse_espeak_ipa(raw: str) -> list[str]:
    value = unicodedata.normalize("NFC", raw.strip().lower())
    # eSpeak-NG inserts joiners inside diphthongs/r-colored vowels. They are
    # pronunciation hints, not phonemes in the recognizer vocabulary.
    value = value.replace("\u200d", "").replace("\u200c", "").replace("\ufeff", "")
    replacements = {
        "dʒ": "d͡ʒ", "tʃ": "t͡ʃ", "əʊ": "oʊ", "ɜː": "ɚ", "ɝ": "ɚ", "ɜ": "ɚ",
        "ɐ": "ə", "ᵻ": "ɪ", "ɒ": "ɑ", "ɾ": "t", "ɫ": "l", "g": "ɡ", "r": "ɹ",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.replace("ˈ", "").replace("ˌ", "").replace("ː", "").replace(".", "")

    phones: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character.isspace() or character in {"-", "_", "|", "/", "[", "]", "(", ")"}:
            index += 1
            continue
        matched = next((phone for phone in MULTI_PHONES if value.startswith(phone, index)), None)
        if matched:
            phones.append(matched)
            index += len(matched)
            continue
        if character in SUPPORTED_PHONES:
            phones.append(character)
            index += 1
            continue
        if unicodedata.combining(character) or unicodedata.category(character).startswith("M"):
            index += 1
            continue
        raise ValueError(f"Unsupported IPA symbol from espeak-ng: {character}")
    if not phones:
        raise ValueError("No supported phonemes generated")
    return phones


@lru_cache(maxsize=1024)
def resolve_word(value: str) -> dict:
    word = normalize_word(value)
    if not word:
        raise ValueError("English word is required")
    completed = subprocess.run(
        ["espeak-ng", "-q", "--ipa=3", "-v", "en-us", word],
        capture_output=True,
        check=False,
        text=True,
        timeout=3,
    )
    if completed.returncode != 0:
        raise ValueError("Unable to generate pronunciation")
    phonemes = parse_espeak_ipa(completed.stdout)
    return {
        "id": word,
        "word": word,
        "translation": "",
        "category": "专项训练",
        "ipa": f"/{''.join(phonemes)}/",
        "phonemes": phonemes,
        "focus": [],
    }
