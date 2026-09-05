import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.audit_log import AuditLog as AuditLogModel
from app.models.device import DevicePlatform
from app.models.user import UserRole, UserStatus


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    status: UserStatus
    role: UserRole
    is_email_verified: bool
    created_at: datetime
    device_count: int

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    status: UserStatus | None = None
    role: UserRole | None = None


class AdminDeviceOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    name: str
    platform: DevicePlatform
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime


class AdminAuditLogOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None
    device_id: uuid.UUID | None
    action: str
    resource: str | None
    result: str
    metadata_json: dict[str, Any] | None
    created_at: datetime


class AdminStatsOut(BaseModel):
    total_users: int
    active_users: int
    suspended_users: int
    total_devices: int
    active_devices: int
    total_reminders: int
    audit_log_count_last_24h: int
