from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), default=UserStatus.ACTIVE, nullable=False
    )
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False)

    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Assistant identity/config (kept flat here; grows into its own table when
    # personality/voice config expands beyond a handful of fields).
    assistant_name: Mapped[str] = mapped_column(String(100), default="Nova")

    devices: Mapped[list["Device"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    permissions: Mapped[list["UserPermission"]] = relationship(back_populates="user", cascade="all, delete-orphan")
