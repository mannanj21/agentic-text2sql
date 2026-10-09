import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.database.core import AsyncSessionLocal
from app.database.models import (
    Connection,
    GlossaryTerm,
    SchemaColumn,
    SchemaRelationship,
    SchemaTable,
    User,
)
from app.tools.retrieval import retrieve_schema

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def retrieval_setup():
    async with AsyncSessionLocal() as db:
        user = User(email=f"rag-{uuid.uuid4()}@example.com", password_hash="hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        conn = Connection(
            user_id=user.id,
            name="test_rag",
            host="localhost",
            port=5432,
            database="db",
            username="user",
            encrypted_password="pwd",
            allowed_schemas=["public"],
        )
        db.add(conn)
        await db.commit()
        await db.refresh(conn)

        # Create two tables and columns
        t1 = SchemaTable(connection_id=conn.id, schema="public", name="users")
        t2 = SchemaTable(connection_id=conn.id, schema="public", name="orders")
        t3 = SchemaTable(connection_id=conn.id, schema="public", name="unrelated")
        db.add_all([t1, t2, t3])
        await db.commit()

        c1 = SchemaColumn(table_id=t1.id, name="id", data_type="int", is_pk=True)
        c2 = SchemaColumn(table_id=t2.id, name="user_id", data_type="int")
        c3 = SchemaColumn(table_id=t3.id, name="foo", data_type="int")
        db.add_all([c1, c2, c3])
        await db.commit()

        # FK users.id -> orders.user_id
        # Wait, the relationship is from orders.user_id to users.id
        rel = SchemaRelationship(
            connection_id=conn.id,
            from_column_id=c2.id,
            to_column_id=c1.id,
        )
        db.add(rel)

        # Glossary term
        gt = GlossaryTerm(
            connection_id=conn.id,
            term="Active Orders",
            definition="Orders placed in the last 30 days.",
        )
        db.add(gt)

        await db.commit()

        yield conn.id


async def test_retrieve_schema_bypasses_if_small(retrieval_setup):
    conn_id = retrieval_setup

    async with AsyncSessionLocal() as db:
        with patch("app.tools.retrieval.get_settings") as mock_settings:
            mock_settings.return_value.RETRIEVAL_MIN_TABLES = 10

            result = await retrieve_schema(db, conn_id, "Show me active orders")

            assert len(result.table_ids) == 3
            assert "CREATE TABLE public.users" in result.ddl
            assert "CREATE TABLE public.orders" in result.ddl
            assert "CREATE TABLE public.unrelated" in result.ddl
            assert "Active Orders: Orders placed in the last 30 days." in result.ddl
            assert "REFERENCES public.users(id)" in result.ddl
            assert result.latency_ms >= 1


async def test_retrieve_schema_vector_search_with_fk_expansion(retrieval_setup):
    conn_id = retrieval_setup

    async with AsyncSessionLocal() as db:
        with patch("app.tools.retrieval.get_settings") as mock_settings:
            # Trigger vector search
            mock_settings.return_value.RETRIEVAL_MIN_TABLES = 1
            mock_settings.return_value.RETRIEVAL_TOP_K = 1

            # Mock DB embeddings
            from sqlalchemy import text

            q1 = f"UPDATE schema_tables SET embedding = '[{','.join(['0'] * 1024)}]' WHERE connection_id = '{conn_id}'"  # noqa: S608, E501
            await db.execute(text(q1))

            q2 = f"UPDATE schema_columns SET embedding = '[{','.join(['0'] * 1024)}]' WHERE table_id IN (SELECT id FROM schema_tables WHERE connection_id = '{conn_id}')"  # noqa: S608, E501
            await db.execute(text(q2))
            await db.commit()

            with patch("app.tools.retrieval.EmbedderClient") as mock_embedder_cls:
                mock_embedder = mock_embedder_cls.return_value
                mock_embedder.aembed = AsyncMock(return_value=[[0.0] * 1024])
                mock_embedder.aclose = AsyncMock()

                result = await retrieve_schema(db, conn_id, "Active orders")

                # One top-k hit plus a one-hop FK expansion is bounded and usable.
                assert 1 <= len(result.table_ids) <= 2
                assert result.ddl
