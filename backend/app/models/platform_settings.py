from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PlatformSettings(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "platform_settings"

    assistant_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Nova")