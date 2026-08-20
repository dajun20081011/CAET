# ============================================================
# CAET 后端配置 — 使用 pydantic-settings 从 .env 读取
# ============================================================
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库（异步 asyncpg）
    DATABASE_URL: str = ""

    # Redis（轻量接入：会话/简单缓存/AI 预留；不可用时自动降级）
    REDIS_URL: str = "redis://caet-redis:6379/0"
    CACHE_TTL_SECONDS: int = 300

    # JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS：逗号分隔的前端来源（生产由 .env 的 CORS_ORIGINS 覆盖，此处仅为占位默认值）
    CORS_ORIGINS: str = "https://crew.cabinvoice.cn"

    # 首次部署初始化管理员
    INIT_ADMIN_EMAIL: str = ""
    INIT_ADMIN_PASSWORD: str = ""
    INIT_ADMIN_NAME: str = "管理员"

    # 上传目录
    UPLOAD_DIR: str = "./uploads"

    # 服务监听
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL must be configured")
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
