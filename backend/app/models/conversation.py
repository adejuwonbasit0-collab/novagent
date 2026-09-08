from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Conversation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Conversation")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
