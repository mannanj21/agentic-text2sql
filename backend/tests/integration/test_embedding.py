import httpx
import pytest
from sqlalchemy import text

from app.config import Settings
from app.database.core import AsyncSessionLocal
from app.database.models import SchemaTable
from app.llm.embedding import EmbedderClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_ollama_real_smoke():
    """Smoke test to hit real Ollama. Skip if Ollama is down or model is missing."""
    settings = Settings(EMBEDDING_MODEL="bge-m3", EMBEDDING_DIM=1024)
    embedder = EmbedderClient(settings)

    try:
        vecs = await embedder.aembed(["Hello world", "Agentic SQL"])
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        pytest.skip(f"Ollama not available or model missing: {exc}")
        return
    finally:
        await embedder.aclose()

    assert len(vecs) == 2
    assert len(vecs[0]) == 1024


async def test_store_and_query_pgvector():
    """Test storing and querying pgvector in the database."""
    import uuid

    from app.database.models import Connection, User

    async with AsyncSessionLocal() as db_session:
        # Create test user and connection
        user = User(email=f"emb-{uuid.uuid4()}@example.com", password_hash="hash")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        test_connection = Connection(
            user_id=user.id,
            name="eval_ecommerce",
            host="localhost",
            port=5432,
            database="ecommerce",
            username="postgres",
            encrypted_password="dummy",
            allowed_schemas=["public"],
        )
        db_session.add(test_connection)
        await db_session.commit()
        await db_session.refresh(test_connection)

        vec1 = [0.0] * 1024
        vec1[0] = 1.0

        vec2 = [0.0] * 1024
        vec2[1] = 1.0

        table1 = SchemaTable(
            connection_id=test_connection.id, schema="public", name="sales", embedding=vec1
        )
        table2 = SchemaTable(
            connection_id=test_connection.id, schema="public", name="users", embedding=vec2
        )

        db_session.add_all([table1, table2])
        await db_session.commit()

        # Query using pgvector cosine distance `<=>`
        target_vec = [0.0] * 1024
        target_vec[0] = 1.0
        target_vec[1] = 0.1
        query = text(
            "SELECT name FROM schema_tables WHERE connection_id = :conn_id "
            "ORDER BY embedding <=> cast(:vec as vector) LIMIT 1"
        )

        result = await db_session.execute(
            query, {"conn_id": test_connection.id, "vec": str(target_vec)}
        )
        closest = result.scalar()

        assert closest == "sales"
