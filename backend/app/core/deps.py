import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenType, decode_token
from app.models.user import User, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != TokenType.ACCESS.value:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    from app.models.user import UserRole

    if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


device_token_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/devices", auto_error=False)


async def get_current_device(
    token: str | None = Depends(device_token_scheme),
    db: AsyncSession = Depends(get_db),
) -> "Device":
    """
    Authenticates a request as coming from a specific registered device
    (desktop agent / browser extension), rather than a logged-in browser
    session. Used by endpoints the local agent calls directly — e.g. tool
    execution triggered by voice/wake-word — so audit logs can record
    which device performed an action, and revoked devices are rejected
    immediately regardless of the underlying JWT's expiry.
    """
    from app.core.security import TokenType, decode_token, hash_token
    from app.models.device import Device

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing device token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != TokenType.DEVICE.value:
        raise credentials_exception

    try:
        device_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_exception

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if device is None or not device.is_active:
        raise credentials_exception
    if device.token_hash != hash_token(token):
        raise credentials_exception  # token was rotated/replaced

    from datetime import datetime, timezone

    device.last_seen_at = datetime.now(timezone.utc)
    await db.commit()

    return device


actor_token_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_actor(
    token: str | None = Depends(actor_token_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, "Device | None"]:
    """
    Resolves the (User, Device|None) pair behind a request, accepting
    EITHER a user access token (web/mobile dashboard) OR a device token
    (desktop agent / browser extension calling on the user's behalf).

    Tool execution needs this rather than get_current_user alone: a tool
    call always runs as a user, but when it originates from a registered
    device we want that device_id on the audit log (see ToolResponse
    logging in app/tools/base.py) and revoked devices must not be able to
    trigger tools even though the user's account is fine.
    """
    from app.core.security import TokenType, decode_token, hash_token
    from app.models.device import Device
    from datetime import datetime, timezone

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    token_type = payload.get("type")

    if token_type == TokenType.ACCESS.value:
        user = await get_current_user(token=token, db=db)
        return user, None

    if token_type == TokenType.DEVICE.value:
        try:
            device_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError):
            raise credentials_exception

        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if device is None or not device.is_active or device.token_hash != hash_token(token):
            raise credentials_exception

        user_result = await db.execute(select(User).where(User.id == device.user_id))
        user = user_result.scalar_one_or_none()
        if user is None or user.status != UserStatus.ACTIVE:
            raise credentials_exception

        device.last_seen_at = datetime.now(timezone.utc)
        await db.commit()

        return user, device

    raise credentials_exception
