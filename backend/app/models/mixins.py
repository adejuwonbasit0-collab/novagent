import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
