"""
Shared FastAPI dependencies: authentication, ownership lookups, rate limiting.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Hashable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import DatabaseConnection, QueryRecord, User
from backend.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def get_owned_connection(db: Session, user: User, connection_id: int) -> DatabaseConnection:
    conn = db.get(DatabaseConnection, connection_id)
    if conn is None or conn.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return conn


def get_owned_query(db: Session, user: User, query_id: int) -> QueryRecord:
    record = db.get(QueryRecord, query_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    return record


class RateLimiter:
    """In-process sliding-window limiter (per worker process)."""

    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self._hits: dict[Hashable, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: Hashable, limit: int, message: str = "Too many requests") -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"{message}. Try again in {retry}s.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


ai_rate_limiter = RateLimiter()
login_rate_limiter = RateLimiter()
LOGIN_ATTEMPTS_PER_MINUTE = 10


def enforce_ai_rate_limit(user: User = Depends(get_current_user)) -> User:
    ai_rate_limiter.check(user.id, settings.AI_RATE_LIMIT_PER_MINUTE, "Too many AI requests")
    return user
