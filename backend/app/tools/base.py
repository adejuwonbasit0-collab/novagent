from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import PermissionScope, RiskLevel
from app.models.user import User


class ToolResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


@dataclass
class ToolExecutionContext:
    """Everything a tool needs to execute safely and be audited."""

    user: User
    db: AsyncSession
    device_id: uuid.UUID | None = None
    confirmed: bool = False  # true if the user already confirmed a high-risk action


@dataclass
class ToolResponse:
    result: ToolResult
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    error: str | None = None
    duration_ms: float | None = None


class BaseTool(ABC):
    """
    Every tool in the registry (spec section 6) must declare:
    name, description, input schema, permission level, risk level,
    confirmation requirement, and platform compatibility.

    Subclasses implement `_run`; `execute` wraps it with permission
    checks, confirmation gating, timing, and error handling so no
    individual tool has to reimplement that plumbing.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    required_permission: ClassVar[PermissionScope | None] = None
    risk_level: ClassVar[RiskLevel] = RiskLevel.LOW
    requires_confirmation: ClassVar[bool] = False
    supported_platforms: ClassVar[tuple[str, ...]] = ("cloud", "windows", "macos", "linux")
    timeout_seconds: ClassVar[float] = 15.0

    @abstractmethod
    async def _run(self, params: BaseModel, ctx: ToolExecutionContext) -> ToolResponse:
        """Tool-specific logic. Raise exceptions freely — `execute` catches them."""
        raise NotImplementedError

    async def execute(self, raw_params: dict[str, Any], ctx: ToolExecutionContext) -> ToolResponse:
        start = time.perf_counter()

        # 1. Permission check
        if self.required_permission is not None:
            if not await self._has_permission(ctx):
                return ToolResponse(
                    result=ToolResult.DENIED,
                    error=f"Missing permission: {self.required_permission.value}",
                )

        # 2. Confirmation gate for high-risk tools
        if self.requires_confirmation and not ctx.confirmed:
            return ToolResponse(
                result=ToolResult.REQUIRES_CONFIRMATION,
                message=f"'{self.name}' is a {self.risk_level.value}-risk action and requires confirmation.",
            )

        # 3. Validate input against schema
        try:
            params = self.input_schema(**raw_params)
        except Exception as e:
            return ToolResponse(result=ToolResult.FAILURE, error=f"Invalid input: {e}")

        # 4. Execute with timeout + error handling
        try:
            import asyncio

            response = await asyncio.wait_for(self._run(params, ctx), timeout=self.timeout_seconds)
        except TimeoutError:
            response = ToolResponse(result=ToolResult.FAILURE, error="Tool execution timed out")
        except Exception as e:
            response = ToolResponse(result=ToolResult.FAILURE, error=str(e))

        response.duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # 5. Audit log (best-effort — never let logging failure break the response)
        try:
            await self._audit(ctx, response)
        except Exception:
            pass

        return response

    async def _has_permission(self, ctx: ToolExecutionContext) -> bool:
        from sqlalchemy import select

        from app.models.permission import UserPermission

        result = await ctx.db.execute(
            select(UserPermission).where(
                UserPermission.user_id == ctx.user.id,
                UserPermission.scope == self.required_permission,
            )
        )
        perm = result.scalar_one_or_none()
        return bool(perm and perm.granted)

    async def _audit(self, ctx: ToolExecutionContext, response: ToolResponse) -> None:
        from app.models.audit_log import AuditLog

        log = AuditLog(
            user_id=ctx.user.id,
            device_id=ctx.device_id,
            action=self.name,
            resource=response.data.get("resource"),
            result=response.result.value,
            metadata_json={"message": response.message, "error": response.error, "duration_ms": response.duration_ms},
        )
        ctx.db.add(log)
        await ctx.db.commit()


class ToolRegistry:
    """Central registry the orchestration engine queries for tool selection."""

    _tools: ClassVar[dict[str, BaseTool]] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool | None:
        return cls._tools.get(name)

    @classmethod
    def all(cls) -> list[BaseTool]:
        return list(cls._tools.values())

    @classmethod
    def list_tools(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "risk_level": t.risk_level.value,
                "required_permission": t.required_permission.value if t.required_permission else None,
                "requires_confirmation": t.requires_confirmation,
                "platforms": t.supported_platforms,
            }
            for t in cls._tools.values()
        ]
