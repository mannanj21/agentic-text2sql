import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.config import Settings
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, SchemaColumn, SchemaTable, User
from app.tools.enrichment import enrich_connection_metadata

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def enrichment_setup():
    async with AsyncSessionLocal() as db:
        user = User(email=f"enrich-{uuid.uuid4()}@example.com", password_hash="hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        connection = Connection(
            user_id=user.id,
            name="eval_ecommerce",
            host="localhost",
            port=5432,
            database="ecommerce",
            username="postgres",
            encrypted_password="dummy",
            allowed_schemas=["public"],
            sample_values_enabled=False,
        )
        db.add(connection)
        await db.commit()
        await db.refresh(connection)

        table = SchemaTable(connection_id=connection.id, schema="public", name="users")
        db.add(table)
        await db.commit()
        await db.refresh(table)

        col1 = SchemaColumn(table_id=table.id, name="id", data_type="integer")
        col2 = SchemaColumn(
            table_id=table.id, name="password_hash", data_type="varchar", is_sensitive=True
        )
        col3 = SchemaColumn(
            table_id=table.id, name="email", data_type="varchar", sensitive_override=True
        )

        db.add_all([col1, col2, col3])
        await db.commit()

        yield connection.id

        # Teardown handled by cascade-delete on the database


async def test_enrichment_preserves_user_edits_and_computes_embeddings(enrichment_setup):
    connection_id = enrichment_setup

    async with AsyncSessionLocal() as db:
        table = (
            await db.scalars(select(SchemaTable).where(SchemaTable.connection_id == connection_id))
        ).first()
        table.description = "User edited description."
        await db.commit()

    # Run enrichment with mocked LLM (user-edited table description must NOT be overwritten)
    with patch("app.tools.enrichment.LLMClient") as mock_llm_cls:
        mock_llm_instance = mock_llm_cls.return_value
        mock_result = MagicMock()
        mock_result.description = "LLM table description"
        col_mock = MagicMock()
        col_mock.name = "id"
        col_mock.description = "LLM id description"
        mock_result.columns = [col_mock]

        mock_usage = MagicMock()
        mock_usage.total_tokens = 50

        mock_llm_instance.complete_structured = AsyncMock(return_value=(mock_result, mock_usage))
        mock_llm_instance.aclose = AsyncMock()

        await enrich_connection_metadata(connection_id)

    async with AsyncSessionLocal() as db:
        table = (
            await db.scalars(select(SchemaTable).where(SchemaTable.connection_id == connection_id))
        ).first()
        columns = (
            await db.scalars(select(SchemaColumn).where(SchemaColumn.table_id == table.id))
        ).all()

        # User edit is preserved (not overwritten by LLM)
        assert table.description == "User edited description."

        # Columns with no description are filled by LLM
        id_col = next(c for c in columns if c.name == "id")
        assert id_col.description == "LLM id description"

        # Embeddings were computed
        assert table.embedding is not None
        assert id_col.embedding is not None


async def test_enrichment_token_cap(enrichment_setup):
    connection_id = enrichment_setup

    # Set cap to 0 — LLM must never be called
    with patch("app.tools.enrichment.get_settings") as mock_get_settings:
        settings = Settings(ENRICHMENT_TOKEN_CAP=0)
        mock_get_settings.return_value = settings

        with patch("app.tools.enrichment.LLMClient") as mock_llm_cls:
            mock_llm_instance = mock_llm_cls.return_value
            mock_llm_instance.complete_structured = AsyncMock()
            mock_llm_instance.aclose = AsyncMock()

            await enrich_connection_metadata(connection_id)

            mock_llm_instance.complete_structured.assert_not_called()


async def test_sample_values_not_gathered_when_opted_out(enrichment_setup):
    connection_id = enrichment_setup

    with (
        patch("app.tools.enrichment._target_engine") as mock_engine,
        patch("app.tools.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_llm_instance = mock_llm_cls.return_value
        mock_llm_instance.complete_structured = AsyncMock()
        mock_llm_instance.aclose = AsyncMock()

        await enrich_connection_metadata(connection_id)
        mock_engine.assert_not_called()


async def test_sample_values_never_for_sensitive(enrichment_setup):
    connection_id = enrichment_setup

    async with AsyncSessionLocal() as db:
        conn = await db.get(Connection, connection_id)
        conn.sample_values_enabled = True
        await db.commit()

    with patch("app.tools.enrichment.resolve_target") as mock_resolve:
        mock_resolve.return_value = MagicMock(
            hostaddr="127.0.0.1", port=5432, original_host="localhost"
        )
        with patch("app.tools.enrichment._target_engine") as mock_engine_func:
            mock_engine = mock_engine_func.return_value
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__aenter__.return_value = mock_conn
            mock_engine.dispose = AsyncMock()

            mock_result = MagicMock()
            mock_result.all.return_value = [("sample1",)]
            mock_conn.execute = AsyncMock(return_value=mock_result)

            with patch("app.tools.enrichment.LLMClient") as mock_llm_cls:
                mock_llm_instance = mock_llm_cls.return_value
                mock_result_llm = MagicMock()
                mock_result_llm.description = "dummy desc"
                mock_result_llm.columns = []
                mock_llm_instance.complete_structured = AsyncMock(
                    return_value=(mock_result_llm, MagicMock(total_tokens=10))
                )
                mock_llm_instance.aclose = AsyncMock()

                await enrich_connection_metadata(connection_id)

            executed_queries = [call[0][0].text for call in mock_conn.execute.call_args_list]

            # Non-sensitive column "id" should be queried
            assert any('"id"' in q for q in executed_queries)

            # Sensitive columns must never be sampled
            # "password_hash" is sensitive via is_sensitive=True
            assert not any('"password_hash"' in q for q in executed_queries)
            # "email" is sensitive via sensitive_override=True
            assert not any('"email"' in q for q in executed_queries)
