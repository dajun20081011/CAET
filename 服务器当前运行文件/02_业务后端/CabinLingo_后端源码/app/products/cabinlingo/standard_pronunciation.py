from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from time import sleep
from typing import Any, Callable, Iterable
from uuid import uuid4

from pypinyin import Style, lazy_pinyin
from pypinyin.contrib.mmseg import seg

from ...integrations.pronunciation import (
    builtin_pronunciations,
    normalize_pronunciation_text,
    provider_pronunciations,
    resolve_pronunciations,
)


_CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_ENGLISH_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


@dataclass(frozen=True)
class StandardPronunciationToken:
    text: str
    start: int
    end: int
    pinyin: str
    source: str
    confidence: str


@dataclass(frozen=True)
class CachedStandardAudio:
    data: bytes
    content_type: str
    token: StandardPronunciationToken
    cache_key: str
    cache_hit: bool


def pronunciation_snapshot(entries: Iterable[dict[str, Any]]) -> tuple[str, str]:
    values = list(entries)
    builtin_version = str(builtin_pronunciations()[0].get("dictionary_version") or "unknown")
    serialized = json.dumps([
        {
            "phrase": item.get("phrase"), "pinyin": item.get("pinyin"),
            "source": item.get("source"), "enabled": item.get("enabled", True),
            "priority": item.get("priority", 100), "updated_at": str(item.get("updated_at") or ""),
        }
        for item in values
    ], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return builtin_version, sha256(serialized.encode("utf-8")).hexdigest()


def resolve_standard_tokens(text: str, entries: Iterable[dict[str, Any]]) -> tuple[str, list[StandardPronunciationToken]]:
    normalized = normalize_pronunciation_text(text)
    values = list(entries)
    resolutions = resolve_pronunciations(normalized, values)
    preferred: list[StandardPronunciationToken] = []
    occupied = [False] * len(normalized)
    for resolution in resolutions:
        for start, end in resolution.occurrences:
            if any(occupied[start:end]):
                continue
            preferred.append(StandardPronunciationToken(
                text=resolution.phrase, start=start, end=end, pinyin=resolution.pinyin,
                source=resolution.source, confidence=resolution.confidence,
            ))
            occupied[start:end] = [True] * (end - start)

    tokens = list(preferred)
    for match in _CHINESE_RE.finditer(normalized):
        chunk = match.group(0)
        contextual = lazy_pinyin(
            chunk, style=Style.TONE3, neutral_tone_with_five=True, errors="ignore",
        )
        cursor = 0
        for word in seg.cut(chunk):
            local_start, local_end = cursor, cursor + len(word)
            cursor = local_end
            start, end = match.start() + local_start, match.start() + local_end
            if not word or any(occupied[start:end]):
                continue
            syllables = contextual[local_start:local_end]
            tokens.append(StandardPronunciationToken(
                text=word, start=start, end=end, pinyin=" ".join(syllables),
                source="context", confidence="predicted",
            ))
            occupied[start:end] = [True] * (end - start)

    for match in _ENGLISH_RE.finditer(normalized):
        if any(occupied[match.start():match.end()]):
            continue
        tokens.append(StandardPronunciationToken(
            text=match.group(0), start=match.start(), end=match.end(), pinyin="",
            source="provider", confidence="confirmed",
        ))
    return normalized, sorted(tokens, key=lambda item: (item.start, item.end))


def choose_standard_token(
    tokens: list[StandardPronunciationToken], selected_text: str, reference_index: int | None = None,
) -> StandardPronunciationToken:
    selected = selected_text.strip()
    if reference_index is not None and 0 <= reference_index < len(tokens):
        candidate = tokens[reference_index]
        if selected in candidate.text or candidate.text in selected:
            return candidate
    exact = [item for item in tokens if item.text.casefold() == selected.casefold()]
    if exact:
        return exact[0]
    containing = [item for item in tokens if selected and selected in item.text]
    if containing:
        return min(containing, key=lambda item: len(item.text))
    pinyin = " ".join(lazy_pinyin(
        selected, style=Style.TONE3, neutral_tone_with_five=True, errors="ignore",
    )) if _CHINESE_RE.fullmatch(selected) else ""
    return StandardPronunciationToken(
        text=selected, start=0, end=len(selected), pinyin=pinyin,
        source="context" if pinyin else "provider", confidence="predicted" if pinyin else "confirmed",
    )


def _cache_key(*, token: StandardPronunciationToken, language: str, model: str, voice: str,
               rate: float, dictionary_signature: str) -> str:
    payload = json.dumps({
        "text": token.text, "pinyin": token.pinyin, "language": language,
        "model": model, "voice": voice, "rate": rate,
        "dictionary_signature": dictionary_signature,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def standard_audio(
    *, token: StandardPronunciationToken, language: str, model: str, voice: str, rate: float,
    dictionary_signature: str, cache_root: Path,
    synthesize: Callable[..., Any],
) -> CachedStandardAudio:
    cache_key = _cache_key(
        token=token, language=language, model=model, voice=voice, rate=rate,
        dictionary_signature=dictionary_signature,
    )
    audio_path = cache_root / f"{cache_key}.mp3"
    metadata_path = cache_root / f"{cache_key}.json"
    if audio_path.is_file() and audio_path.stat().st_size:
        return CachedStandardAudio(audio_path.read_bytes(), "audio/mpeg", token, cache_key, True)

    cache_root.mkdir(parents=True, exist_ok=True)
    pronunciations = provider_pronunciations(token.text, [{
        "phrase": token.text, "pinyin": token.pinyin, "applied": True,
    }]) if language == "zh" and token.pinyin else []
    result = synthesize(
        text=token.text, voice=voice, language=language, rate=rate,
        audio_format="mp3", pronunciations=pronunciations,
    )
    temporary = cache_root / f"{cache_key}.{uuid4().hex}.tmp"
    temporary.write_bytes(result.data)
    temporary.replace(audio_path)
    metadata_path.write_text(json.dumps({
        "cache_key": cache_key, "token": asdict(token), "language": language,
        "model": model, "voice": voice, "rate": rate,
        "dictionary_signature": dictionary_signature,
        "content_type": result.content_type, "request_id": result.request_id,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return CachedStandardAudio(result.data, result.content_type, token, cache_key, False)


def warm_standard_audio_cache(
    *, text: str, language: str, entries: Iterable[dict[str, Any]], model: str, voice: str,
    rate: float, cache_root: Path, synthesize: Callable[..., Any], max_unique_tokens: int = 500,
) -> dict[str, Any]:
    entry_values = list(entries)
    normalized, tokens = resolve_standard_tokens(text, entry_values)
    dictionary_version, dictionary_signature = pronunciation_snapshot(entry_values)
    all_unique: list[StandardPronunciationToken] = []
    seen: set[tuple[str, str]] = set()
    for token in tokens:
        key = (token.text.casefold(), token.pinyin)
        if key in seen:
            continue
        seen.add(key)
        all_unique.append(token)
    unique = all_unique[:max_unique_tokens]

    manifest_dir = cache_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    context_hash = sha256(normalized.encode("utf-8")).hexdigest()
    manifest_path = manifest_dir / f"{context_hash}.json"
    manifest: dict[str, Any] = {
        "context_hash": context_hash, "dictionary_version": dictionary_version,
        "dictionary_signature": dictionary_signature, "model": model, "voice": voice,
        "rate": rate, "language": language, "token_count": len(tokens),
        "unique_token_count": len(unique), "truncated": len(all_unique) > len(unique), "items": [],
    }
    for token in unique:
        try:
            cached = standard_audio(
                token=token, language=language, model=model, voice=voice, rate=rate,
                dictionary_signature=dictionary_signature, cache_root=cache_root,
                synthesize=synthesize,
            )
            manifest["items"].append({
                **asdict(token), "cache_key": cached.cache_key,
                "status": "cached" if cached.cache_hit else "generated",
            })
            if not cached.cache_hit:
                sleep(0.4)
        except Exception as exc:
            manifest["items"].append({**asdict(token), "status": "failed", "error": str(exc)[:300]})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
