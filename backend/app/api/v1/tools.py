from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_actor
from app.models.device import Device
from app.models.user import User
from app.schemas.tool import ToolExecuteRequest, ToolExecuteResponse
from app.tools.base import ToolExecutionContext, ToolRegistry

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("")
async def list_tools(actor: tuple[User, Device | None] = Depends(get_current_actor)):
    """Lets a client (desktop agent, browser extension) discover available
    tools and their permission requirements before attempting to call them."""
    return ToolRegistry.list_tools()


@router.post("/{tool_name}/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    tool_name: str,
    payload: ToolExecuteRequest,
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Single entry point for running any registered tool, called by:
    - the web/mobile dashboard on behalf of the logged-in user, or
    - the desktop agent / browser extension on behalf of the user it's
      registered to (device_id then flows into the audit log).

    High-risk tools return REQUIRES_CONFIRMATION on the first call; the
    client re-calls with confirmed=true after the user approves — this
    mirrors the shutdown-computer confirmation flow in the spec (section 5)
    without hard-coding it into any single tool.
    """
    tool = ToolRegistry.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool: {tool_name}")

    user, device = actor
    ctx = ToolExecutionContext(
        user=user,
        db=db,
        device_id=device.id if device else None,
        confirmed=payload.confirmed,
    )

    response = await tool.execute(payload.params, ctx)

    return ToolExecuteResponse(
        result=response.result.value,
        data=response.data,
        message=response.message,
        error=response.error,
        duration_ms=response.duration_ms,
    )
