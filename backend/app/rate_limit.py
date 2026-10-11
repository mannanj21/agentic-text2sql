"""Postgres-backed fixed-window rate limiting shared across API replicas."""

from __future__ import annotations

import datetime
import hashlib
import hmac
from collections.abc import Callable
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTCNow = Callable[[], datetime.datetime]
CounterKind = Literal["user", "login"]

_USER_INCREMENT = text(
    "INSERT INTO rate_limits (user_id, window_start, count) VALUES (:value, :window, 1) "
    "ON CONFLICT (user_id, window_start) DO UPDATE SET count = rate_limits.count + 1 "
    "RETURNING count"
)
_LOGIN_INCREMENT = text(
    "INSERT INTO login_rate_limits (subject_digest, window_start, count) "
    "VALUES (:value, :window, 1) "
    "ON CONFLICT (subject_digest, window_start) DO UPDATE "
    "SET count = login_rate_limits.count + 1 RETURNING count"
)
_USER_CLEANUP = text("DELETE FROM rate_limits WHERE window_start < :cutoff")
_LOGIN_CLEANUP = text("DELETE FROM login_rate_limits WHERE window_start < :cutoff")


def _current_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _window_start(now: datetime.datetime) -> datetime.datetime:
    return now.replace(second=0, microsecond=0)


def _retry_after(now: datetime.datetime) -> str:
    return str(max(1, 60 - now.second))


def login_subject(email: str, session_secret: str) -> str:
    """Return a keyed digest so failed login counters do not persist raw emails."""
    return hmac.new(
        session_secret.encode("utf-8"), email.casefold().encode("utf-8"), hashlib.sha256
    ).hexdigest()


async def _increment(
    db: AsyncSession, kind: CounterKind, value: str, now: datetime.datetime
) -> int:
    window = _window_start(now)
    count = await db.scalar(
        _LOGIN_INCREMENT if kind == "login" else _USER_INCREMENT,
        {"value": value, "window": window},
    )
    # Keep two minutes so concurrent requests straddling a minute boundary remain safe.
    await db.execute(
        _LOGIN_CLEANUP if kind == "login" else _USER_CLEANUP,
        {"cutoff": window - datetime.timedelta(minutes=2)},
    )
    await db.commit()
    return int(count or 0)


async def _enforce(
    db: AsyncSession,
    *,
    kind: CounterKind,
    value: str,
    limit: int,
    now: datetime.datetime | None = None,
) -> None:
    if limit < 1:
        raise ValueError("Rate limit must be at least one request per minute")
    current = now or _current_utc()
    count = await _increment(db, kind, value, current)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={"Retry-After": _retry_after(current)},
        )


async def enforce_rate_limit(
    db: AsyncSession, user_id: str, limit: int, *, now: datetime.datetime | None = None
) -> None:
    """Apply the authenticated per-user limit and persist the atomic counter."""
    await _enforce(db, kind="user", value=user_id, limit=limit, now=now)


async def enforce_login_rate_limit(
    db: AsyncSession,
    email: str,
    session_secret: str,
    limit: int,
    *,
    now: datetime.datetime | None = None,
) -> None:
    """Apply login throttling before credential verification, including unknown users."""
    await _enforce(
        db,
        kind="login",
        value=login_subject(email, session_secret),
        limit=limit,
        now=now,
    )
