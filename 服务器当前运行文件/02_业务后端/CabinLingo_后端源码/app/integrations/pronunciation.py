from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Iterable

from pypinyin import Style, lazy_pinyin, pinyin
from pypinyin.contrib.mmseg import seg


_CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_PINYIN_RE = re.compile(r"^[a-züv]+[1-5]$", re.IGNORECASE)
_MAX_RESOLUTIONS = 80
_AUTO_POLYPHONE_CHARS = frozenset(
    "夹尽行重乐长调降着空系还为转好发处供藏恶血将朝差省便都强薄似数假觉结载角间种应答落说"
)
_PROSODY_TAG_RE = re.compile(
    r"\[(?:亲切|平稳|提醒|关切|严肃|紧迫|明确|稍慢|中速|稍快)\]"
)
_PROVIDER_NATURAL_PRONUNCIATION_PHRASES = frozenset({"为了"})


class PronunciationError(ValueError):
    pass


@dataclass(frozen=True)
class PronunciationResolution:
    phrase: str
    pinyin: str
    source: str
    confidence: str
    note: str
    occurrences: tuple[tuple[int, int], ...]
    applied: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase,
            "pinyin": self.pinyin,
            "source": self.source,
            "confidence": self.confidence,
            "note": self.note,
            "occurrences": [{"start": start, "end": end} for start, end in self.occurrences],
            "applied": self.applied,
        }


def validate_pronunciation(phrase: str, numbered_pinyin: str) -> tuple[str, str]:
    clean_phrase = phrase.strip()
    clean_pinyin = " ".join(numbered_pinyin.strip().lower().replace("u:", "v").split())
    if not clean_phrase or len(clean_phrase) > 40 or not _CHINESE_RE.fullmatch(clean_phrase):
        raise PronunciationError("词语必须为 1–40 个汉字")
    syllables = clean_pinyin.split()
    if len(syllables) != len(clean_phrase):
        raise PronunciationError("拼音数量必须与汉字数量一致")
    if any(not _PINYIN_RE.fullmatch(item) for item in syllables):
        raise PronunciationError("拼音必须使用带数字声调格式，例如 jia1 feng4")
    return clean_phrase, clean_pinyin


def normalize_pronunciation_text(text: str) -> str:
    """Remove CabinLingo broadcast controls while preserving spoken characters."""
    normalized = _PROSODY_TAG_RE.sub("", text)
    normalized = re.sub(r"【([^【】]+)】", r"\1", normalized)
    normalized = normalized.replace("【", "").replace("】", "")
    normalized = re.sub(r"/{1,3}", " ", normalized)
    normalized = normalized.translate(str.maketrans("", "", "↑↓→"))
    return re.sub(r"\s+", " ", normalized).strip()


@lru_cache(maxsize=1)
def builtin_pronunciations() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parents[1] / "data" / "aviation_pronunciation_lexicon.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = str(payload.get("version") or "unknown")
    result = []
    for index, item in enumerate(payload.get("entries") or []):
        phrase, numbered = validate_pronunciation(str(item.get("phrase") or ""), str(item.get("pinyin") or ""))
        result.append({
            "id": f"builtin-{index + 1}", "phrase": phrase, "pinyin": numbered,
            "note": str(item.get("note") or ""), "enabled": True, "priority": 100,
            "source": "builtin", "dictionary_version": version, "editable": False,
        })
    return tuple(result)


def merge_pronunciations(overrides: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {item["phrase"]: dict(item) for item in builtin_pronunciations()}
    for raw in overrides:
        phrase, numbered = validate_pronunciation(str(raw.get("phrase") or ""), str(raw.get("pinyin") or ""))
        previous = merged.get(phrase)
        merged[phrase] = {
            "id": str(raw.get("id") or ""), "phrase": phrase, "pinyin": numbered,
            "note": str(raw.get("note") or ""), "enabled": bool(raw.get("enabled", True)),
            "priority": int(raw.get("priority") or 100), "source": "manual",
            "dictionary_version": "manual", "editable": True,
            "overrides_builtin": bool(previous and previous.get("source") == "builtin"),
            "updated_at": raw.get("updated_at"),
        }
    return sorted(merged.values(), key=lambda item: (-int(item["priority"]), -len(item["phrase"]), item["phrase"]))


def _is_polyphonic(char: str) -> bool:
    values = pinyin(char, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True, errors="ignore")
    return bool(values and len(set(values[0])) > 1)


def _context_tokens(chunk: str) -> list[tuple[str, int, int]]:
    tokens = []
    cursor = 0
    for token in seg.cut(chunk):
        start = cursor
        cursor += len(token)
        tokens.append((token, start, cursor))
    return tokens


def resolve_pronunciations(text: str, entries: Iterable[dict[str, Any]]) -> list[PronunciationResolution]:
    if not text.strip():
        return []
    entries = list(entries)
    occupied = [False] * len(text)
    resolutions: list[PronunciationResolution] = []
    seen: dict[str, int] = {}

    # A disabled manual override is an explicit instruction to leave the phrase to
    # the provider. Keep context inference from silently adding it again.
    for item in entries:
        if item.get("enabled") or item.get("source") != "manual":
            continue
        phrase = str(item.get("phrase") or "")
        cursor = 0
        while phrase:
            start = text.find(phrase, cursor)
            if start < 0:
                break
            end = start + len(phrase)
            occupied[start:end] = [True] * (end - start)
            cursor = end

    # Longest phrase wins before administrator priority. This prevents a high
    # priority single-character entry from masking a verified aviation phrase.
    for item in sorted((value for value in entries if value.get("enabled")),
                       key=lambda value: (-len(str(value.get("phrase") or "")),
                                          -int(value.get("priority") or 100))):
        phrase = str(item.get("phrase") or "")
        if not phrase or phrase not in text:
            continue
        occurrences = []
        cursor = 0
        while True:
            start = text.find(phrase, cursor)
            if start < 0:
                break
            end = start + len(phrase)
            cursor = end
            if not any(occupied[start:end]):
                occurrences.append((start, end))
                occupied[start:end] = [True] * (end - start)
        if occurrences:
            seen[phrase] = len(resolutions)
            resolutions.append(PronunciationResolution(
                phrase=phrase, pinyin=str(item["pinyin"]), source=str(item.get("source") or "builtin"),
                confidence="confirmed", note=str(item.get("note") or ""), occurrences=tuple(occurrences),
            ))

    for match in _CHINESE_RE.finditer(text):
        chunk = match.group(0)
        contextual = lazy_pinyin(chunk, style=Style.TONE3, neutral_tone_with_five=True, errors="ignore")
        if len(contextual) != len(chunk):
            continue
        for token, local_start, local_end in _context_tokens(chunk):
            start, end = match.start() + local_start, match.start() + local_end
            if (any(occupied[start:end])
                    or not any(char in _AUTO_POLYPHONE_CHARS and _is_polyphonic(char) for char in token)):
                continue
            if len(token) == 1:
                window_start = max(0, local_start - 1)
                window_end = min(len(chunk), local_end + 1)
                token = chunk[window_start:window_end]
                start, end = match.start() + window_start, match.start() + window_end
                if any(occupied[start:end]):
                    continue
                syllables = contextual[window_start:window_end]
            else:
                syllables = contextual[local_start:local_end]
            try:
                phrase, numbered = validate_pronunciation(token, " ".join(syllables))
            except PronunciationError:
                continue
            if phrase in seen:
                current = resolutions[seen[phrase]]
                if current.pinyin == numbered:
                    combined = tuple(sorted(set((*current.occurrences, (start, end)))))
                    resolutions[seen[phrase]] = PronunciationResolution(
                        phrase=current.phrase, pinyin=current.pinyin, source=current.source,
                        confidence=current.confidence, note=current.note, occurrences=combined,
                        applied=current.applied,
                    )
                continue
            occupied[start:end] = [True] * (end - start)
            seen[phrase] = len(resolutions)
            resolutions.append(PronunciationResolution(
                phrase=phrase, pinyin=numbered, source="context", confidence="predicted",
                note="系统根据当前句子自动判断，请在生成前试听确认", occurrences=((start, end),),
            ))
            if len(resolutions) >= _MAX_RESOLUTIONS:
                return resolutions
    return resolutions


def provider_pronunciations(text: str, items: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    occupied = [False] * len(text)
    for item in sorted(items, key=lambda value: -len(str(value.get("phrase") or ""))):
        if not item.get("applied", True):
            continue
        phrase, numbered = validate_pronunciation(str(item.get("phrase") or ""), str(item.get("pinyin") or ""))
        # Qwen's public hot-fix contract does not define a neutral-tone marker.
        # Sending "为了": "wei4 le5" has produced an incorrect syllable in
        # production, while the model reads this common phrase correctly from
        # context. Keep it out of hot_fix even if context inference finds it or
        # an old/manual dictionary entry still exists.
        if phrase in _PROVIDER_NATURAL_PRONUNCIATION_PHRASES:
            continue
        if phrase not in text or phrase in seen:
            continue
        occurrences: list[tuple[int, int]] = []
        cursor = 0
        while True:
            start = text.find(phrase, cursor)
            if start < 0:
                break
            end = start + len(phrase)
            cursor = end
            if not any(occupied[start:end]):
                occurrences.append((start, end))
        if not occurrences:
            continue
        for start, end in occurrences:
            occupied[start:end] = [True] * (end - start)
        seen.add(phrase)
        result.append({phrase: numbered})
        if len(result) >= _MAX_RESOLUTIONS:
            break
    return result


class PronunciationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def list(self) -> list[dict[str, Any]]:
        if not self.database_url:
            return []
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id::text, phrase, pinyin, note, enabled, priority, updated_at
                           FROM cl_tts_pronunciations ORDER BY priority DESC, length(phrase) DESC, phrase""")
            return [dict(row) for row in cur.fetchall()]

    def upsert(self, *, phrase: str, numbered_pinyin: str, note: str, enabled: bool,
               priority: int, actor_id: str) -> dict[str, Any]:
        phrase, numbered_pinyin = validate_pronunciation(phrase, numbered_pinyin)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cl_tts_pronunciations
                     (phrase,pinyin,note,enabled,priority,created_by,updated_by,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,now())
                   ON CONFLICT(phrase) DO UPDATE SET pinyin=EXCLUDED.pinyin,note=EXCLUDED.note,
                     enabled=EXCLUDED.enabled,priority=EXCLUDED.priority,updated_by=EXCLUDED.updated_by,updated_at=now()
                   RETURNING id::text,phrase,pinyin,note,enabled,priority,updated_at""",
                (phrase, numbered_pinyin, note.strip(), enabled, priority, actor_id, actor_id),
            )
            row = dict(cur.fetchone())
            cur.execute(
                """INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                   VALUES (%s,'cabinlingo','tts_pronunciation.updated','tts_pronunciation',%s::uuid,
                           jsonb_build_object('phrase',%s::text,'enabled',%s::boolean))""",
                (actor_id, row["id"], phrase, enabled),
            )
            return row

    def delete(self, entry_id: str, actor_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cl_tts_pronunciations WHERE id=%s RETURNING id,phrase", (entry_id,))
            row = cur.fetchone()
            if not row:
                return False
            cur.execute(
                """INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                   VALUES (%s,'cabinlingo','tts_pronunciation.deleted','tts_pronunciation',%s::uuid,
                           jsonb_build_object('phrase',%s::text))""",
                (actor_id, row["id"], row["phrase"]),
            )
            return True
