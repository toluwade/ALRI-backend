from __future__ import annotations

from pydantic import model_validator
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

    ENVIRONMENT: str = "development"  # development | production

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.JWT_SECRET == "change-me":
            raise ValueError(
                "JWT_SECRET must be set to a strong, unique value in production. "
                "Do not use the default 'change-me'."
            )
        return self

    CLERK_SECRET_KEY: str | None = None
    CLERK_PUBLISHABLE_KEY: str | None = None
    CLERK_WEBHOOK_SECRET: str | None = None

    # LLM
    LLM_PROVIDER: str = "kimi"  # kimi | claude
    NVIDIA_NIM_API_KEY: str | None = None
    NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    KIMI_MODEL: str = "moonshotai/kimi-k2-instruct"

    # OCR — PaddleOCR runs locally, no API key needed

    # Email (Resend)
    RESEND_API_KEY: str | None = None
    RESEND_FROM_HELLO: str = "hello@alri.health"
    RESEND_FROM_BILLING: str = "billing@alri.health"

    # Payments (Paystack)
    PAYSTACK_SECRET_KEY: str | None = None
    PAYSTACK_PUBLIC_KEY: str | None = None
    PAYSTACK_WEBHOOK_SECRET: str | None = None

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

    # Pricing (all in kobo — ₦1 = 100 kobo)
    PRICE_SCAN_UNLOCK_KOBO: int = 20_000       # ₦200
    PRICE_CHAT_MESSAGE_KOBO: int = 5_000        # ₦50
    PRICE_SKIN_ANALYSIS_KOBO: int = 25_000      # ₦250
    PRICE_VOICE_TRANSCRIPTION_KOBO: int = 10_000  # ₦100
    INITIAL_SIGNUP_BONUS_KOBO: int = 500_000    # ₦5,000

    # Chat tier limits
    CHAT_CHAR_LIMIT_FREE: int = 150
    CHAT_CHAR_LIMIT_PAID: int = 250
    CHAT_MSG_LIMIT_FREE: int = 5

    # Speech-to-text (Groq preferred — free + faster; OpenAI Whisper as fallback)
    GROQ_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None


settings = Settings()
