import uuid
from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ToolCallOut(BaseModel):
    tool_name: str
    result: str
    data: dict[str, Any] = {}
    message: str | None = None
    error: str | None = None
    pending_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallOut] = []


class ConfirmResponse(BaseModel):
    tool_name: str
    result: str
    data: dict[str, Any] = {}
    message: str | None = None
    error: str | None = None
