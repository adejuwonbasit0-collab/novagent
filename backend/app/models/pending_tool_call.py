from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PendingToolCall(UUIDPKMixin, TimestampMixin, Base):
    """
    A tool call the orchestration engine proposed that BaseTool.execute()
    flagged as requiring confirmation (spec section 5: 'Do not allow the AI
    to execute unrestricted... simply because an LLM generated them').

    The LLM's plan is never trusted to self-approve — this row is the only
    way a high-risk tool call actually runs, and only a subsequent, explicit
    user action against THIS row (POST /api/v1/assistant/confirm/{id})
    executes it. Short-lived by design so a stale confirmation can't fire
    unexpectedly later.
    """

    __tablename__ = "pending_tool_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True)

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)  # shown to the user before they confirm

    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
