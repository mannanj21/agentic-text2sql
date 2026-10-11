"""Database-level rate limit tests, including independent concurrent sessions."""

import asyncio
import datetime
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.database.core import AsyncSessionLocal
from app.database.models import User
from app.rate_limit import enforce_rate_limit

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _make_user() -> str:
    user = User(email=f"rate-{uuid.uuid4().hex}@example.com", password_hash="not-used")
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
        return user.id


async def _attempt(user_id: str, limit: int) -> bool:
    async with AsyncSessionLocal() as db:
        try:
            await enforce_rate_limit(db, user_id, limit)
        except HTTPException as exc:
            assert exc.status_code == 429
            return False
    return True


async def test_counter_isolated_per_user_and_cleans_expired_windows() -> None:
    first_user, second_user = await _make_user(), await _make_user()
    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=3)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO rate_limits (user_id, window_start, count) "
                "VALUES (:user_id, :window_start, 1)"
            ),
            {"user_id": first_user, "window_start": stale},
        )
        await db.commit()

    assert await _attempt(first_user, 1)
    assert not await _attempt(first_user, 1)
    assert await _attempt(second_user, 1)

    async with AsyncSessionLocal() as db:
        stale_count = await db.scalar(
            text(
                "SELECT count(*) FROM rate_limits "
                "WHERE user_id = :user_id AND window_start = :window_start"
            ),
            {"user_id": first_user, "window_start": stale},
        )
    assert stale_count == 0


async def test_concurrent_sessions_never_admit_more_than_limit() -> None:
    user_id = await _make_user()
    admitted = await asyncio.gather(*(_attempt(user_id, 3) for _ in range(12)))
    assert sum(admitted) == 3
