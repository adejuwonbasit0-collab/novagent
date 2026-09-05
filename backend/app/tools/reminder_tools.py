from datetime import datetime

from pydantic import BaseModel

from app.models.permission import PermissionScope, RiskLevel
from app.models.reminder import Reminder
from app.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResponse, ToolResult


class CreateReminderInput(BaseModel):
    title: str
    due_at: datetime
    notes: str | None = None
    timezone: str = "UTC"


class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = "Create a reminder for the user at a specific date/time."
    input_schema = CreateReminderInput
    required_permission = PermissionScope.REMINDERS_MANAGE
    risk_level = RiskLevel.LOW
    requires_confirmation = False
    supported_platforms = ("cloud", "windows", "macos", "linux", "mobile")

    async def _run(self, params: CreateReminderInput, ctx: ToolExecutionContext) -> ToolResponse:
        reminder = Reminder(
            user_id=ctx.user.id,
            title=params.title,
            notes=params.notes,
            due_at=params.due_at,
            timezone=params.timezone,
        )
        ctx.db.add(reminder)
        await ctx.db.commit()
        await ctx.db.refresh(reminder)

        return ToolResponse(
            result=ToolResult.SUCCESS,
            data={"resource": params.title, "reminder_id": str(reminder.id)},
            message=f"Reminder '{params.title}' set for {params.due_at.isoformat()}.",
        )


class GetScheduleInput(BaseModel):
    limit: int = 10


class GetScheduleTool(BaseTool):
    name = "get_schedule"
    description = "Retrieve the user's upcoming pending reminders."
    input_schema = GetScheduleInput
    required_permission = PermissionScope.REMINDERS_MANAGE
    risk_level = RiskLevel.LOW

    async def _run(self, params: GetScheduleInput, ctx: ToolExecutionContext) -> ToolResponse:
        from sqlalchemy import select

        from app.models.reminder import ReminderStatus

        result = await ctx.db.execute(
            select(Reminder)
            .where(Reminder.user_id == ctx.user.id, Reminder.status == ReminderStatus.PENDING)
            .order_by(Reminder.due_at.asc())
            .limit(params.limit)
        )
        reminders = result.scalars().all()

        return ToolResponse(
            result=ToolResult.SUCCESS,
            data={
                "reminders": [
                    {"id": str(r.id), "title": r.title, "due_at": r.due_at.isoformat()} for r in reminders
                ]
            },
        )


# Register on import — app startup imports this module to populate the registry.
ToolRegistry.register(CreateReminderTool())
ToolRegistry.register(GetScheduleTool())
