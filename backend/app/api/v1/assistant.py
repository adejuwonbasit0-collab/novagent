import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_actor
from app.models.device import Device
from app.models.pending_tool_call import PendingToolCall
from app.models.user import User
from app.schemas.assistant import ChatRequest, ChatResponse, ConfirmResponse, ToolCallOut
from app.services.orchestrator import OrchestrationError, confirm_pending_tool_call, run_orchestration
from app.tools.base import ToolExecutionContext

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Natural-language entry point: the model plans and may propose tool
    calls, which run through the exact same permission/risk/confirmation
    gate as a direct /api/v1/tools/{name}/execute call. High-risk proposals
    come back as REQUIRES_CONFIRMATION with a pending_id — the client must
    call /confirm/{pending_id} to actually run them.
    """
    user, device = actor
    ctx = ToolExecutionContext(user=user, db=db, device_id=device.id if device else None, confirmed=False)

    try:
        result = await run_orchestration(payload.message, ctx, client_local_time=payload.client_local_time)
    except OrchestrationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    return ChatResponse(
        reply=result.reply,
        tool_calls=[
            ToolCallOut(
                tool_name=o.tool_name,
                result=o.result,
                data=o.data,
                message=o.message,
                error=o.error,
                pending_id=o.pending_id,
            )
            for o in result.tool_calls
        ],
    )


@router.post("/confirm/{pending_id}", response_model=ConfirmResponse)
async def confirm(
    pending_id: uuid.UUID,
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """The only path by which a REQUIRES_CONFIRMATION tool call actually
    executes — requires the same authenticated actor that owns the pending
    row, and refuses anything already resolved or past its TTL."""
    user, device = actor

    result = await db.execute(
        select(PendingToolCall).where(PendingToolCall.id == pending_id, PendingToolCall.user_id == user.id)
    )
    pending = result.scalar_one_or_none()

    if pending is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such pending action")
    if pending.resolved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This action was already resolved")
    if pending.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This confirmation has expired — ask again")

    ctx = ToolExecutionContext(user=user, db=db, device_id=device.id if device else pending.device_id)
    outcome = await confirm_pending_tool_call(pending, ctx)

    pending.resolved = True
    await db.commit()

    return ConfirmResponse(
        tool_name=outcome.tool_name,
        result=outcome.result,
        data=outcome.data,
        message=outcome.message,
        error=outcome.error,
    )
