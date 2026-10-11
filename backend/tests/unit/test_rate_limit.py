import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.rate_limit import enforce_login_rate_limit, enforce_rate_limit, login_subject


async def test_allows_requests_up_to_limit() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=3)
    await enforce_rate_limit(db, "user-1", 3)
    assert db.scalar.await_count == 1
    assert db.commit.await_count == 1


async def test_rejects_request_above_limit_with_retry_after() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=4)
    now = datetime.datetime(2026, 10, 10, 12, 34, 17, tzinfo=datetime.UTC)
    with pytest.raises(HTTPException) as raised:
        await enforce_rate_limit(db, "user-1", 3, now=now)
    assert raised.value.status_code == 429
    assert raised.value.headers == {"Retry-After": "43"}


def test_login_subject_is_stable_but_does_not_expose_email() -> None:
    subject = login_subject("USER@example.com", "session-secret")
    assert subject == login_subject("user@example.com", "session-secret")
    assert subject != login_subject("user@example.com", "different-secret")
    assert "user@example.com" not in subject


async def test_login_limiter_uses_the_hashed_subject() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=1)
    await enforce_login_rate_limit(db, "user@example.com", "session-secret", 3)
    params = db.scalar.await_args.args[1]
    assert params["value"] == login_subject("user@example.com", "session-secret")


async def test_new_fixed_window_allows_request_after_rollover() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[3, 1])
    await enforce_rate_limit(
        db,
        "user-1",
        3,
        now=datetime.datetime(2026, 10, 10, 12, 34, 59, tzinfo=datetime.UTC),
    )
    await enforce_rate_limit(
        db,
        "user-1",
        3,
        now=datetime.datetime(2026, 10, 10, 12, 35, 0, tzinfo=datetime.UTC),
    )
    first_window = db.scalar.await_args_list[0].args[1]["window"]
    second_window = db.scalar.await_args_list[1].args[1]["window"]
    assert second_window - first_window == datetime.timedelta(minutes=1)
