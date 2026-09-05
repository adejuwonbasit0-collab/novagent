from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import settings

logger = logging.getLogger("nova.connection_manager")


class DeviceNotConnected(Exception):
    pass


class CommandTimeout(Exception):
    pass


@dataclass
class _PendingCommand:
    future: asyncio.Future


# TTL on the Redis device-location key. Refreshed on connect; deleted on
# clean disconnect. The TTL exists as a safety net for the unclean-shutdown
# case (process killed, network partition) so a stale mapping doesn't
# claim a device is reachable on an instance that's actually gone.
DEVICE_LOCATION_TTL_SECONDS = 120
CROSS_INSTANCE_COMMAND_TIMEOUT_PADDING = 3.0  # local dispatch already has its own timeout; this covers Redis round-trip


class DeviceConnectionManager:
    """
    Tracks one live WebSocket per connected device and lets backend code
    (tools, in particular) send a command to a specific device and await
    its result — the mechanism spec section 3 requires ("a website cannot
    directly control a user's operating system", hence a persistent
    connection out to the device that CAN).

    Single-instance fast path: if the target device is connected to THIS
    process, send_command() dispatches directly over its in-memory
    WebSocket reference — identical to the original single-process design,
    no Redis round-trip involved.

    Multi-instance path: every instance publishes {device_id -> instance_id}
    to Redis on connect (with a TTL refreshed periodically) and removes it
    on disconnect. When send_command() is called for a device that isn't
    connected locally, it looks up which instance the device IS connected
    to, forwards the command over a Redis pub/sub channel scoped to that
    instance, and awaits the reply on a shared results channel — the
    owning instance does the actual local dispatch and publishes the
    result back. This is what makes a command work correctly regardless of
    which backend replica happens to receive the REST request.
    """

    def __init__(self):
        self.instance_id = str(uuid.uuid4())
        self._connections: dict[uuid.UUID, WebSocket] = {}
        self._pending: dict[str, _PendingCommand] = {}          # local WS dispatch (device -> this instance)
        self._cross_instance_pending: dict[str, _PendingCommand] = {}  # commands forwarded to another instance

        self._redis = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    # ---- lifecycle ----

    async def start(self) -> None:
        """Call once at app startup (see main.py lifespan). Connects to
        Redis and starts the background listener for commands forwarded
        to this instance and results forwarded back to it. Safe to skip
        in single-process/local-dev use — send_command()'s local fast path
        works without Redis at all; only cross-instance dispatch needs it."""
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3.0,
                socket_timeout=5.0,
            )
            await asyncio.wait_for(self._redis.ping(), timeout=3.0)
        except Exception as e:
            logger.warning("Redis unavailable (%s) — falling back to single-instance mode only", e)
            self._redis = None
            return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(f"nova:commands:{self.instance_id}")
        await self._pubsub.psubscribe("nova:results:*")

        self._listener_task = asyncio.create_task(self._listen())
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        for task in (self._listener_task, self._heartbeat_task):
            if task:
                task.cancel()
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()

    async def _heartbeat(self) -> None:
        """Refreshes the TTL on every locally-connected device's Redis
        location entry, so a long-lived connection doesn't have its
        mapping expire out from under it."""
        while True:
            await asyncio.sleep(DEVICE_LOCATION_TTL_SECONDS / 3)
            for device_id in list(self._connections.keys()):
                try:
                    await self._redis.set(
                        f"nova:device_location:{device_id}", self.instance_id, ex=DEVICE_LOCATION_TTL_SECONDS
                    )
                except Exception:
                    pass  # best-effort — a missed heartbeat just means a shorter effective TTL

    async def _listen(self) -> None:
        async for message in self._pubsub.listen():
            if message["type"] not in ("message", "pmessage"):
                continue
            try:
                payload = json.loads(message["data"])
            except (TypeError, json.JSONDecodeError):
                continue

            channel = message.get("channel", "")
            if channel == f"nova:commands:{self.instance_id}":
                asyncio.create_task(self._handle_forwarded_command(payload))
            elif channel.startswith("nova:results:"):
                self._resolve_cross_instance(payload)

    async def _handle_forwarded_command(self, payload: dict[str, Any]) -> None:
        """Another instance forwarded a command for a device that's
        actually connected here. Dispatch it locally (this instance owns
        the real WebSocket) and publish the result back."""
        request_id = payload["request_id"]
        device_id = uuid.UUID(payload["device_id"])

        try:
            result = await self._dispatch_local(device_id, payload["tool"], payload["params"], payload["timeout"])
            outcome = {"request_id": request_id, "ok": True, "result": result}
        except DeviceNotConnected:
            outcome = {"request_id": request_id, "ok": False, "error": "not_connected"}
        except CommandTimeout:
            outcome = {"request_id": request_id, "ok": False, "error": "timeout"}
        except Exception as e:
            outcome = {"request_id": request_id, "ok": False, "error": str(e)}

        await self._redis.publish(f"nova:results:{request_id}", json.dumps(outcome))

    def _resolve_cross_instance(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        pending = self._cross_instance_pending.get(request_id)
        if pending and not pending.future.done():
            pending.future.set_result(payload)

    # ---- connection registry ----

    async def connect(self, device_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[device_id] = websocket
        if self._redis:
            try:
                await self._redis.set(
                    f"nova:device_location:{device_id}", self.instance_id, ex=DEVICE_LOCATION_TTL_SECONDS
                )
            except Exception:
                pass  # local dispatch on this instance still works without Redis

    async def disconnect(self, device_id: uuid.UUID) -> None:
        self._connections.pop(device_id, None)
        if self._redis:
            try:
                # Only clear the mapping if it still points to us — avoids
                # a race where this device already reconnected to a
                # different instance before this disconnect handler ran.
                current = await self._redis.get(f"nova:device_location:{device_id}")
                if current == self.instance_id:
                    await self._redis.delete(f"nova:device_location:{device_id}")
            except Exception:
                pass

    def is_connected(self, device_id: uuid.UUID) -> bool:
        return device_id in self._connections

    # ---- dispatch ----

    async def _dispatch_local(
        self, device_id: uuid.UUID, tool_name: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        websocket = self._connections.get(device_id)
        if websocket is None:
            raise DeviceNotConnected(f"Device {device_id} has no active connection on this instance")

        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = _PendingCommand(future=future)

        try:
            await websocket.send_json(
                {"type": "command", "request_id": request_id, "tool": tool_name, "params": params}
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise CommandTimeout(f"Device {device_id} did not respond to '{tool_name}' within {timeout}s")
        finally:
            self._pending.pop(request_id, None)

    async def send_command(
        self, device_id: uuid.UUID, tool_name: str, params: dict[str, Any], timeout: float = 15.0
    ) -> dict[str, Any]:
        # Fast path: device is connected right here — identical to the
        # original single-process behavior, no Redis involved.
        if device_id in self._connections:
            return await self._dispatch_local(device_id, tool_name, params, timeout)

        if self._redis is None:
            raise DeviceNotConnected(f"Device {device_id} has no active connection")

        target_instance = await self._redis.get(f"nova:device_location:{device_id}")
        if not target_instance or target_instance == self.instance_id:
            # Either genuinely not connected anywhere, or Redis says it's
            # "here" but it isn't in our local dict (stale entry) — both
            # cases mean we can't reach it.
            raise DeviceNotConnected(f"Device {device_id} has no active connection")

        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._cross_instance_pending[request_id] = _PendingCommand(future=future)

        try:
            await self._redis.publish(
                f"nova:commands:{target_instance}",
                json.dumps(
                    {"request_id": request_id, "device_id": str(device_id), "tool": tool_name, "params": params, "timeout": timeout}
                ),
            )
            outcome = await asyncio.wait_for(future, timeout=timeout + CROSS_INSTANCE_COMMAND_TIMEOUT_PADDING)
        except asyncio.TimeoutError:
            raise CommandTimeout(f"Device {device_id} (on another instance) did not respond to '{tool_name}' in time")
        finally:
            self._cross_instance_pending.pop(request_id, None)

        if not outcome["ok"]:
            if outcome["error"] == "not_connected":
                raise DeviceNotConnected(f"Device {device_id} has no active connection")
            if outcome["error"] == "timeout":
                raise CommandTimeout(f"Device {device_id} did not respond to '{tool_name}' within {timeout}s")
            raise RuntimeError(outcome["error"])

        return outcome["result"]

    def resolve_result(self, request_id: str, payload: dict[str, Any]) -> None:
        """Called from the WebSocket endpoint's receive loop when a
        directly-connected device sends back a {"type": "result", ...}
        message — wakes up the waiting _dispatch_local() call."""
        pending = self._pending.get(request_id)
        if pending and not pending.future.done():
            pending.future.set_result(payload)


# Single process-wide instance — tools import this directly rather than
# getting it via FastAPI dependency injection, since it needs to be the
# same instance the WebSocket endpoint registers connections into.
connection_manager = DeviceConnectionManager()
