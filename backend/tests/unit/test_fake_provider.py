import pytest

from app.agent.contextualize import ContextOutput
from app.agent.nodes import GenerateOutput
from app.config import Settings
from app.llm.client import LLMClient


@pytest.mark.asyncio
async def test_fake_provider_returns_safe_structured_query_output() -> None:
    client = LLMClient(Settings(LLM_PROVIDER="fake"))
    output, usage = await client.complete_structured("strong", [], GenerateOutput)
    await client.aclose()
    assert output.sql == "SELECT 1 AS value"
    assert output.tables_used == []
    assert usage.total_tokens == 0


@pytest.mark.asyncio
async def test_fake_provider_routes_to_database_query() -> None:
    client = LLMClient(Settings(LLM_PROVIDER="fake"))
    output, _ = await client.complete_structured("fast", [], ContextOutput)
    await client.aclose()
    assert output.intent == "DATABASE_QUERY"
