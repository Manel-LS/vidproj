"""FastAPI dependencies: database session, current user, rate limiting."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, RateLimitError
from app.core.security import decode_access_token
from app.db.base import get_session
from app.models import User

_bearer = HTTPBearer(auto_error=False, description="JWT issued by /auth/login")

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Please sign in to continue.")
    user_id = decode_access_token(credentials.credentials)
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Your session is no longer valid. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class SlidingWindowRateLimiter:
    """A small in-process limiter.

    Sufficient for a single node; a multi-node deployment should point this at Redis
    (the interface is one method, so swapping it is contained).
    """

    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.requests:
                retry_after = int(self.window - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 20_000:  # bound memory under a spray of unique keys
                for stale_key in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(stale_key, None)
            return True, 0


_general_limiter = SlidingWindowRateLimiter(
    settings.rate_limit_requests, settings.rate_limit_window_seconds
)
_upload_limiter = SlidingWindowRateLimiter(
    settings.rate_limit_upload_requests, settings.rate_limit_window_seconds
)
_auth_limiter = SlidingWindowRateLimiter(12, 60)


def _client_key(request: Request, suffix: str = "") -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")
    return f"{ip}:{suffix}"


def rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = _general_limiter.check(_client_key(request))
    if not allowed:
        raise RateLimitError(
            f"Too many requests. Please wait {retry_after} seconds and try again.",
            details={"retry_after": retry_after},
        )


def upload_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = _upload_limiter.check(_client_key(request, "upload"))
    if not allowed:
        raise RateLimitError(
            f"You are uploading too quickly. Please wait {retry_after} seconds.",
            details={"retry_after": retry_after},
        )


def auth_rate_limit(request: Request) -> None:
    """Tighter limit on sign-in and sign-up, to blunt credential stuffing."""
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = _auth_limiter.check(_client_key(request, "auth"))
    if not allowed:
        raise RateLimitError(
            f"Too many attempts. Please wait {retry_after} seconds before trying again.",
            details={"retry_after": retry_after},
        )
