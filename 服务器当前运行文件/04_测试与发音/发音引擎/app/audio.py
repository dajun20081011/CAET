from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np


SAMPLE_RATE = 16_000


class AudioError(ValueError):
    pass


def decode_audio(path: Path, max_seconds: float) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required but was not found")
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            str(max_seconds + 0.5),
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-",
        ],
        capture_output=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise AudioError(detail or "无法解析录音")
    waveform = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if waveform.size == 0:
        raise AudioError("录音为空")
    if waveform.size / SAMPLE_RATE > max_seconds:
        raise AudioError(f"录音不能超过 {max_seconds:g} 秒")
    if not np.isfinite(waveform).all():
        raise AudioError("录音包含无效采样")
    return waveform


def prepare_waveform(waveform: np.ndarray) -> np.ndarray:
    waveform = waveform.astype(np.float32, copy=False)
    waveform -= float(waveform.mean())
    peak = float(np.max(np.abs(waveform)))
    rms = float(np.sqrt(np.mean(np.square(waveform))))
    if peak < 0.005 or rms < 0.0005:
        raise AudioError("没有检测到清晰语音，请靠近麦克风重试")

    threshold = max(0.004, peak * 0.04)
    active = np.flatnonzero(np.abs(waveform) >= threshold)
    if active.size:
        margin = int(0.08 * SAMPLE_RATE)
        start = max(0, int(active[0]) - margin)
        end = min(waveform.size, int(active[-1]) + margin + 1)
        waveform = waveform[start:end]
    if waveform.size < int(0.18 * SAMPLE_RATE):
        raise AudioError("录音过短，请完整读出单词")

    # Short CTC inputs can lose their first/last phone; a small silent margin fixes it.
    waveform = np.pad(waveform, (4_000, 4_000))
    variance = float(np.var(waveform))
    return ((waveform - float(np.mean(waveform))) / np.sqrt(variance + 1e-7)).astype(np.float32)

