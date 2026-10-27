from dataclasses import dataclass
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "CAET Learning Platform API")
    app_version: str = os.getenv("APP_VERSION", "1.0.0-production-candidate")
    environment: str = os.getenv("APP_ENV", "development").strip().lower()
    database_url: str = os.getenv("DATABASE_URL", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_issuer: str = os.getenv("JWT_ISSUER", "cabinlingo-api")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "cabinlingo-web")
    jwt_ttl_seconds: int = _int("JWT_TTL_SECONDS", 3600)
    enable_demo_seed: bool = _bool("ENABLE_DEMO_SEED", False)
    upload_dir: str = os.getenv("UPLOAD_DIR", "/uploads")
    audio_max_bytes: int = _int("AUDIO_MAX_BYTES", 25 * 1024 * 1024)
    course_media_max_bytes: int = _int("COURSE_MEDIA_MAX_BYTES", 100 * 1024 * 1024)
    tencent_cos_enabled: bool = _bool("TENCENT_COS_ENABLED", False)
    tencent_cos_secret_id: str = os.getenv("TENCENT_COS_SECRET_ID", "")
    tencent_cos_secret_key: str = os.getenv("TENCENT_COS_SECRET_KEY", "")
    tencent_cos_security_token: str = os.getenv("TENCENT_COS_SECURITY_TOKEN", "")
    tencent_cos_cvm_role_name: str = os.getenv("TENCENT_COS_CVM_ROLE_NAME", "").strip()
    tencent_cos_region: str = os.getenv("TENCENT_COS_REGION", "").strip()
    tencent_cos_bucket: str = os.getenv("TENCENT_COS_BUCKET", "").strip()
    tencent_cos_prefix: str = os.getenv("TENCENT_COS_PREFIX", "expression-skills/").strip().lstrip("/")
    tencent_cos_fallback_video_keys: tuple[str, ...] = _csv("TENCENT_COS_FALLBACK_VIDEO_KEYS")
    tencent_cos_signed_url_ttl_seconds: int = _int("TENCENT_COS_SIGNED_URL_TTL_SECONDS", 900)
    allowed_origins: tuple[str, ...] = _csv("ALLOWED_ORIGINS")
    ai_settings_master_key: str = os.getenv("AI_SETTINGS_MASTER_KEY", "")

    qwen_tts_enabled: bool = _bool("QWEN_TTS_ENABLED", False)
    qwen_tts_endpoint: str = os.getenv(
        "QWEN_TTS_ENDPOINT",
        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
    ).strip()
    qwen_tts_api_key: str = os.getenv("QWEN_TTS_API_KEY", "")
    qwen_tts_workspace_id: str = os.getenv("QWEN_TTS_WORKSPACE_ID", "").strip()
    qwen_tts_model: str = os.getenv("QWEN_TTS_MODEL", "qwen-audio-3.0-tts-flash").strip()
    qwen_tts_voices: str = os.getenv(
        "QWEN_TTS_VOICES",
        "longanfengyue|龙安风悦|zh+en;longanyuanfei|龙安元妃|zh+en;"
        "longanlingxi|龙安灵希|zh+en;longanxiaoxin|龙安小昕|zh+en;"
        "longanhuan_v3.6|龙安欢|zh+en;longjielidou_v3.6|龙杰力豆|zh+en;"
        "longpaopao_v3.6|龙泡泡|zh+en;longhuohuo_v3.6|龙火火|zh+en;"
        "longchuanshu_v3.6|龙川叔|zh+en;loongmary|Mary|en;"
        "loongeva_v3.6|Eva|en;loongjohn|John|en",
    ).strip()
    qwen_tts_voice_profiles: str = os.getenv("QWEN_TTS_VOICE_PROFILES", "").strip()
    qwen_tts_timeout_seconds: float = _float("QWEN_TTS_TIMEOUT_SECONDS", 90)
    qwen_tts_max_text_chars: int = _int("QWEN_TTS_MAX_TEXT_CHARS", 5000)
    qwen_tts_max_audio_bytes: int = _int("QWEN_TTS_MAX_AUDIO_BYTES", 25 * 1024 * 1024)

    ai_gateway_enabled: bool = _bool("AI_GATEWAY_ENABLED", False)
    ai_required_adapters: tuple[str, ...] = _csv("AI_REQUIRED_ADAPTERS", "suntone")
    ai_timeout_seconds: float = _float("AI_TIMEOUT_SECONDS", 15)
    ai_max_retries: int = _int("AI_MAX_RETRIES", 1)
    ai_backoff_seconds: float = _float("AI_BACKOFF_SECONDS", 0.25)
    ai_audio_transport: str = os.getenv("AI_AUDIO_TRANSPORT", "base64").strip().lower()
    ai_audio_max_bytes: int = _int("AI_AUDIO_MAX_BYTES", 15 * 1024 * 1024)
    audio_transcode_enabled: bool = _bool("AUDIO_TRANSCODE_ENABLED", True)
    audio_transcode_binary: str = os.getenv("AUDIO_TRANSCODE_BINARY", "ffmpeg").strip()
    audio_transcode_timeout_seconds: float = _float("AUDIO_TRANSCODE_TIMEOUT_SECONDS", 30)
    audio_transcode_max_seconds: int = _int("AUDIO_TRANSCODE_MAX_SECONDS", 300)
    audio_transcode_max_output_bytes: int = _int("AUDIO_TRANSCODE_MAX_OUTPUT_BYTES", 12 * 1024 * 1024)

    asr_iat_endpoint: str = os.getenv("ASR_IAT_ENDPOINT", "").strip()
    asr_iat_api_key: str = os.getenv("ASR_IAT_API_KEY", "")
    asr_iat_app_id: str = os.getenv("ASR_IAT_APP_ID", "").strip()
    asr_iat_api_secret: str = os.getenv("ASR_IAT_API_SECRET", "")
    asr_iat_provider: str = os.getenv("ASR_IAT_PROVIDER", "asr_iat_http").strip()
    asr_iat_version: str = os.getenv("ASR_IAT_VERSION", "v1").strip()
    asr_iat_score_scale: float = _float("ASR_IAT_SCORE_SCALE", 100)
    asr_iat_language: str = os.getenv("ASR_IAT_LANGUAGE", "en_us").strip()
    asr_iat_domain: str = os.getenv("ASR_IAT_DOMAIN", "iat").strip()
    asr_iat_accent: str = os.getenv("ASR_IAT_ACCENT", "mandarin").strip()
    asr_iat_sample_rate: int = _int("ASR_IAT_SAMPLE_RATE", 16000)

    ise_endpoint: str = os.getenv("ISE_ENDPOINT", "").strip()
    ise_api_key: str = os.getenv("ISE_API_KEY", "")
    ise_app_id: str = os.getenv("ISE_APP_ID", "").strip()
    ise_api_secret: str = os.getenv("ISE_API_SECRET", "")
    ise_provider: str = os.getenv("ISE_PROVIDER", "ise_http").strip()
    ise_version: str = os.getenv("ISE_VERSION", "v1").strip()
    ise_score_scale: float = _float("ISE_SCORE_SCALE", 100)
    ise_ent: str = os.getenv("ISE_ENT", "en_vip").strip()
    ise_category: str = os.getenv("ISE_CATEGORY", "read_chapter").strip()
    ise_sample_rate: int = _int("ISE_SAMPLE_RATE", 16000)

    suntone_endpoint: str = os.getenv("SUNTONE_ENDPOINT", "").strip()
    suntone_app_id: str = os.getenv("SUNTONE_APP_ID", "").strip()
    suntone_api_key: str = os.getenv("SUNTONE_API_KEY", "")
    suntone_api_secret: str = os.getenv("SUNTONE_API_SECRET", "")
    suntone_provider: str = os.getenv("SUNTONE_PROVIDER", "xfyun_suntone").strip()
    suntone_version: str = os.getenv("SUNTONE_VERSION", "v1").strip()
    suntone_score_scale: float = _float("SUNTONE_SCORE_SCALE", 100)
    suntone_language: str = os.getenv("SUNTONE_LANGUAGE", "en").strip()
    suntone_core: str = os.getenv("SUNTONE_CORE", "para").strip()
    suntone_dialect: str = os.getenv("SUNTONE_DIALECT", "en_us").strip()
    suntone_encoded_audio_max_bytes: int = _int("SUNTONE_ENCODED_AUDIO_MAX_BYTES", 7 * 1024 * 1024)

    object_storage_mode: str = os.getenv("OBJECT_STORAGE_MODE", "local").strip().lower()
    object_storage_endpoint: str = os.getenv("OBJECT_STORAGE_ENDPOINT", "").strip()
    object_storage_bucket: str = os.getenv("OBJECT_STORAGE_BUCKET", "").strip()
    object_storage_api_key: str = os.getenv("OBJECT_STORAGE_API_KEY", "")
    object_storage_timeout_seconds: float = _float("OBJECT_STORAGE_TIMEOUT_SECONDS", 15)
    object_storage_max_retries: int = _int("OBJECT_STORAGE_MAX_RETRIES", 1)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_runtime(self) -> None:
        if self.ai_settings_master_key and len(self.ai_settings_master_key) < 32:
            raise RuntimeError("AI_SETTINGS_MASTER_KEY must contain at least 32 characters")
        supported_adapters = {"asr_iat", "ise", "suntone"}
        unknown = set(self.ai_required_adapters) - supported_adapters
        if unknown:
            raise RuntimeError(f"Unsupported AI_REQUIRED_ADAPTERS: {', '.join(sorted(unknown))}")
        if self.ai_audio_transport not in {"base64", "reference"}:
            raise RuntimeError("AI_AUDIO_TRANSPORT must be base64 or reference")
        if self.object_storage_mode not in {"local", "presigned_http"}:
            raise RuntimeError("OBJECT_STORAGE_MODE must be local or presigned_http")
        if not self.audio_transcode_binary or self.audio_transcode_timeout_seconds <= 0 or self.audio_transcode_max_seconds <= 0:
            raise RuntimeError("Audio transcoder settings are invalid")
        if self.audio_transcode_max_output_bytes <= 44:
            raise RuntimeError("AUDIO_TRANSCODE_MAX_OUTPUT_BYTES is invalid")
        if self.suntone_language not in {"cn", "en", "kr", "fr", "de", "ru", "sp", "jp"}:
            raise RuntimeError("SUNTONE_LANGUAGE is invalid")
        if self.suntone_core not in {"word", "sent", "para"}:
            raise RuntimeError("SUNTONE_CORE is invalid")
        if self.suntone_encoded_audio_max_bytes <= 64 or self.suntone_encoded_audio_max_bytes > 7 * 1024 * 1024:
            raise RuntimeError("SUNTONE_ENCODED_AUDIO_MAX_BYTES is invalid")
        if self.ai_gateway_enabled:
            missing = [name for name in self.ai_required_adapters if not getattr(self, f"{name}_endpoint")]
            if missing:
                raise RuntimeError(f"Missing AI provider endpoints: {', '.join(missing)}")
            credential_fields = {
                "asr_iat": ("asr_iat_app_id", "asr_iat_api_key", "asr_iat_api_secret"),
                "ise": ("ise_app_id", "ise_api_key", "ise_api_secret"),
                "suntone": ("suntone_app_id", "suntone_api_key", "suntone_api_secret"),
            }
            incomplete = [name for name in self.ai_required_adapters
                          if getattr(self, f"{name}_endpoint").lower().startswith(("ws://", "wss://"))
                          and not all(getattr(self, field) for field in credential_fields[name])]
            if incomplete:
                raise RuntimeError(f"Missing AI provider credentials: {', '.join(incomplete)}")
        if self.object_storage_mode == "presigned_http" and (not self.object_storage_endpoint or not self.object_storage_bucket):
            raise RuntimeError("OBJECT_STORAGE_ENDPOINT and OBJECT_STORAGE_BUCKET are required for presigned_http")
        if self.tencent_cos_enabled:
            if not self.tencent_cos_region or not self.tencent_cos_bucket:
                raise RuntimeError("Tencent COS region and bucket are required when enabled")
            if not self.tencent_cos_cvm_role_name and not (self.tencent_cos_secret_id and self.tencent_cos_secret_key):
                raise RuntimeError("Tencent COS CVM role or credentials are required when enabled")
            if not self.tencent_cos_prefix or ".." in self.tencent_cos_prefix.split("/"):
                raise RuntimeError("TENCENT_COS_PREFIX is invalid")
            if not 60 <= self.tencent_cos_signed_url_ttl_seconds <= 3600:
                raise RuntimeError("TENCENT_COS_SIGNED_URL_TTL_SECONDS must be between 60 and 3600")
        if self.qwen_tts_enabled:
            if not self.qwen_tts_api_key:
                raise RuntimeError("QWEN_TTS_API_KEY is required when QWEN_TTS_ENABLED=true")
            if not self.qwen_tts_endpoint and not self.qwen_tts_workspace_id:
                raise RuntimeError("QWEN_TTS_ENDPOINT is required")
            if self.qwen_tts_timeout_seconds <= 0 or self.qwen_tts_max_text_chars < 1:
                raise RuntimeError("Qwen TTS limits are invalid")
            if not 1024 <= self.qwen_tts_max_audio_bytes <= 100 * 1024 * 1024:
                raise RuntimeError("QWEN_TTS_MAX_AUDIO_BYTES is invalid")
        if self.is_production:
            if not self.database_url:
                raise RuntimeError("DATABASE_URL is required in production")
            if len(self.jwt_secret) < 32:
                raise RuntimeError("JWT_SECRET must contain at least 32 characters in production")
            if self.enable_demo_seed:
                raise RuntimeError("ENABLE_DEMO_SEED must be false in production")
            if not self.allowed_origins:
                raise RuntimeError("ALLOWED_ORIGINS is required in production")
            if not self.upload_dir.startswith("/"):
                raise RuntimeError("UPLOAD_DIR must be an absolute path in production")


settings = Settings()
