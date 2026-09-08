import uuid
from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    # BUG FIX: nothing anywhere told the model what the current date/time
    # actually is. Every "create_reminder" call requires an absolute
    # due_at datetime (backend/app/tools/reminder_tools.py), but a request
    # like "remind me at 6 AM" or "in 20 minutes" is meaningless without
    # knowing what time it is NOW, in the user's own timezone -- the model
    # would have to guess, and it has no reliable way to guess right
    # (it doesn't know today's date, let alone the user's offset). This
    # is an ISO 8601 timestamp WITH UTC offset, e.g.
    # "2026-09-07T14:32:00-04:00" -- the client's own local wall-clock
    # time, not UTC. Optional so older/other clients that don't send it
    # yet don't break; the model is told explicitly when it's missing
    # rather than silently guessing.
    client_local_time: str | None = None


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
