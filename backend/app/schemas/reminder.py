import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.reminder import RecurrenceType, ReminderStatus


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)
    due_at: datetime
    timezone: str = "UTC"
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_rule: str | None = None
    notify_desktop: bool = True
    notify_sound: bool = True


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
    due_at: datetime | None = None
    status: ReminderStatus | None = None
    snoozed_until: datetime | None = None


class ReminderOut(BaseModel):
    id: uuid.UUID
    title: str
    notes: str | None
    due_at: datetime
    timezone: str
    recurrence_type: RecurrenceType
    status: ReminderStatus
    snoozed_until: datetime | None
    completed_at: datetime | None
    notify_desktop: bool
    notify_sound: bool
    created_at: datetime

    class Config:
        from_attributes = True
