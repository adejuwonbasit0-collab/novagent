from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from config import settings
from core.device_store import DeviceIdentity, DeviceStore, detect_platform


class APIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


@dataclass
class ToolCallResult:
    tool_name: str
    result: str
    data: dict[str, Any]
    message: str | None
    error: str | None
    pending_id: str | None = None


@dataclass
class ChatReply:
    reply: str
    tool_calls: list[ToolCallResult]


class NovaAPIClient:
    """
    Thin wrapper over the backend's REST API. Two auth modes, matching the
    backend's get_current_actor: user-token mode (right after login, before
    a device is registered) and device-token mode (normal operation once
    registered — every call after that authenticates as this device).
    """

    def __init__(self, base_url: str = settings.BACKEND_URL):
        self.base_url = base_url.rstrip("/")
        self._device_token: str | None = DeviceStore.get_token()
        self._user_token: str | None = None  # only held in memory during first-run login

    # ---- internal ----

    def _headers(self) -> dict[str, str]:
        token = self._device_token or self._user_token
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, timeout: float = 30.0, **kwargs) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        if resp.status_code == 204:
            return None
        return resp.json()

    # ---- first-run: account + device registration ----

    async def login(self, email: str, password: str) -> None:
        data = await self._request("POST", "/api/v1/auth/login", json={"email": email, "password": password})
        self._user_token = data["access_token"]

    async def register_account(self, email: str, password: str, full_name: str | None = None) -> None:
        await self._request(
            "POST", "/api/v1/auth/register", json={"email": email, "password": password, "full_name": full_name}
        )

    async def register_this_device(self, device_name: str) -> DeviceIdentity:
        """Requires self._user_token to be set (i.e. call login() first).
        On success, the device token replaces the user token for all future calls."""
        if not self._user_token:
            raise RuntimeError("Must be logged in (user token) to register a device")

        data = await self._request(
            "POST",
            "/api/v1/devices",
            json={"name": device_name, "platform": detect_platform(), "app_version": "0.1.0"},
        )
        identity = DeviceIdentity(device_id=data["device_id"], device_name=device_name, platform=detect_platform())
        DeviceStore.save(identity, data["device_token"])

        self._device_token = data["device_token"]
        self._user_token = None  # don't keep the user token around longer than needed
        return identity

    # ---- normal operation (device-token authenticated) ----

    async def chat(self, message: str) -> ChatReply:
        # BUG FIX: chat can now involve several sequential model round-trips
        # server-side (see orchestrator.py's multi-turn tool loop) plus
        # actual tool execution time -- the previous fixed 30s client
        # timeout was tuned for single-call endpoints and would cut off a
        # legitimate multi-step reply (e.g. "get the exchange rate, then
        # calculate with it") partway through. Other endpoints keep the
        # short default so a real failure there is still detected fast.
        data = await self._request(
            "POST",
            "/api/v1/assistant/chat",
            json={"message": message, "client_local_time": datetime.now().astimezone().isoformat()},
            timeout=150.0,
        )
        return ChatReply(
            reply=data["reply"],
            tool_calls=[
                ToolCallResult(
                    tool_name=tc["tool_name"],
                    result=tc["result"],
                    data=tc.get("data", {}),
                    message=tc.get("message"),
                    error=tc.get("error"),
                    pending_id=tc.get("pending_id"),
                )
                for tc in data.get("tool_calls", [])
            ],
        )

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> ToolCallResult:
        data = await self._request("POST", f"/api/v1/tools/{tool_name}/execute", json={"params": params})
        return ToolCallResult(
            tool_name=tool_name,
            result=data["result"],
            data=data.get("data", {}),
            message=data.get("message"),
            error=data.get("error"),
            pending_id=data.get("pending_id"),
        )

    async def confirm_pending(self, pending_id: str) -> ToolCallResult:
        data = await self._request("POST", f"/api/v1/assistant/confirm/{pending_id}")
        return ToolCallResult(
            tool_name=data["tool_name"],
            result=data["result"],
            data=data.get("data", {}),
            message=data.get("message"),
            error=data.get("error"),
        )

    async def get_reminders(self) -> list[dict]:
        return await self._request("GET", "/api/v1/reminders")

    # BUG FIX: ui/reminder_alert.py's Snooze/Dismiss buttons on the alarm
    # dialog (spec section 35) have been calling client.snooze_reminder()
    # and client.dismiss_reminder() since they were written -- neither
    # method existed on this class. Every click raised AttributeError
    # inside the fire-and-forget worker thread, silently swallowed by its
    # generic except-and-emit-failed handler: the dialog closed like the
    # click worked, but the backend reminder row was never actually
    # snoozed or deleted. Net effect: the SAME reminder fires again next
    # poll cycle (or on next agent restart / another device), because as
    # far as the backend is concerned nothing happened. Both endpoints
    # already existed and worked correctly on the backend
    # (POST .../snooze, DELETE ...) -- only the client-side methods to
    # call them were missing.
    async def snooze_reminder(self, reminder_id: str, minutes: int = 10) -> dict:
        return await self._request("POST", f"/api/v1/reminders/{reminder_id}/snooze", params={"minutes": minutes})

    async def dismiss_reminder(self, reminder_id: str) -> None:
        await self._request("DELETE", f"/api/v1/reminders/{reminder_id}")

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/health")
            return True
        except Exception:
            return False

    async def get_assistant_name(self) -> str:
        data = await self._request("GET", "/api/v1/settings/assistant-name")
        return data["assistant_name"]

    # ---- speaker verification (spec section 8/9) ----

    async def get_speaker_template(self) -> dict:
        return await self._request("GET", "/api/v1/speaker/template")

    async def enroll_speaker(self, embeddings: list[list[float]]) -> dict:
        return await self._request("POST", "/api/v1/speaker/enroll", json={"embeddings": embeddings})

    async def reset_speaker_profile(self) -> dict:
        return await self._request("DELETE", "/api/v1/speaker/profile")
