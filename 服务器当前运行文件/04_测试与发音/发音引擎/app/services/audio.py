from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from app.core.errors import AudioValidationError


@dataclass(frozen=True)
class ProcessedAudio:
    samples: np.ndarray
    sample_rate: int
    duration_ms: int
    trimmed: bool


def _trim_silence(
    samples: np.ndarray, sample_rate: int, threshold_db: float = -42.0
) -> tuple[np.ndarray, bool]:
    if samples.size == 0:
        return samples, False
    threshold = 10 ** (threshold_db / 20)
    active = np.flatnonzero(np.abs(samples) >= threshold)
    if active.size == 0:
        return samples, False
    pad = int(0.08 * sample_rate)
    start = max(0, int(active[0]) - pad)
    end = min(samples.size, int(active[-1]) + pad + 1)
    trimmed = start > 0 or end < samples.size
    return samples[start:end], trimmed


def preprocess_audio(
    raw: bytes,
    *,
    target_sample_rate: int = 16_000,
    min_seconds: float = 0.25,
    max_seconds: float = 12.0,
) -> ProcessedAudio:
    try:
        samples, sample_rate = sf.read(BytesIO(raw), dtype="float32", always_2d=True)
    except Exception as exc:
        raise AudioValidationError(
            "无法读取音频；请上传 WAV、FLAC 或当前服务器 libsndfile 支持的格式。"
        ) from exc

    if samples.shape[0] == 0 or sample_rate <= 0:
        raise AudioValidationError("音频为空。")

    mono = np.mean(samples, axis=1, dtype=np.float32)
    if not np.isfinite(mono).all():
        raise AudioValidationError("音频包含无效采样值。")

    raw_duration = mono.size / sample_rate
    if raw_duration > max_seconds + 1:
        raise AudioValidationError(f"音频过长；最长允许 {max_seconds:g} 秒。")

    if sample_rate != target_sample_rate:
        gcd = np.gcd(sample_rate, target_sample_rate)
        mono = resample_poly(mono, target_sample_rate // gcd, sample_rate // gcd).astype(np.float32)
        sample_rate = target_sample_rate

    mono, trimmed = _trim_silence(mono, sample_rate)
    duration = mono.size / sample_rate
    if duration < min_seconds:
        raise AudioValidationError(f"有效语音过短；至少需要 {min_seconds:g} 秒。")
    if duration > max_seconds:
        raise AudioValidationError(f"有效语音过长；最长允许 {max_seconds:g} 秒。")

    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono))))
    if peak < 1e-4 or rms < 5e-5:
        raise AudioValidationError("未检测到足够清晰的语音。")
    if peak > 0.99:
        mono = mono / peak * 0.95
    elif peak < 0.10:
        mono = mono / peak * 0.70

    return ProcessedAudio(
        samples=np.ascontiguousarray(mono, dtype=np.float32),
        sample_rate=sample_rate,
        duration_ms=round(duration * 1000),
        trimmed=trimmed,
    )


def write_wav(audio: ProcessedAudio, path: Path) -> None:
    sf.write(path, audio.samples, audio.sample_rate, subtype="PCM_16", format="WAV")
