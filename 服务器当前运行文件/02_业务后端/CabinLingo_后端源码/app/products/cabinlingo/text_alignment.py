from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


_TOKEN_RE = re.compile(
    r"[A-Za-zＡ-Ｚａ-ｚ]+(?:['’][A-Za-zＡ-Ｚａ-ｚ]+)?|"
    r"[0-9０-９]+(?:[.:：．][0-9０-９]+)?|[\u3400-\u9fff]"
)


def _normalized_token(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().replace("’", "'")


def tokenize_text(value: str | None) -> list[dict[str, Any]]:
    """Tokenize English by word and Chinese by character, retaining source text."""
    if not isinstance(value, str):
        return []
    return [
        {
            "text": match.group(0),
            "normalized": _normalized_token(match.group(0)),
            "start_char": match.start(),
            "end_char": match.end(),
        }
        for match in _TOKEN_RE.finditer(value)
    ]


def _recognized_timings(
    transcript_tokens: list[dict[str, Any]],
    iat_tokens: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    """Bind provider token starts without manufacturing per-word precision."""
    if not isinstance(iat_tokens, list):
        return {}

    provider_parts: list[dict[str, Any]] = []
    for provider_index, item in enumerate(iat_tokens):
        if not isinstance(item, dict):
            continue
        parts = tokenize_text(str(item.get("text") or ""))
        for part_index, part in enumerate(parts):
            provider_parts.append({
                "normalized": part["normalized"],
                # ws.bg is the start of the provider unit. When that unit contains
                # several logical words/characters, only its first part inherits it.
                "start_ms": item.get("start_ms") if part_index == 0 else None,
                "provider_bg": item.get("provider_bg") if part_index == 0 else None,
                "confidence": item.get("confidence") if part_index == 0 else None,
                "provider_fields": item.get("provider_fields") if part_index == 0 else None,
                "provider_index": provider_index,
            })

    transcript_values = [item["normalized"] for item in transcript_tokens]
    provider_values = [item["normalized"] for item in provider_parts]
    timings: dict[int, dict[str, Any]] = {}
    for tag, i1, i2, j1, j2 in SequenceMatcher(
        a=transcript_values,
        b=provider_values,
        autojunk=False,
    ).get_opcodes():
        if tag != "equal":
            continue
        for offset in range(i2 - i1):
            provider = provider_parts[j1 + offset]
            start_ms = provider.get("start_ms")
            timings[i1 + offset] = {
                "start_ms": start_ms if isinstance(start_ms, int) and not isinstance(start_ms, bool) else None,
                "provider_bg": provider.get("provider_bg"),
                "confidence": provider.get("confidence"),
                "provider_fields": provider.get("provider_fields"),
                "iat_token_index": provider["provider_index"],
            }
    return timings


def align_text(
    reference_text: str | None,
    transcript: str | None,
    iat_tokens: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Align official text and IAT transcript as text evidence.

    The result intentionally describes text differences only. It must not be
    interpreted as pronunciation scoring; Suntone remains the pronunciation
    authority.
    """
    reference_tokens = tokenize_text(reference_text)
    recognized_tokens = tokenize_text(transcript)
    reference_values = [item["normalized"] for item in reference_tokens]
    recognized_values = [item["normalized"] for item in recognized_tokens]
    timings = _recognized_timings(recognized_tokens, iat_tokens)
    alignment: list[dict[str, Any]] = []

    def append(
        alignment_type: str,
        reference_index: int | None,
        recognized_index: int | None,
    ) -> None:
        reference = reference_tokens[reference_index] if reference_index is not None else None
        recognized = recognized_tokens[recognized_index] if recognized_index is not None else None
        timing = timings.get(recognized_index, {}) if recognized_index is not None else {}
        alignment.append({
            "type": alignment_type,
            "reference": reference["text"] if reference else None,
            "recognized": recognized["text"] if recognized else None,
            "start_ms": timing.get("start_ms"),
            "provider_bg": timing.get("provider_bg"),
            "confidence": timing.get("confidence"),
            "provider_fields": timing.get("provider_fields"),
            "iat_token_index": timing.get("iat_token_index"),
            "reference_index": reference_index,
            "recognized_index": recognized_index,
            "normalized_reference": reference["normalized"] if reference else None,
            "normalized_recognized": recognized["normalized"] if recognized else None,
        })

    matcher = SequenceMatcher(a=reference_values, b=recognized_values, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                append("matched", i1 + offset, j1 + offset)
            continue
        if tag == "delete":
            for reference_index in range(i1, i2):
                append("omission", reference_index, None)
            continue
        if tag == "insert":
            for recognized_index in range(j1, j2):
                append("insertion", None, recognized_index)
            continue

        # Pair the shared part of a replace block as substitutions. Any tail on
        # either side remains an explicit omission/insertion.
        paired = min(i2 - i1, j2 - j1)
        for offset in range(paired):
            append("substitution", i1 + offset, j1 + offset)
        for reference_index in range(i1 + paired, i2):
            append("omission", reference_index, None)
        for recognized_index in range(j1 + paired, j2):
            append("insertion", None, recognized_index)

    return alignment


def build_alignment_payload(
    reference_text: str | None,
    transcript: str | None,
    iat_tokens: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return alignment plus the unchanged source texts for auditability."""
    return {
        "reference_text": reference_text or "",
        "transcript": transcript or "",
        "alignment": align_text(reference_text, transcript, iat_tokens),
    }
