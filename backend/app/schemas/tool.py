from typing import Any

from pydantic import BaseModel


class ToolExecuteRequest(BaseModel):
    params: dict[str, Any] = {}
    confirmed: bool = False  # set true on the retry after the user confirms a high-risk action


class ToolExecuteResponse(BaseModel):
    result: str
    data: dict[str, Any] = {}
    message: str | None = None
    error: str | None = None
    duration_ms: float | None = None
