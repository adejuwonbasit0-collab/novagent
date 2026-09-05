from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.platform_settings import PlatformSettings
from app.models.user import User
from app.schemas.platform_settings import AssistantNameOut

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/assistant-name", response_model=AssistantNameOut)
async def get_public_assistant_name(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PlatformSettings).order_by(PlatformSettings.created_at).limit(1))
    settings = result.scalar_one_or_none()
    return AssistantNameOut(assistant_name=settings.assistant_name if settings else "Nova")