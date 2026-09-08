from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class SecurityEventType(str, enum.Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    PHISHING_ANALYSIS = "PHISHING_ANALYSIS"
    FRAUD_ANALYSIS = "FRAUD_ANALYSIS"


class SecurityRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEvent(UUIDPKMixin, Base):
    __tablename__ = "security_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True)

    event_type: Mapped[SecurityEventType] = mapped_column(
        SAEnum(SecurityEventType, name="security_event_type"), nullable=False, index=True
    )
    risk_level: Mapped[SecurityRiskLevel] = mapped_column(
        SAEnum(SecurityRiskLevel, name="security_risk_level"), default=SecurityRiskLevel.LOW, nullable=False
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 to 100

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_summary: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g., "London, UK" or "Localhost"

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
