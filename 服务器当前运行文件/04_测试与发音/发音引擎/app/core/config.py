from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "CabinLingo Pronunciation Engine"
    app_env: str = "development"
    engine_backend: str = "mock"
    device: str = "auto"
    model_dir: Path = Path("models")
    preload_models: bool = False
    allow_custom_text: bool = False
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_audio_seconds: float = Field(default=12.0, ge=1.0, le=60.0)
    min_audio_seconds: float = Field(default=0.25, ge=0.05, le=5.0)
    target_sample_rate: int = 16_000
    pherr_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    weak_score_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    cors_origins: str = "http://localhost:8000"
    api_key: str | None = None
    hf_token: str | None = None
    wavlm_repo_id: str = "Jianshu001/wavlm-phoneme-scorer"
    wavlm_revision: str = "19f6b9675d02a61dcd5b2aec0fdcc4364c1fc9da"
    wavlm_checkpoint: str = "wavlm_finetuned.pt"
    wavlm_checkpoint_sha256: str = (
        "7b9485b679d9a1219ac7dbef197b5185ec16e7909632b082b1f0576a963e0040"
    )
    wavlm_base_model_id: str = "microsoft/wavlm-large"
    wavlm_base_revision: str = "c1423ed94bb01d80a3f5ce5bc39f6026a0f4828c"
    ctc_model_id: str = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
    ctc_revision: str = "2c733782da5604684829819a5eb744c193fe9398"

    @field_validator("api_key", "hf_token", mode="before")
    @classmethod
    def empty_secret_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("engine_backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"mock", "wavlm"}:
            raise ValueError("ENGINE_BACKEND must be 'mock' or 'wavlm'")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
