from __future__ import annotations

import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDPKMixin


class AuditLog(UUIDPKMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "OPEN_APPLICATION"
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "Chrome"
    result: Mapped[str] = mapped_column(String(20), nullable=False)  # SUCCESS | FAILURE | DENIED

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
