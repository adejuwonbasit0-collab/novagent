from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_provider_key
from app.models.ai_provider import AIProvider, AIProviderSettings
from app.models.pending_tool_call import PendingToolCall
from app.tools.base import ToolExecutionContext, ToolRegistry, ToolResult

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class OrchestrationError(Exception):
    """Raised for upstream (Anthropic API) failures — callers turn this into an HTTP 502."""


@dataclass
class ToolCallOutcome:
    tool_name: str
    result: str  # ToolResult value, as a string
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    error: str | None = None
    pending_id: uuid.UUID | None = None  # set when result == REQUIRES_CONFIRMATION


@dataclass
class OrchestrationResult:
    reply: str
    tool_calls: list[ToolCallOutcome] = field(default_factory=list)


def _pydantic_to_anthropic_input_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


def build_tool_schemas() -> list[dict]:
    """Converts every registered tool's Pydantic input schema into the
    Anthropic tool-use format, so the model can only ever propose calls
    shaped the way BaseTool.execute() already validates against."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": _pydantic_to_anthropic_input_schema(tool.input_schema),
        }
        for tool in ToolRegistry.all()
    ]


async def _call_anthropic(messages: list[dict], tools: list[dict]) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        raise OrchestrationError("ANTHROPIC_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "messages": messages,
                "tools": tools,
            },
        )

    if resp.status_code >= 400:
        raise OrchestrationError(f"Anthropic API error {resp.status_code}: {resp.text}")

    return resp.json()


async def _call_openai_compatible(api_key: str, base_url: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 1024, "messages": messages, "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]},
        )
    if resp.status_code >= 400:
        raise OrchestrationError(f"AI provider error {resp.status_code}: {resp.text}")
    data = resp.json()
    message = data.get("choices", [{}])[0].get("message", {})
    content = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls", []):
        function = call.get("function", {})
        try:
            import json
            tool_input = json.loads(function.get("arguments", "{}"))
        except ValueError:
            tool_input = {}
        content.append({"type": "tool_use", "name": function.get("name", ""), "input": tool_input})
    return {"content": content}


async def _call_gemini(api_key: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    contents = [{"role": "user", "parts": [{"text": messages[-1]["content"]}]}]
    declarations = [{"name": t["name"], "description": t["description"], "parameters": t["input_schema"]} for t in tools]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={"contents": contents, "tools": [{"function_declarations": declarations}]},
        )
    if resp.status_code >= 400:
        raise OrchestrationError(f"Gemini API error {resp.status_code}: {resp.text}")
    parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return {"content": [{"type": "text", "text": p["text"]} if "text" in p else {"type": "tool_use", "name": p["functionCall"]["name"], "input": p["functionCall"].get("args", {})} for p in parts]}


async def _call_configured_provider(messages: list[dict], tools: list[dict], db) -> dict:
    result = await db.execute(select(AIProviderSettings).order_by(AIProviderSettings.created_at).limit(1))
    configured = result.scalar_one_or_none()
    if configured and configured.enabled and configured.encrypted_api_key:
        api_key = decrypt_provider_key(configured.encrypted_api_key)
        if configured.provider == AIProvider.GEMINI:
            return await _call_gemini(api_key, configured.model, messages, tools)
        if configured.provider == AIProvider.ANTHROPIC:
            return await _call_anthropic_with_credentials(api_key, configured.model, messages, tools)
        base_url = configured.base_url or "https://api.openai.com/v1"
        return await _call_openai_compatible(api_key, base_url, configured.model, messages, tools)
    return await _call_anthropic(messages, tools)


async def _call_anthropic_with_credentials(api_key: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    original_key, original_model = settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL
    try:
        settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL = api_key, model
        return await _call_anthropic(messages, tools)
    finally:
        settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL = original_key, original_model


async def _persist_pending_confirmation(
    tool_name: str, params: dict, message: str | None, ctx: ToolExecutionContext
) -> PendingToolCall:
    pending = PendingToolCall(
        user_id=ctx.user.id,
        device_id=ctx.device_id,
        tool_name=tool_name,
        params=params,
        reason=message,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PENDING_CONFIRMATION_TTL_MINUTES),
    )
    ctx.db.add(pending)
    await ctx.db.commit()
    await ctx.db.refresh(pending)
    return pending


async def run_orchestration(user_message: str, ctx: ToolExecutionContext) -> OrchestrationResult:
    """
    Pipeline (spec section 7), STT/TTS and speaker verification excluded —
    those sit in front of this at the voice-interface layer, which isn't
    built yet:

        user text -> intent + planning (LLM w/ tool-use) -> tool selection
        -> tool execution (via BaseTool.execute, unchanged) -> result
        -> response generation

    The model NEVER executes anything directly. It proposes tool_use
    blocks; every single one still passes through the same permission
    check, risk classification, and confirmation gate as a manually-typed
    API call to /api/v1/tools/{name}/execute — this function is a caller
    of that logic, not a bypass of it.
    """
    tools_schema = build_tool_schemas()
    messages = [{"role": "user", "content": user_message}]

    ai_response = await _call_configured_provider(messages, tools_schema, ctx.db)

    text_parts: list[str] = []
    tool_use_blocks: list[dict] = []

    for block in ai_response.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block["text"])
        elif block.get("type") == "tool_use":
            tool_use_blocks.append(block)

    outcomes: list[ToolCallOutcome] = []

    for block in tool_use_blocks:
        tool_name = block["name"]
        tool_input = block.get("input", {})

        tool = ToolRegistry.get(tool_name)
        if tool is None:
            outcomes.append(
                ToolCallOutcome(tool_name=tool_name, result=ToolResult.FAILURE.value, error="Unknown tool")
            )
            continue

        # confirmed is always False here — the LLM's plan cannot self-approve
        # a high-risk action; only a real confirm-endpoint call (driven by
        # the user, against a PendingToolCall row) can set confirmed=True.
        response = await tool.execute(tool_input, ctx)

        if response.result == ToolResult.REQUIRES_CONFIRMATION:
            pending = await _persist_pending_confirmation(tool_name, tool_input, response.message, ctx)
            outcomes.append(
                ToolCallOutcome(
                    tool_name=tool_name,
                    result=response.result.value,
                    message=response.message,
                    pending_id=pending.id,
                )
            )
        else:
            outcomes.append(
                ToolCallOutcome(
                    tool_name=tool_name,
                    result=response.result.value,
                    data=response.data,
                    message=response.message,
                    error=response.error,
                )
            )

    reply = " ".join(text_parts).strip()
    if not reply and outcomes:
        # Model went straight to a tool call with no accompanying text —
        # synthesize something so the user isn't shown an empty response.
        reply = outcomes[0].message or "Done."

    return OrchestrationResult(reply=reply or "I'm not sure how to help with that.", tool_calls=outcomes)


async def confirm_pending_tool_call(pending: PendingToolCall, ctx: ToolExecutionContext) -> ToolCallOutcome:
    """Executes a previously-proposed tool call for real, now that the user
    has explicitly approved it. Always sets confirmed=True — this is the
    ONLY code path allowed to do so on the caller's behalf."""
    tool = ToolRegistry.get(pending.tool_name)
    if tool is None:
        return ToolCallOutcome(tool_name=pending.tool_name, result=ToolResult.FAILURE.value, error="Unknown tool")

    ctx.confirmed = True
    response = await tool.execute(pending.params, ctx)

    return ToolCallOutcome(
        tool_name=pending.tool_name,
        result=response.result.value,
        data=response.data,
        message=response.message,
        error=response.error,
    )
