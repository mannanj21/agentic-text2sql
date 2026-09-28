import asyncio
import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database.core import AsyncSessionLocal
from app.database.crypto import CredentialCipher

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

settings = get_settings()


async def test_alembic_migrations() -> None:
    """Test that migrations can upgrade and downgrade cleanly."""
    # We run alembic commands via the CLI equivalent using subprocess.run
    # This ensures they run exactly like they would in production.

    # Downgrade to base
    process = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=os.path.join(os.path.dirname(__file__), "../../"),
    )
    assert process.returncode == 0

    # Upgrade to head
    process = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), "../../"),
    )
    assert process.returncode == 0


async def test_tables_and_indexes_exist() -> None:
    """Verify that all required tables and specific indexes exist."""
    db_url = settings.DATABASE_URL.get_secret_value()
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        # Check tables
        tables = [
            "users",
            "connections",
            "schema_tables",
            "schema_columns",
            "schema_indexes",
            "schema_relationships",
            "glossary_terms",
            "conversations",
            "messages",
            "runs",
            "run_steps",
            "run_attempts",
            "rate_limits",
        ]
        for table in tables:
            result = await conn.execute(text("SELECT to_regclass(:table)"), {"table": table})
            assert result.scalar() == table

        # Check vector extension
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar() == "vector"
    await engine.dispose()


async def test_cascade_delete() -> None:
    """Test that deleting a user cascades to connections, conversations, and runs."""
    async with AsyncSessionLocal() as session:
        from app.database.models import Connection, Conversation, Run, User

        user = User(email="test@example.com", password_hash="hash")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        conn = Connection(
            user_id=user.id,
            name="Test",
            host="localhost",
            port=5432,
            database="db",
            username="u",
            encrypted_password="p",
        )
        conv = Conversation(user_id=user.id, connection_id=conn.id)
        session.add(conn)
        await session.commit()
        await session.refresh(conn)
        conv.connection_id = conn.id
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        run = Run(conversation_id=conv.id, user_id=user.id, question="Q")
        session.add(run)
        await session.commit()

        # Delete user
        await session.delete(user)
        await session.commit()

        # Verify cascades
        user_exists = await session.get(User, user.id)
        conn_exists = await session.get(Connection, conn.id)
        conv_exists = await session.get(Conversation, conv.id)
        run_exists = await session.get(Run, run.id)

        assert user_exists is None
        assert conn_exists is None
        assert conv_exists is None
        assert run_exists is None


async def test_connection_password_is_encrypted_in_the_database() -> None:
    """Connection rows must never persist the target database password as plaintext."""
    from app.database.models import Connection, User

    plaintext = "target-password-that-must-not-be-stored"
    cipher = CredentialCipher(settings.ENCRYPTION_KEY)
    encrypted = cipher.encrypt(plaintext)

    async with AsyncSessionLocal() as session:
        user = User(email=f"crypto-{uuid.uuid4()}@example.com", password_hash="hash")
        session.add(user)
        await session.flush()
        connection = Connection(
            user_id=user.id,
            name="Encrypted connection",
            host="db.example.test",
            port=5432,
            database="analytics",
            username="readonly",
            encrypted_password=encrypted,
        )
        session.add(connection)
        await session.commit()

        stored_password = await session.scalar(
            select(Connection.encrypted_password).where(Connection.id == connection.id)
        )

    assert stored_password == encrypted
    assert stored_password != plaintext
    assert plaintext not in stored_password
