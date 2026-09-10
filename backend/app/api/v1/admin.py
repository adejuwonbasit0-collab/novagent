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
from app.schemas.platform_settings import (
    AssistantNameOut,
    AssistantNameUpdate,
    PlatformBrandingOut,
    PlatformBrandingUpdate,
)
from app.core.security import encrypt_provider_key
from app.services.connection_manager import connection_manager

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


def _branding_out(s: PlatformSettings) -> PlatformBrandingOut:
    return PlatformBrandingOut(
        site_name=s.site_name,
        site_description=s.site_description,
        logo_url=s.logo_url,
        favicon_url=s.favicon_url,
        primary_icon_url=s.primary_icon_url,
        desktop_icon_url=s.desktop_icon_url,
        mobile_icon_url=s.mobile_icon_url,
        footer_text=s.footer_text,
        seo_title=s.seo_title,
        seo_description=s.seo_description,
        theme=s.theme,
        accent_color=s.accent_color,
        assistant_name=s.assistant_name,
        assistant_greeting=s.assistant_greeting,
        assistant_personality=s.assistant_personality,
        default_language=s.default_language,
        default_voice=s.default_voice,
    )


@router.get("/branding", response_model=PlatformBrandingOut)
async def get_platform_branding(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    settings = await _get_platform_settings(db)
    return _branding_out(settings)


@router.put("/branding", response_model=PlatformBrandingOut)
async def update_platform_branding(
    payload: PlatformBrandingUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_platform_settings(db)
    for field, val in payload.model_dump().items():
        setattr(settings, field, val)
    await db.commit()
    await db.refresh(settings)

    # Broadcast live to connected desktop agents and mobile clients
    await connection_manager.broadcast_config_update({
        "assistant_name": settings.assistant_name,
        "assistant_greeting": settings.assistant_greeting,
        "assistant_personality": settings.assistant_personality,
        "default_language": settings.default_language,
        "default_voice": settings.default_voice,
        "desktop_icon_url": settings.desktop_icon_url,
        "theme": settings.theme,
        "accent_color": settings.accent_color,
    })

    return _branding_out(settings)


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

    await connection_manager.broadcast_config_update({"assistant_name": settings.assistant_name})

    return AssistantNameOut(assistant_name=settings.assistant_name)


def _provider_out(settings: AIProviderSettings, key_warning: str | None = None) -> AIProviderSettingsOut:
    return AIProviderSettingsOut(
        provider=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        has_api_key=bool(settings.encrypted_api_key),
        enabled=settings.enabled,
        key_warning=key_warning,
    )


# Mirrors dashboard/app/admin/ai-provider/page.tsx's KEY_PREFIX_HINTS — kept
# in sync manually since this is a small, stable list; if one changes,
# change the other. This is the backend backstop for the same root-cause
# bug (see that file's comment): a key saved while the wrong provider is
# selected gets sent, unmodified, to the wrong provider's endpoint, and
# the resulting "invalid_api_key" error gives no hint why. Any direct API
# caller (not just the dashboard UI) gets this warning too.
_KEY_PREFIX_HINTS: dict[str, tuple[str, str]] = {
    "anthropic": ("sk-ant-", "Anthropic"),
    "openai": ("sk-", "OpenAI"),
    "openrouter": ("sk-or-", "OpenRouter"),
    "groq": ("gsk_", "Groq"),
    "gemini": ("AIza", "Google Gemini"),
}


def _detect_key_mismatch(provider: str, api_key: str) -> str | None:
    key = api_key.strip()
    if not key:
        return None
    # BUG (caught by actually running this, not just reading it): an
    # Anthropic key ("sk-ant-...") also starts with the generic "sk-"
    # prefix used for OpenAI, so a naive per-provider "does it start with
    # this prefix" check matches BOTH and the mismatch never fires for
    # exactly the case this exists to catch. Rank by prefix length
    # (most specific first) and take the single best match as the key's
    # actual detected provider, then compare that to what's selected —
    # "sk-ant-" beats "sk-" for an Anthropic key even though both match.
    best_provider, best_prefix, best_label = None, "", ""
    for other_provider, (prefix, label) in _KEY_PREFIX_HINTS.items():
        if key.startswith(prefix) and len(prefix) > len(best_prefix):
            best_provider, best_prefix, best_label = other_provider, prefix, label
    if best_provider and best_provider != provider:
        provider_label = next((p_label for p, (_, p_label) in _KEY_PREFIX_HINTS.items() if p == provider), provider)
        return f"This looks like a {best_label} key, but Provider is set to {provider_label}."
    return None


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
    key_warning = None
    if payload.api_key:
        key_warning = _detect_key_mismatch(payload.provider.value, payload.api_key)
        settings.encrypted_api_key = encrypt_provider_key(payload.api_key)
    await db.commit()
    await db.refresh(settings)
    return _provider_out(settings, key_warning=key_warning)

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


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own admin account")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()
    return None


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
