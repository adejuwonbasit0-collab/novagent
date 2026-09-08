import logging
import os
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("nova.config")


def _redact_db_url(url: str) -> str:
    """host/db name only — never log credentials, even to a local console."""
    try:
        parts = urlsplit(url)
        netloc = parts.hostname or ""
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    except Exception:
        return "<unparsable DATABASE_URL>"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Nova Assistant Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./nova.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str = "nova_default_dev_jwt_secret_key_change_in_production_32bytes"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEVICE_TOKEN_EXPIRE_DAYS: int = 90

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

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
    resolved = Settings()

    # BUG FIX: pydantic-settings always lets a real OS/shell environment
    # variable win over .env, silently, with zero indication that's what
    # happened. That's normally the right precedence (env vars are meant
    # to override files in prod) -- but in local dev it means a
    # DATABASE_URL left over in a terminal from a DIFFERENT project can
    # quietly point this backend at the wrong database, with every
    # downstream symptom (existing users/devices "not found", 401s, 403s
    # on the device WebSocket) looking like an auth bug instead of what
    # it actually is. This can't stop that precedence -- overriding via
    # env is a legitimate, sometimes required use case (Docker, CI,
    # hosting platforms) -- but it makes the source impossible to miss.
    if "DATABASE_URL" in os.environ:
        logger.warning(
            "DATABASE_URL is set as a real environment variable, not just in "
            ".env -- it will win, ignoring backend/.env's value. If that's "
            "not what you intended (e.g. it's left over from another "
            "project's shell session), clear it and restart: "
            "PowerShell: Remove-Item Env:DATABASE_URL -- "
            "bash/zsh: unset DATABASE_URL"
        )
    # print(), not just logger.info(): this backend has no logging config
    # of its own (uvicorn's default config doesn't apply INFO to loggers
    # it doesn't own), so a plain logger.info() here would silently never
    # be seen on a default run -- and this line is exactly the thing to
    # check first when devices/users that should exist suddenly don't.
    print(f"[nova] Connecting to database: {_redact_db_url(resolved.DATABASE_URL)}")

    return resolved


settings = get_settings()
