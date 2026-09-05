import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_actor
from app.models.device import Device
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.schemas.reminder import ReminderCreate, ReminderOut, ReminderUpdate

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])

# Reminders are read/managed by both the web dashboard (user token) and the
# desktop agent (device token) — e.g. "what's on my schedule" via voice —
# so every route here uses get_current_actor rather than get_current_user.
Actor = tuple[User, Device | None]


async def _get_owned_reminder(reminder_id: uuid.UUID, user: User, db: AsyncSession) -> Reminder:
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    return reminder


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: ReminderCreate,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    reminder = Reminder(user_id=user.id, **payload.model_dump())
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    status_filter: ReminderStatus | None = None,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    query = select(Reminder).where(Reminder.user_id == user.id)
    if status_filter:
        query = query.where(Reminder.status == status_filter)
    query = query.order_by(Reminder.due_at.asc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{reminder_id}", response_model=ReminderOut)
async def get_reminder(
    reminder_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    return await _get_owned_reminder(reminder_id, user, db)


@router.patch("/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderUpdate,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    reminder = await _get_owned_reminder(reminder_id, user, db)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == ReminderStatus.COMPLETED:
        updates["completed_at"] = datetime.now(timezone.utc)

    for field, value in updates.items():
        setattr(reminder, field, value)

    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.post("/{reminder_id}/snooze", response_model=ReminderOut)
async def snooze_reminder(
    reminder_id: uuid.UUID,
    minutes: int = 10,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta

    user, _device = actor
    reminder = await _get_owned_reminder(reminder_id, user, db)
    reminder.status = ReminderStatus.SNOOZED
    reminder.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    reminder = await _get_owned_reminder(reminder_id, user, db)
    await db.delete(reminder)
    await db.commit()
