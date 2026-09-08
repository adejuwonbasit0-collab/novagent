from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.platform_settings import PlatformSettings
from app.models.user import User
from app.schemas.platform_settings import AssistantNameOut, PlatformBrandingOut

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/assistant-name", response_model=AssistantNameOut)
async def get_public_assistant_name(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PlatformSettings).order_by(PlatformSettings.created_at).limit(1))
    settings = result.scalar_one_or_none()
    return AssistantNameOut(assistant_name=settings.assistant_name if settings else "Nova")


@router.get("/branding", response_model=PlatformBrandingOut)
async def get_public_platform_branding(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PlatformSettings).order_by(PlatformSettings.created_at).limit(1))
    s = result.scalar_one_or_none()
    if s is None:
        s = PlatformSettings()
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