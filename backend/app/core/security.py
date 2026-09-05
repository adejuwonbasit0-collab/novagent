import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    DEVICE = "device"


_BCRYPT_MAX_BYTES = 72  # bcrypt silently ignores bytes beyond this; reject instead of truncating


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must be 72 bytes or fewer")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta, extra_claims: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),  # unique id — enables future revocation/blacklisting
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, extra_claims: dict | None = None) -> str:
    return _create_token(
        subject=user_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_device_token(device_id: str, user_id: str) -> str:
    return _create_token(
        subject=device_id,
        token_type=TokenType.DEVICE,
        expires_delta=timedelta(days=settings.DEVICE_TOKEN_EXPIRE_DAYS),
        extra_claims={"user_id": user_id},
    )


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired token — caller converts to HTTP 401."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise e


def hash_token(token: str) -> str:
    """SHA-256 for storing/looking up high-entropy tokens (JWTs, API keys).
    Not bcrypt: bcrypt caps input at 72 bytes and is designed for low-entropy
    human passwords, not already-random tokens — SHA-256 is the standard
    approach for this case (same as e.g. GitHub PAT storage)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _provider_cipher() -> Fernet:
    key = hashlib.sha256(settings.JWT_SECRET_KEY.encode("utf-8")).digest()
    return Fernet(__import__("base64").urlsafe_b64encode(key))


def encrypt_provider_key(value: str) -> str:
    return _provider_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_provider_key(value: str) -> str:
    return _provider_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
