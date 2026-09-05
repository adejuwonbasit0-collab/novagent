from pydantic import BaseModel

from app.models.permission import PermissionScope, RiskLevel
from app.services.connection_manager import CommandTimeout, DeviceNotConnected, connection_manager
from app.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResponse, ToolResult


async def _dispatch_to_device(tool_name: str, params: dict, ctx: ToolExecutionContext, timeout: float = 15.0) -> ToolResponse:
    """
    Shared dispatch path for every OS-control tool: routes the call over
    the caller's WebSocket connection (app/services/connection_manager.py)
    to the exact device that's supposed to run it, and turns the device's
    reply into a ToolResponse. A tool call with no device context (e.g.
    made from the web dashboard, which has no OS to control) fails
    immediately rather than silently no-op'ing.
    """
    if ctx.device_id is None:
        return ToolResponse(
            result=ToolResult.FAILURE,
            error="This action must be run from a connected device, not the web dashboard.",
        )

    try:
        result = await connection_manager.send_command(ctx.device_id, tool_name, params, timeout=timeout)
    except DeviceNotConnected:
        return ToolResponse(
            result=ToolResult.FAILURE,
            error="The device isn't currently connected. Open the desktop agent and try again.",
        )
    except CommandTimeout:
        return ToolResponse(result=ToolResult.FAILURE, error="The device didn't respond in time.")

    if result.get("success"):
        return ToolResponse(
            result=ToolResult.SUCCESS,
            data={"resource": tool_name},
            message=result.get("message"),
        )
    return ToolResponse(result=ToolResult.FAILURE, error=result.get("error") or "Device reported failure")


class ShutdownComputerInput(BaseModel):
    pass


class ShutdownComputerTool(BaseTool):
    """Matches the exact example in spec section 5: high-risk, always
    requires confirmation regardless of what the LLM decided. Now
    dispatches for real over the device WebSocket connection rather than
    being a stub — see _dispatch_to_device above."""

    name = "shutdown_computer"
    description = "Shut down the user's computer. Always requires explicit confirmation."
    input_schema = ShutdownComputerInput
    required_permission = PermissionScope.SYSTEM_SHUTDOWN
    risk_level = RiskLevel.HIGH
    requires_confirmation = True
    supported_platforms = ("windows", "macos", "linux")
    timeout_seconds = 20.0  # dispatch adds network round-trip on top of BaseTool's own timeout

    async def _run(self, params: ShutdownComputerInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await _dispatch_to_device("shutdown_computer", {}, ctx)


class LockComputerInput(BaseModel):
    pass


class LockComputerTool(BaseTool):
    name = "lock_computer"
    description = "Lock the user's computer screen."
    input_schema = LockComputerInput
    required_permission = PermissionScope.SYSTEM_LOCK
    risk_level = RiskLevel.MEDIUM
    requires_confirmation = False
    supported_platforms = ("windows", "macos", "linux")
    timeout_seconds = 20.0

    async def _run(self, params: LockComputerInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await _dispatch_to_device("lock_computer", {}, ctx)


class OpenApplicationInput(BaseModel):
    app_name: str


class OpenApplicationTool(BaseTool):
    name = "open_application"
    description = "Open an application on the user's computer by name."
    input_schema = OpenApplicationInput
    required_permission = PermissionScope.APP_OPEN
    risk_level = RiskLevel.LOW
    requires_confirmation = False
    supported_platforms = ("windows", "macos", "linux")
    timeout_seconds = 20.0

    async def _run(self, params: OpenApplicationInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await _dispatch_to_device("open_application", {"app_name": params.app_name}, ctx)


ToolRegistry.register(ShutdownComputerTool())
ToolRegistry.register(LockComputerTool())
ToolRegistry.register(OpenApplicationTool())
