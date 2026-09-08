from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class ServiceComponentHealth(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: float | None = None
    details: dict[str, Any] = {}


class SystemHealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    environment: str
    database: ServiceComponentHealth
    ai_provider: ServiceComponentHealth
    websocket: ServiceComponentHealth
    voice_service: ServiceComponentHealth
    storage: ServiceComponentHealth
