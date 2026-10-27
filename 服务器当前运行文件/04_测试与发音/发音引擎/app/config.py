from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    model_path: Path = Path(os.getenv("MODEL_PATH", ROOT / "models" / "model_q4.onnx"))
    vocab_path: Path = Path(os.getenv("VOCAB_PATH", ROOT / "models" / "vocab.json"))
    word_bank_path: Path = Path(os.getenv("WORD_BANK_PATH", ROOT / "data" / "words.json"))
    model_preload: bool = _boolean("MODEL_PRELOAD", True)
    onnx_intra_threads: int = int(os.getenv("ONNX_INTRA_THREADS", "2"))
    max_concurrent_assessments: int = int(os.getenv("MAX_CONCURRENT_ASSESSMENTS", "1"))
    max_audio_bytes: int = int(os.getenv("MAX_AUDIO_BYTES", str(3 * 1024 * 1024)))
    max_audio_seconds: float = float(os.getenv("MAX_AUDIO_SECONDS", "5"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()
    )


settings = Settings()

