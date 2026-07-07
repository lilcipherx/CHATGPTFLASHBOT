"""Symmetric encryption for secrets at rest (AI account API keys).

Values are encrypted with Fernet (AES-128-CBC + HMAC). The key is derived from
``ENC_SECRET`` (falls back to ``ADMIN_JWT_SECRET`` so it works without extra
config, though a dedicated ENC_SECRET is recommended in prod).

Ciphertext is stored with an ``enc::`` prefix so we can transparently read legacy
plaintext values (anything without the prefix is returned as-is). Rotating the
secret invalidates existing ciphertext — re-enter the affected keys in admin.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

_PREFIX = "enc::"
_log = logging.getLogger(__name__)


@lru_cache
def _fernet() -> Fernet:
    # FIX: AUDIT-1 - remove "change-me" weak fallback; require explicit secret
    secret = (settings.enc_secret or settings.admin_jwt_secret)
    if not secret:
        raise RuntimeError("no encryption secret configured: set ENC_SECRET or ADMIN_JWT_SECRET")
    secret = secret.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty input passes through unchanged."""
    if not plaintext:
        return plaintext
    token = _fernet().encrypt(plaintext.encode()).decode()
    return _PREFIX + token


def decrypt(value: str) -> str:
    """Decrypt a stored secret. Legacy/plaintext values (no prefix) are returned
    unchanged. A value we CANNOT decrypt (wrong/rotated key) yields an empty
    string, so the affected account reads as unconfigured (``is_available()`` ->
    False) and is skipped — rather than sending the raw ``enc::`` ciphertext
    upstream as a bogus API key and burning a request on a guaranteed auth error."""
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        _log.error(
            "crypto.decrypt_failed: ENC_SECRET likely rotated/mismatched; "
            "re-enter the affected API key in the admin panel."
        )
        return ""
