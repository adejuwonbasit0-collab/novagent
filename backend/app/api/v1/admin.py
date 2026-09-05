import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.audit_log import AuditLog
from app.models.ai_provider import AIProviderSettings
from app.models.device import Device
from app.models.platform_settings import PlatformSettings
from app.models.reminder import Reminder
from app.models.user import User, UserRole, UserStatus
from app.schemas.admin import AdminAuditLogOut, AdminDeviceOut, AdminStatsOut, AdminUserOut, AdminUserUpdate
from app.schemas.ai_provider import AIProviderSettingsOut, AIProviderSettingsUpdate
from app.schemas.platform_settings import AssistantNameOut, AssistantNameUpdate
from app.core.security import encrypt_provider_key

def _user_to_admin_out(user: User, device_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=user.status,
        role=user.role,
        is_email_verified=user.is_email_verified,
        created_at=user.created_at,
        device_count=device_count,
    )


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _get_platform_settings(db: AsyncSession) -> PlatformSettings:
    result = await db.execute(select(PlatformSettings).order_by(PlatformSettings.created_at).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = PlatformSettings(assistant_name="Nova")
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("/assistant-name", response_model=AssistantNameOut)
async def get_assistant_name(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    settings = await _get_platform_settings(db)
    return AssistantNameOut(assistant_name=settings.assistant_name)


@router.put("/assistant-name", response_model=AssistantNameOut)
async def update_assistant_name(
    payload: AssistantNameUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_platform_settings(db)
    settings.assistant_name = payload.assistant_name.strip()
    await db.commit()
    return AssistantNameOut(assistant_name=settings.assistant_name)


def _provider_out(settings: AIProviderSettings) -> AIProviderSettingsOut:
    return AIProviderSettingsOut(
        provider=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        has_api_key=bool(settings.encrypted_api_key),
        enabled=settings.enabled,
    )


@router.get("/ai-provider", response_model=AIProviderSettingsOut)
async def get_ai_provider(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIProviderSettings).order_by(AIProviderSettings.created_at).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AIProviderSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return _provider_out(settings)


@router.put("/ai-provider", response_model=AIProviderSettingsOut)
async def update_ai_provider(
    payload: AIProviderSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AIProviderSettings).order_by(AIProviderSettings.created_at).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AIProviderSettings()
        db.add(settings)
    settings.provider = payload.provider
    settings.model = payload.model
    settings.base_url = payload.base_url
    settings.enabled = payload.enabled
    if payload.api_key:
        settings.encrypted_api_key = encrypt_provider_key(payload.api_key)
    await db.commit()
    await db.refresh(settings)
    return _provider_out(settings)

# Every route here requires get_current_admin — a 403 for anyone whose role
# isn't ADMIN or SUPER_ADMIN, checked before any query runs.


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    active_users = (
        await db.execute(select(func.count()).select_from(User).where(User.status == UserStatus.ACTIVE))
    ).scalar_one()
    suspended_users = (
        await db.execute(select(func.count()).select_from(User).where(User.status == UserStatus.SUSPENDED))
    ).scalar_one()
    total_devices = (await db.execute(select(func.count()).select_from(Device))).scalar_one()
    active_devices = (
        await db.execute(select(func.count()).select_from(Device).where(Device.is_active == True))  # noqa: E712
    ).scalar_one()
    total_reminders = (await db.execute(select(func.count()).select_from(Reminder))).scalar_one()

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    audit_count = (
        await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= since))
    ).scalar_one()

    return AdminStatsOut(
        total_users=total_users,
        active_users=active_users,
        suspended_users=suspended_users,
        total_devices=total_devices,
        active_devices=active_devices,
        total_reminders=total_reminders,
        audit_log_count_last_24h=audit_count,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    status_filter: UserStatus | None = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if status_filter:
        query = query.where(User.status == status_filter)
    query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    users = result.scalars().all()

    # N+1 device-count query per user is fine at admin-dashboard scale
    # (tens to low hundreds of rows); revisit with a join/subquery if this
    # page is ever paginating through thousands of users.
    out = []
    for user in users:
        count_result = await db.execute(select(func.count()).select_from(Device).where(Device.user_id == user.id))
        out.append(_user_to_admin_out(user, count_result.scalar_one()))
    return out


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == admin.id and payload.status is not None and payload.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend or deactivate your own account")

    if payload.role is not None and user.id == admin.id and payload.role != admin.role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role")

    if payload.status is not None:
        user.status = payload.status
    if payload.role is not None:
        user.role = payload.role

    await db.commit()

    count_result = await db.execute(select(func.count()).select_from(Device).where(Device.user_id == user.id))
    return _user_to_admin_out(user, count_result.scalar_one())


@router.get("/devices", response_model=list[AdminDeviceOut])
async def list_devices(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)

    return [
        AdminDeviceOut(
            id=device.id,
            user_id=device.user_id,
            user_email=email,
            name=device.name,
            platform=device.platform,
            is_active=device.is_active,
            last_seen_at=device.last_seen_at,
            created_at=device.created_at,
        )
        for device, email in result.all()
    ]


@router.post("/devices/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def admin_revoke_device(
    device_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lets an admin revoke any user's device — e.g. responding to a
    security report — without needing that user's own session."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    device.is_active = False
    await db.commit()


@router.get("/audit-logs", response_model=list[AdminAuditLogOut])
async def list_audit_logs(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    user_id: uuid.UUID | None = None,
    result_filter: str | None = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog, User.email).outerjoin(User, AuditLog.user_id == User.id)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if result_filter:
        query = query.where(AuditLog.result == result_filter)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)

    return [
        AdminAuditLogOut(
            id=log.id,
            user_id=log.user_id,
            user_email=email,
            device_id=log.device_id,
            action=log.action,
            resource=log.resource,
            result=log.result,
            metadata_json=log.metadata_json,
            created_at=log.created_at,
        )
        for log, email in result.all()
    ]
