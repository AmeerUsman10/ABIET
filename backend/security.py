"""
Password hashing, access tokens, and encryption of stored database passwords.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72


@lru_cache
def get_secret_key() -> str:
    """
    Return the signing/encryption secret.

    Uses ``SECRET_KEY`` when set. Otherwise a key is generated once and kept in
    ``DATA_DIR/.secret_key`` so sessions and stored connection passwords survive
    restarts.
    """
    if settings.SECRET_KEY:
        return settings.SECRET_KEY
    key_file = settings.DATA_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(48)
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    logger.warning("SECRET_KEY not set; generated one at %s. Set SECRET_KEY in production.", key_file)
    return key


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except ValueError:
        return False


# --- Access tokens -----------------------------------------------------------


def create_access_token(user_id: int, username: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, get_secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id in a valid token, or ``None``."""
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# --- Stored secrets ----------------------------------------------------------


@lru_cache
def _fernet() -> Fernet:
    digest = hashlib.sha256(b"abiet-connection-secrets:" + get_secret_key().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("Stored connection password could not be decrypted (SECRET_KEY changed?)")
        return None
