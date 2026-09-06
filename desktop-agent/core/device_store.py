from __future__ import annotations

import json
import platform
import stat
from dataclasses import dataclass

import keyring
import keyring.errors

from config import CONFIG_DIR, DEVICE_STATE_FILE

KEYRING_SERVICE = "nova-assistant"
KEYRING_USERNAME = "device_token"

_FALLBACK_KEY_FILE = CONFIG_DIR / ".local_key"
_FALLBACK_TOKEN_FILE = CONFIG_DIR / ".local_token"

# Cached speaker-verification template (embedding vector + threshold/enabled
# flag), synced from GET /api/v1/speaker/template. Not a secret on the level
# of a device token, but it's biometric-derived data, so it gets the same
# owner-only file permissions as the encrypted-token fallback rather than
# being written world-readable.
_SPEAKER_TEMPLATE_FILE = CONFIG_DIR / "speaker_template.json"


def detect_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    return "linux"  # sane default rather than raising on an unexpected value


@dataclass
class DeviceIdentity:
    device_id: str
    device_name: str
    platform: str


def _fallback_fernet():
    """
    Used only when the OS has no keyring backend at all (some headless
    Linux setups, minimal distros, CI). Encrypts the token at rest with a
    locally-generated key stored with owner-only permissions — weaker than
    a real OS keyring (an attacker with local file access to both files
    can decrypt it), but strictly better than the raw-plaintext token this
    would otherwise fall back to. Prefer the real keyring whenever one is
    available; this path exists so the agent doesn't simply crash without it.
    """
    from cryptography.fernet import Fernet

    if not _FALLBACK_KEY_FILE.exists():
        key = Fernet.generate_key()
        _FALLBACK_KEY_FILE.write_bytes(key)
        _FALLBACK_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — owner read/write only
    else:
        key = _FALLBACK_KEY_FILE.read_bytes()

    return Fernet(key)


class DeviceStore:
    """
    Splits device identity into two places on purpose:
    - device.json: id/name/platform — not sensitive, fine to read for debugging
    - OS keyring (or the local-encrypted-file fallback below): the actual
      device token — never touches disk in plaintext, matching the
      backend's own rule that raw tokens are shown once and never
      persisted server-side either.
    """

    @staticmethod
    def is_registered() -> bool:
        return DEVICE_STATE_FILE.exists() and DeviceStore.get_token() is not None

    @staticmethod
    def save(identity: DeviceIdentity, token: str) -> None:
        DEVICE_STATE_FILE.write_text(
            json.dumps({"device_id": identity.device_id, "device_name": identity.device_name, "platform": identity.platform})
        )
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        except keyring.errors.KeyringError:
            fernet = _fallback_fernet()
            _FALLBACK_TOKEN_FILE.write_bytes(fernet.encrypt(token.encode("utf-8")))
            _FALLBACK_TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)

    @staticmethod
    def get_identity() -> DeviceIdentity | None:
        if not DEVICE_STATE_FILE.exists():
            return None
        data = json.loads(DEVICE_STATE_FILE.read_text())
        return DeviceIdentity(device_id=data["device_id"], device_name=data["device_name"], platform=data["platform"])

    @staticmethod
    def get_token() -> str | None:
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if token is not None:
                return token
        except keyring.errors.KeyringError:
            pass

        if _FALLBACK_TOKEN_FILE.exists() and _FALLBACK_KEY_FILE.exists():
            fernet = _fallback_fernet()
            try:
                return fernet.decrypt(_FALLBACK_TOKEN_FILE.read_bytes()).decode("utf-8")
            except Exception:
                return None
        return None

    @staticmethod
    def clear() -> None:
        if DEVICE_STATE_FILE.exists():
            DEVICE_STATE_FILE.unlink()
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.KeyringError:
            pass
        for f in (_FALLBACK_TOKEN_FILE, _FALLBACK_KEY_FILE, _SPEAKER_TEMPLATE_FILE):
            if f.exists():
                f.unlink()

    # ---- speaker verification template cache ----
    # Kept separate from the token methods above: this is device-local
    # storage of an *account-level* template (synced from the backend so
    # verification keeps working with no network — spec section 38), not
    # device identity.

    @staticmethod
    def save_speaker_template(embedding: list[float] | None, threshold: float, enabled: bool) -> None:
        _SPEAKER_TEMPLATE_FILE.write_text(
            json.dumps({"embedding": embedding, "threshold": threshold, "enabled": enabled})
        )
        try:
            _SPEAKER_TEMPLATE_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # best-effort on platforms where chmod semantics differ (e.g. some Windows setups)

    @staticmethod
    def get_speaker_template() -> dict | None:
        if not _SPEAKER_TEMPLATE_FILE.exists():
            return None
        try:
            return json.loads(_SPEAKER_TEMPLATE_FILE.read_text())
        except Exception:
            return None

    @staticmethod
    def clear_speaker_template() -> None:
        if _SPEAKER_TEMPLATE_FILE.exists():
            _SPEAKER_TEMPLATE_FILE.unlink()
