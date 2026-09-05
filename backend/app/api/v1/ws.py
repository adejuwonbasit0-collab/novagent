from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import TokenType, decode_token, hash_token
from app.models.device import Device
from app.services.connection_manager import connection_manager

router = APIRouter(tags=["websocket"])


async def _authenticate_device(token: str, db: AsyncSession) -> Device | None:
    """
    Mirrors get_current_device's checks (token type, subject, hash match,
    active status) but standalone rather than a FastAPI dependency —
    WebSocket auth commonly comes via a query param rather than a header
    (browser WebSocket clients can't set Authorization), so this is called
    explicitly after the handshake rather than injected.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != TokenType.DEVICE.value:
        return None

    try:
        device_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if device is None or not device.is_active or device.token_hash != hash_token(token):
        return None

    return device


@router.websocket("/api/v1/ws/device")
async def device_websocket(websocket: WebSocket, token: str):
    """
    Persistent connection for a single desktop-agent device. Once
    connected, backend tools can push commands to this exact device via
    connection_manager.send_command() and await the result — see
    app/tools/system_tools.py for the calling side.

    Protocol (JSON messages, both directions):
      server -> device: {"type": "command", "request_id": str, "tool": str, "params": dict}
      device -> server: {"type": "result", "request_id": str, "success": bool, "message": str|None, "error": str|None}
    """
    async with AsyncSessionLocal() as db:
        device = await _authenticate_device(token, db)

    if device is None:
        await websocket.close(code=4401)  # custom close code — invalid/expired credentials
        return

    await connection_manager.connect(device.id, websocket)

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "result":
                request_id = message.get("request_id")
                if request_id:
                    connection_manager.resolve_result(request_id, message)
            # Other inbound message types (e.g. a device-initiated event,
            # local notification ack) would be handled here as the
            # protocol grows — currently the device is only ever replying
            # to commands the server sent it.
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(device.id)

        # Keep last_seen_at accurate for the device list UI even for
        # connections that never made a REST call during this session.
        async with AsyncSessionLocal() as db2:
            from datetime import datetime, timezone

            result = await db2.execute(select(Device).where(Device.id == device.id))
            d = result.scalar_one_or_none()
            if d:
                d.last_seen_at = datetime.now(timezone.utc)
                await db2.commit()
