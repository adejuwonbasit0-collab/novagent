from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class DevicePlatform(str, enum.Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    BROWSER_EXTENSION = "browser_extension"
    MOBILE = "mobile"


class Device(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(SAEnum(DevicePlatform, name="device_platform"), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # flips false on revoke
    last_seen_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Hash of the device token, never the raw token — mirrors password storage practice.
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship(back_populates="devices")
