from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PermissionScope(str, enum.Enum):
    """Maps to spec section 34 — flat list kept in code, not DB, so adding a
    new permission is a one-line change and doesn't need a migration."""

    FILES_READ = "FILES_READ"
    FILES_WRITE = "FILES_WRITE"
    APP_OPEN = "APP_OPEN"
    APP_CLOSE = "APP_CLOSE"
    BROWSER_READ = "BROWSER_READ"
    BROWSER_CONTROL = "BROWSER_CONTROL"
    EMAIL_SEND = "EMAIL_SEND"
    CALENDAR_READ = "CALENDAR_READ"
    CALENDAR_WRITE = "CALENDAR_WRITE"
    CONTACTS_READ = "CONTACTS_READ"
    CALL_INITIATE = "CALL_INITIATE"
    SYSTEM_LOCK = "SYSTEM_LOCK"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    SCREEN_READ = "SCREEN_READ"
    AUTOMATION_EXECUTE = "AUTOMATION_EXECUTE"
    REMINDERS_MANAGE = "REMINDERS_MANAGE"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Static risk classification — used by the tool layer to decide whether a
# tool call needs interactive confirmation before executing.
PERMISSION_RISK: dict[PermissionScope, RiskLevel] = {
    PermissionScope.FILES_READ: RiskLevel.LOW,
    PermissionScope.FILES_WRITE: RiskLevel.MEDIUM,
    PermissionScope.APP_OPEN: RiskLevel.LOW,
    PermissionScope.APP_CLOSE: RiskLevel.MEDIUM,
    PermissionScope.BROWSER_READ: RiskLevel.LOW,
    PermissionScope.BROWSER_CONTROL: RiskLevel.MEDIUM,
    PermissionScope.EMAIL_SEND: RiskLevel.HIGH,
    PermissionScope.CALENDAR_READ: RiskLevel.LOW,
    PermissionScope.CALENDAR_WRITE: RiskLevel.MEDIUM,
    PermissionScope.CONTACTS_READ: RiskLevel.LOW,
    PermissionScope.CALL_INITIATE: RiskLevel.HIGH,
    PermissionScope.SYSTEM_LOCK: RiskLevel.MEDIUM,
    PermissionScope.SYSTEM_SHUTDOWN: RiskLevel.HIGH,
    PermissionScope.SCREEN_READ: RiskLevel.HIGH,
    PermissionScope.AUTOMATION_EXECUTE: RiskLevel.MEDIUM,
    PermissionScope.REMINDERS_MANAGE: RiskLevel.LOW,
}


class UserPermission(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "scope", name="uq_user_permission_scope"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scope: Mapped[PermissionScope] = mapped_column(SAEnum(PermissionScope, name="permission_scope"), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="permissions")
