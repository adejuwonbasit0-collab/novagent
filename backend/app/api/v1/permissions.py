from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.permission import PERMISSION_RISK, PermissionScope, UserPermission
from app.models.user import User
from app.schemas.permission import PermissionOut, PermissionUpdate

router = APIRouter(prefix="/api/v1/permissions", tags=["permissions"])


@router.get("", response_model=list[PermissionOut])
async def list_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Every known PermissionScope, not just the ones the user has rows for —
    a new scope added to the enum shows up as ungranted by default rather
    than silently missing from this list until someone touches it.
    """
    result = await db.execute(select(UserPermission).where(UserPermission.user_id == current_user.id))
    existing = {p.scope: p.granted for p in result.scalars().all()}

    return [
        PermissionOut(scope=scope, granted=existing.get(scope, False), risk_level=PERMISSION_RISK[scope])
        for scope in PermissionScope
    ]


@router.put("/{scope}", response_model=PermissionOut)
async def set_permission(
    scope: PermissionScope,
    payload: PermissionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent grant/revoke — safe to call whether or not a row exists yet."""
    result = await db.execute(
        select(UserPermission).where(UserPermission.user_id == current_user.id, UserPermission.scope == scope)
    )
    perm = result.scalar_one_or_none()

    if perm is None:
        perm = UserPermission(user_id=current_user.id, scope=scope, granted=payload.granted)
        db.add(perm)
    else:
        perm.granted = payload.granted

    await db.commit()

    return PermissionOut(scope=scope, granted=perm.granted, risk_level=PERMISSION_RISK[scope])
