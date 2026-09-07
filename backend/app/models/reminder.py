from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class RecurrenceType(str, enum.Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"  # interpreted via recurrence_rule (cron-like string)


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class Reminder(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "reminders"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    due_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")  # IANA tz name, e.g. "Africa/Lagos"

    recurrence_type: Mapped[RecurrenceType] = mapped_column(
        SAEnum(RecurrenceType, name="recurrence_type"), default=RecurrenceType.NONE
    )
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus, name="reminder_status"), default=ReminderStatus.PENDING, index=True
    )

    snoozed_until: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notify_desktop: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_sound: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="reminders")
