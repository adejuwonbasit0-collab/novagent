import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.device import DevicePlatform


class DeviceRegister(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    platform: DevicePlatform
    app_version: str | None = None


class DeviceRegisterResponse(BaseModel):
    device_id: uuid.UUID
    device_token: str  # returned once, at registration — never persisted or re-shown


class DeviceRename(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    platform: DevicePlatform
    app_version: str | None
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
