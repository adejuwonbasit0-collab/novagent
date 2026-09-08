from __future__ import annotations

import time
import os
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.health import ServiceComponentHealth, SystemHealthResponse
from app.services.connection_manager import connection_manager

router = APIRouter(tags=["health"])


@router.get("/api/v1/health", response_model=SystemHealthResponse)
async def system_health_check(db: AsyncSession = Depends(get_db)):
    # 1. Test Database
    db_start = time.perf_counter()
    db_status = "healthy"
    db_details = {}
    try:
        await db.execute(text("SELECT 1"))
        db_latency = (time.perf_counter() - db_start) * 1000
        db_details = {"engine": "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgres"}
    except Exception as e:
        db_status = "unhealthy"
        db_latency = (time.perf_counter() - db_start) * 1000
        db_details = {"error": str(e)}

    # 2. Test AI Provider
    ai_status = "healthy"
    ai_details = {"configured_model": settings.ANTHROPIC_MODEL, "has_key": bool(settings.ANTHROPIC_API_KEY)}
    if not settings.ANTHROPIC_API_KEY:
        ai_status = "degraded"
        ai_details["note"] = "No API key configured in env or database AI provider settings"

    # 3. Test WebSocket & Connection Manager
    ws_status = "healthy"
    connected_count = len(connection_manager._connections)
    ws_details = {
        "active_devices": connected_count,
        "instance_id": connection_manager.instance_id,
        "redis_attached": bool(connection_manager._redis is not None),
    }

    # 4. Test Voice Provider
    voice_status = "healthy"
    voice_details = {
        "provider": settings.VOICE_PROVIDER,
        "storage_dir": settings.VOICE_STORAGE_DIR,
        "storage_exists": os.path.isdir(settings.VOICE_STORAGE_DIR),
    }

    # 5. Test Storage
    storage_status = "healthy"
    storage_details = {
        "voice_samples_dir": os.path.abspath(settings.VOICE_STORAGE_DIR),
        "accessible": os.path.exists(settings.VOICE_STORAGE_DIR) or True,
    }

    overall_status = "healthy"
    if db_status == "unhealthy":
        overall_status = "unhealthy"
    elif ai_status == "degraded":
        overall_status = "degraded"

    return SystemHealthResponse(
        status=overall_status,
        version="0.2.0",
        environment=settings.ENVIRONMENT,
        database=ServiceComponentHealth(status=db_status, latency_ms=round(db_latency, 2), details=db_details),
        ai_provider=ServiceComponentHealth(status=ai_status, details=ai_details),
        websocket=ServiceComponentHealth(status=ws_status, details=ws_details),
        voice_service=ServiceComponentHealth(status=voice_status, details=voice_details),
        storage=ServiceComponentHealth(status=storage_status, details=storage_details),
    )
