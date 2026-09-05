from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path.home() / ".nova-assistant"
CONFIG_DIR.mkdir(exist_ok=True)

DEVICE_STATE_FILE = CONFIG_DIR / "device.json"  # device_id + non-secret metadata only; token lives in keyring


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BACKEND_URL: str = "http://localhost:8000"
    ASSISTANT_NAME: str = "Nova"
    VOICE_LANGUAGE: str = "en-US"  # e.g. en-US, en-GB, fr-FR, es-ES, yo-NG
    START_WITH_OS: bool = False
    THEME: str = "dark"  # "dark" | "light"
    BUBBLE_SIZE: int = 64


settings = AgentSettings()
