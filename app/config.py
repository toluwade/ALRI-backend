from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://alri:password@db:5432/alri"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24 * 30  # 30 days

    GOOGLE_CLIENT_ID: str | None = None

    # LLM
    LLM_PROVIDER: str = "kimi"  # kimi | claude
    NVIDIA_NIM_API_KEY: str | None = None
    NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    KIMI_MODEL: str = "moonshotai/kimi-k2-instruct"

    # OCR
    GOOGLE_VISION_API_KEY: str | None = None

    # WhatsApp
    WHATSAPP_TOKEN: str | None = None
    WHATSAPP_VERIFY_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None

    # Storage
    STORAGE_TYPE: str = "local"  # local | s3
    STORAGE_PATH: str = "/data/uploads"

    # App
    APP_URL: str = "https://alri.health"
    CORS_ORIGINS: str = "https://alri.health,http://localhost:3000"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60


settings = Settings()
