from __future__ import annotations

import asyncio
import json
import logging

import websockets
from websockets.exceptions import ConnectionClosed

from config import settings
from core.device_store import DeviceStore
from os_control.base import OSActionResult, OSController, get_controller

logger = logging.getLogger("nova.ws_client")

# Maps tool names the backend can dispatch to the OSController method that
# actually performs them. Kept as an explicit table rather than getattr()
# on arbitrary tool names, so an unrecognized/renamed tool fails loudly
# instead of silently trying to call a method that doesn't exist.
_TOOL_DISPATCH = {
    "shutdown_computer": lambda ctl, params: ctl.shutdown_computer(),
    "lock_computer": lambda ctl, params: ctl.lock_computer(),
    "restart_computer": lambda ctl, params: ctl.restart_computer(),
    "open_application": lambda ctl, params: ctl.open_application(params["app_name"]),
    "open_url": lambda ctl, params: ctl.open_url(params["url"]),
    "open_folder": lambda ctl, params: ctl.open_folder(params["path"]),
    "create_folder": lambda ctl, params: ctl.create_folder(params["path"]),
    "create_file": lambda ctl, params: ctl.create_file(params["path"], params.get("content", "")),
    "type_text": lambda ctl, params: ctl.type_text(params["text"]),
    "open_folder_in_application": lambda ctl, params: ctl.open_folder_in_application(params["path"], params["app_name"]),
}


def _ws_url(base_url: str, token: str) -> str:
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.split("://", 1)[-1]
    return f"{scheme}://{host}/api/v1/ws/device?token={token}"


class DeviceWebSocketClient:
    """
    Maintains the persistent connection described in spec section 3 — the
    channel that lets the cloud backend actually reach this machine's OS,
    which a plain web request never could. Reconnects with backoff on
    disconnect; each incoming command is executed via OSController and
    acknowledged with a result message correlated by request_id.
    """

    def __init__(self, controller: OSController | None = None):
        self._controller = controller or get_controller()
        self._stop = False

    async def run_forever(self) -> None:
        backoff = 2
        while not self._stop:
            token = DeviceStore.get_token()
            if token is None:
                await asyncio.sleep(backoff)
                continue

            try:
                url = _ws_url(settings.BACKEND_URL, token)
                async with websockets.connect(url) as ws:
                    logger.info("Connected to backend WebSocket")
                    backoff = 2  # reset after a successful connect
                    await self._listen(ws)
            except ConnectionClosed:
                logger.warning("WebSocket disconnected — reconnecting")
            except Exception as e:
                logger.warning("WebSocket connection failed: %s", e)

            if not self._stop:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def stop(self) -> None:
        self._stop = True

    async def _listen(self, ws) -> None:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if message.get("type") != "command":
                continue

            await self._handle_command(ws, message)

    async def _handle_command(self, ws, message: dict) -> None:
        request_id = message.get("request_id")
        tool_name = message.get("tool")
        params = message.get("params", {})

        handler = _TOOL_DISPATCH.get(tool_name)
        if handler is None:
            await self._send_result(ws, request_id, OSActionResult(success=False, message="", error=f"Unsupported tool: {tool_name}"))
            return

        try:
            # OSController methods are synchronous (subprocess/OS calls) —
            # run off the event loop so a slow OS call doesn't block the
            # WebSocket's ability to receive/send other messages.
            result = await asyncio.to_thread(handler, self._controller, params)
        except Exception as e:
            result = OSActionResult(success=False, message="", error=str(e))

        await self._send_result(ws, request_id, result)

    async def _send_result(self, ws, request_id: str | None, result: OSActionResult) -> None:
        await ws.send(
            json.dumps(
                {
                    "type": "result",
                    "request_id": request_id,
                    "success": result.success,
                    "message": result.message,
                    "error": result.error,
                }
            )
        )
