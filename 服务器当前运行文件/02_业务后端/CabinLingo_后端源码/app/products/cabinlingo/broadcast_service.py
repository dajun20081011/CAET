from dataclasses import dataclass
from typing import Any, Sequence


DEFAULT_SLICE_CHARS = 900
MAX_SLICE_CHARS = 1024
NATURAL_BREAKS = frozenset("。！？.!?，, ")
BROADCAST_SCRIPT_TYPE_ALIASES = {
    "常用广播": ("常用广播", "常用", "common", "boarding", "pre_departure"),
    "通用广播": ("通用广播", "通用", "general"),
    "应急广播": ("应急广播", "应急", "emergency"),
    "机场地名": ("机场地名", "机场", "airport", "airport_place"),
}


class BroadcastLibraryError(ValueError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def broadcast_script_type_filter_values(value: str) -> tuple[str, ...]:
    requested = value.strip()
    requested_folded = requested.casefold()
    for canonical, aliases in BROADCAST_SCRIPT_TYPE_ALIASES.items():
        if requested == canonical or any(requested_folded == alias.casefold() for alias in aliases):
            return aliases
    return (requested,)


@dataclass(frozen=True)
class GeneratedSlice:
    text: str
    start_char: int
    end_char: int


def split_broadcast_text(
    full_text: str,
    max_chars: int = DEFAULT_SLICE_CHARS,
    hard_max: int = MAX_SLICE_CHARS,
) -> list[GeneratedSlice]:
    """Split without trimming so concatenation is byte-for-byte equivalent in Python text."""
    if not 1 <= max_chars <= hard_max <= MAX_SLICE_CHARS:
        raise BroadcastLibraryError("max_chars must be between 1 and 1024", 422)
    if not full_text:
        return []

    slices: list[GeneratedSlice] = []
    start = 0
    length = len(full_text)
    while start < length:
        target = min(start + max_chars, length)
        end = target
        if target < length:
            for index in range(target - 1, start - 1, -1):
                if full_text[index] in NATURAL_BREAKS:
                    end = index + 1
                    break
        if end <= start:
            end = min(start + hard_max, length)
        text = full_text[start:end]
        if len(text) > hard_max:
            raise BroadcastLibraryError("Generated slice exceeds 1024 characters", 422)
        slices.append(GeneratedSlice(text=text, start_char=start, end_char=end))
        start = end

    if "".join(item.text for item in slices) != full_text:
        raise RuntimeError("Slice generation integrity check failed")
    return slices


def validate_version_for_freeze(version: dict[str, Any], slices: Sequence[dict[str, Any]]) -> None:
    if version.get("frozen"):
        raise BroadcastLibraryError("Version is already frozen")
    if version.get("slices_stale"):
        raise BroadcastLibraryError("正文已修改，请先重新生成或人工校正切片", 422)
    if not slices:
        raise BroadcastLibraryError("At least one slice is required before freezing", 422)
    expected_numbers = list(range(1, len(slices) + 1))
    actual_numbers = [int(item["slice_no"]) for item in slices]
    if actual_numbers != expected_numbers:
        raise BroadcastLibraryError("Slice numbers must be continuous from 1", 422)
    if any(not bool(item.get("verified")) for item in slices):
        raise BroadcastLibraryError("All slices must be verified before freezing", 422)
    if any(not item.get("text") or len(str(item["text"])) > MAX_SLICE_CHARS for item in slices):
        raise BroadcastLibraryError("Every slice must contain 1 to 1024 characters", 422)
    if "".join(str(item["text"]) for item in slices) != str(version["full_text"]):
        raise BroadcastLibraryError("Slice text does not exactly match the full text", 422)
