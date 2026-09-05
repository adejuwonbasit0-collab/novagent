from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class AIProvider(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    GROQ = "groq"
    GEMINI = "gemini"
    CUSTOM = "custom"


class AIProviderSettings(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ai_provider_settings"

    provider: Mapped[AIProvider] = mapped_column(
        SAEnum(AIProvider, name="ai_provider"), default=AIProvider.ANTHROPIC, nullable=False
    )
    model: Mapped[str] = mapped_column(String(150), nullable=False, default="claude-sonnet-4-20250514")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)