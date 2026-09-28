import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.auth import create_access_token
from app.database.core import AsyncSessionLocal
from app.database.models import User


@pytest.fixture
async def two_users():
    """
    Creates two distinct users (User A and User B).
    Returns a dictionary with clients authenticated as A and B, plus their IDs.
    """
    async with AsyncSessionLocal() as session:
        user_a = User(email="usera@example.com", password_hash="hash_a")
        user_b = User(email="userb@example.com", password_hash="hash_b")
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

        user_a_id = user_a.id
        user_b_id = user_b.id

    token_a = create_access_token(user_a_id)
    token_b = create_access_token(user_b_id)

    client_a = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies={"session": token_a}
    )
    client_b = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies={"session": token_b}
    )

    yield {
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "client_a": client_a,
        "client_b": client_b,
    }

    # Cleanup (usually DB is rolled back or dropped, but we can explicitly clean up clients)
    await client_a.aclose()
    await client_b.aclose()
