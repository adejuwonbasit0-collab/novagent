from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)
    tool_calls_json: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    tool_calls_json: str | None
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", max_length=255)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    is_archived: bool | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    is_archived: bool
    last_message_at: datetime
    created_at: datetime
    message_count: int = 0


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []
