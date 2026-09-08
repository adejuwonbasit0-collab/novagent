from __future__ import annotations

import asyncio
import json
import logging

import websockets
from PySide6.QtCore import QObject, Signal
from websockets.exceptions import ConnectionClosed, InvalidStatus

from config import settings
from core.device_store import DeviceStore
from os_control.base import OSActionResult, OSController, get_controller

logger = logging.getLogger("nova.ws_client")

# Status codes the backend's handshake can reject with. /api/v1/ws/device
# (see backend/app/api/v1/ws.py) never calls websocket.accept() when
# _authenticate_device() returns None — it closes immediately instead —
# and uvicorn reports an un-accepted WebSocket as a plain HTTP rejection
# in that case, which the client sees as InvalidStatus, not a clean
# close code. Any rejection on THIS endpoint means the token is dead
# (wrong/rotated/points at a device row that no longer exists), not a
# transient network issue, so it gets handled differently below.
_AUTH_REJECTED_STATUS_CODES = {401, 403}

# Maps tool names the backend can dispatch to the OSController method that
# actually performs them. Kept as an explicit table rather than getattr()
# on arbitrary tool names, so an unrecognized/renamed tool fails loudly
# instead of silently trying to call a method that doesn't exist.
_TOOL_DISPATCH = {
    "shutdown_computer": lambda ctl, params: ctl.shutdown_computer(),
    "lock_computer": lambda ctl, params: ctl.lock_computer(),
    "restart_computer": lambda ctl, params: ctl.restart_computer(),
    "take_screenshot": lambda ctl, params: ctl.take_screenshot(),
    "show_desktop": lambda ctl, params: ctl.show_desktop(),
    "open_application": lambda ctl, params: ctl.open_application(params["app_name"]),
    "open_url": lambda ctl, params: ctl.open_url(params["url"]),
    "open_folder": lambda ctl, params: ctl.open_folder(params["path"]),
    "create_folder": lambda ctl, params: ctl.create_folder(params["path"]),
    "create_file": lambda ctl, params: ctl.create_file(params["path"], params.get("content", "")),
    "rename_file": lambda ctl, params: ctl.rename_file(params["old_path"], params["new_path"]),
    "delete_file": lambda ctl, params: ctl.delete_file(params["path"]),
    "type_text": lambda ctl, params: ctl.type_text(params["text"]),
    "open_folder_in_application": lambda ctl, params: ctl.open_folder_in_application(params["path"], params["app_name"]),
    "get_active_window": lambda ctl, params: ctl.get_active_window(),
    "read_file": lambda ctl, params: ctl.read_file(params["path"], params.get("max_chars", 20000)),
}


def _ws_url(base_url: str, token: str) -> str:
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.split("://", 1)[-1]
    return f"{scheme}://{host}/api/v1/ws/device?token={token}"


class DeviceWebSocketClient(QObject):
    """
    Maintains the persistent connection described in spec section 3 — the
    channel that lets the cloud backend actually reach this machine's OS,
    which a plain web request never could. Reconnects with backoff on
    disconnect; each incoming command is executed via OSController and
    acknowledged with a result message correlated by request_id.

    BUG FIX — a rejected handshake (401/403: bad, rotated, or orphaned
    device token — e.g. the device row it points to no longer exists in
    whatever database the backend is currently pointed at) used to be
    treated exactly like a transient network blip: log a warning, back
    off, retry the SAME dead token forever. It can never succeed on its
    own, so the agent would sit there logging "connection failed" in an
    infinite loop with no way out short of the user manually finding and
    deleting device.json. Now: on a 401/403 specifically, the stale
    credential is cleared and device_rejected fires so the app can put
    the user straight back into onboarding to get a fresh one.
    """

    device_rejected = Signal()
    config_updated = Signal(dict)

    def __init__(self, controller: OSController | None = None):
        super().__init__()
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
            except InvalidStatus as e:
                if e.response.status_code in _AUTH_REJECTED_STATUS_CODES:
                    logger.warning(
                        "Device token rejected (HTTP %d) — this device is no longer "
                        "recognized by the backend. Clearing it and asking to re-pair "
                        "instead of retrying a token that can never work.",
                        e.response.status_code,
                    )
                    DeviceStore.clear()
                    self.device_rejected.emit()
                    backoff = 2  # next loop iteration finds no token and just waits
                else:
                    logger.warning("WebSocket connection failed: %s", e)
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

            msg_type = message.get("type")
            if msg_type == "config_updated":
                config_data = message.get("config", {})
                self.config_updated.emit(config_data)
                continue

            if msg_type != "command":
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
