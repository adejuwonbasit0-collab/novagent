from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Nova Assistant Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEVICE_TOKEN_EXPIRE_DAYS: int = 90

    CORS_ORIGINS: str = "http://localhost:3000"

    # --- AI orchestration ---
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    PENDING_CONFIRMATION_TTL_MINUTES: int = 5

    # --- Voice training/synthesis ---
    VOICE_PROVIDER: str = "mock"  # "mock" | "elevenlabs"
    ELEVENLABS_API_KEY: str | None = None
    VOICE_STORAGE_DIR: str = "./data/voice_samples"
    MAX_VOICE_SAMPLE_BYTES: int = 25 * 1024 * 1024  # 25MB per sample

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
