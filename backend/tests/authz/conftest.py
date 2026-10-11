import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.auth import create_access_token
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, Conversation, GlossaryTerm, Run, User


@pytest.fixture
async def two_users():
    """
    Creates two distinct users (User A and User B).
    Returns a dictionary with clients authenticated as A and B, plus their IDs.
    """
    async with AsyncSessionLocal() as session:
        suffix = uuid.uuid4().hex
        user_a = User(email=f"usera-{suffix}@example.com", password_hash="hash_a")
        user_b = User(email=f"userb-{suffix}@example.com", password_hash="hash_b")
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

        connection = Connection(
            user_id=user_a.id,
            name="authz",
            host="example.com",
            port=5432,
            database="analytics",
            username="readonly",
            encrypted_password="ciphertext",
            allowed_schemas=["public"],
            status="ready",
        )
        session.add(connection)
        await session.flush()
        conversation = Conversation(user_id=user_a.id, connection_id=connection.id, title="authz")
        session.add(conversation)
        await session.flush()
        term = GlossaryTerm(connection_id=connection.id, term="revenue", definition="sales")
        run = Run(
            conversation_id=conversation.id,
            user_id=user_a.id,
            question="authz test",
            status="completed",
        )
        session.add_all([term, run])
        await session.commit()

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
        "resource_ids": {
            "connection_id": connection.id,
            "conversation_id": conversation.id,
            "term_id": term.id,
            "run_id": run.id,
        },
    }

    # Cleanup (usually DB is rolled back or dropped, but we can explicitly clean up clients)
    await client_a.aclose()
    await client_b.aclose()
