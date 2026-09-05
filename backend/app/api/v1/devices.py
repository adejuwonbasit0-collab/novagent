import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_device_token, hash_token
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceOut, DeviceRegister, DeviceRegisterResponse, DeviceRename

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


async def _get_owned_device(device_id: uuid.UUID, user: User, db: AsyncSession) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id, Device.user_id == user.id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.post("", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called once when the desktop agent / browser extension installer
    finishes authenticating (spec section 32, step 3). The returned
    device_token is shown ONCE — only its hash is persisted, so it
    cannot be recovered later; a lost token means re-registering the device.
    """
    device = Device(
        user_id=current_user.id,
        name=payload.name,
        platform=payload.platform,
        app_version=payload.app_version,
        token_hash="",  # set below once we know the device id
    )
    db.add(device)
    await db.flush()  # assigns device.id without committing yet

    device_token = create_device_token(device_id=str(device.id), user_id=str(current_user.id))
    device.token_hash = hash_token(device_token)

    await db.commit()
    await db.refresh(device)

    return DeviceRegisterResponse(device_id=device.id, device_token=device_token)


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.user_id == current_user.id).order_by(Device.created_at.desc()))
    return result.scalars().all()


@router.patch("/{device_id}", response_model=DeviceOut)
async def rename_device(
    device_id: uuid.UUID,
    payload: DeviceRename,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_owned_device(device_id, current_user, db)
    device.name = payload.name
    await db.commit()
    await db.refresh(device)
    return device


@router.post("/{device_id}/revoke", response_model=DeviceOut)
async def revoke_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Immediately invalidates the device — get_current_device (used by
    desktop-agent-facing endpoints) checks is_active on every request,
    so this takes effect on the device's very next call, no token
    expiry wait required."""
    device = await _get_owned_device(device_id, current_user, db)
    device.is_active = False
    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_owned_device(device_id, current_user, db)
    await db.delete(device)
    await db.commit()
