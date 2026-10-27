import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class AlignmentItem:
    expected: str | None
    observed: str | None
    operation: str


_EQUIVALENT = {
    "g": "ɡ",
    "r": "ɹ",
    "ɚ": "ɝ",
    "ɜ": "ɝ",
    "ɜː": "ɝ",
    "əː": "ɜː",
    "ə": "ʌ",
    "ɐ": "ʌ",
    "ɑ": "ɑː",
    "a": "ɑː",
    "ɔ": "ɔː",
    "e": "ɛ",
    "ᵻ": "ɪ",
    "i": "iː",
    "o": "oʊ",
    "əʊ": "oʊ",
    "u": "uː",
}


def normalize_phone(phone: str) -> str:
    value = unicodedata.normalize("NFC", phone.strip()).replace("ˈ", "").replace("ˌ", "")
    return _EQUIVALENT.get(value, value)


def align_phones(expected: list[str], observed: list[str]) -> list[AlignmentItem]:
    """Needleman-Wunsch edit alignment with deterministic tie breaking."""
    left = [normalize_phone(item) for item in expected]
    right = [normalize_phone(item) for item in observed]
    rows, cols = len(left) + 1, len(right) + 1
    cost = [[0] * cols for _ in range(rows)]
    back = [[""] * cols for _ in range(rows)]
    for i in range(1, rows):
        cost[i][0], back[i][0] = i, "delete"
    for j in range(1, cols):
        cost[0][j], back[0][j] = j, "insert"

    for i in range(1, rows):
        for j in range(1, cols):
            same = left[i - 1] == right[j - 1]
            candidates = [
                (cost[i - 1][j - 1] + (0 if same else 1), "match" if same else "substitute"),
                (cost[i - 1][j] + 1, "delete"),
                (cost[i][j - 1] + 1, "insert"),
            ]
            cost[i][j], back[i][j] = min(candidates, key=lambda item: item[0])

    aligned: list[AlignmentItem] = []
    i, j = len(left), len(right)
    while i or j:
        op = back[i][j]
        if op in {"match", "substitute"}:
            aligned.append(AlignmentItem(left[i - 1], right[j - 1], op))
            i -= 1
            j -= 1
        elif op == "delete":
            aligned.append(AlignmentItem(left[i - 1], None, op))
            i -= 1
        else:
            aligned.append(AlignmentItem(None, right[j - 1], "insert"))
            j -= 1
    return list(reversed(aligned))


def observed_for_expected(alignment: list[AlignmentItem]) -> list[str | None]:
    return [item.observed for item in alignment if item.expected is not None]
