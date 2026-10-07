"""Integration tests for conversational querying and SSE streaming [S4.6]."""

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import conversations
from app.api.main import app
from app.auth import create_access_token
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, Conversation, Run, RunStep, User

# ---------------------------------------------------------------------------
# Fixtures & Mocks
# ---------------------------------------------------------------------------

@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
async def auth_client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    user = User(email=f"conv-{uuid.uuid4()}@example.com", password_hash="hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": create_access_token(user.id)},
    ) as client:
        client._user = user  # type: ignore
        yield client

@pytest.fixture
async def sample_connection(db: AsyncSession, auth_client: AsyncClient) -> Connection:
    conn = Connection(
        user_id=auth_client._user.id,  # type: ignore
        name="Test Conn",
        host="localhost",
        port=5432,
        database="test",
        username="test",
        encrypted_password="enc",
        allowed_schemas=["public"]
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn

@pytest.fixture
async def sample_conversation(
    db: AsyncSession, sample_connection: Connection
) -> Conversation:
    conv = Conversation(
        user_id=sample_connection.user_id,
        connection_id=sample_connection.id,
        title="Test Conversation",
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@pytest.fixture(autouse=True)
def reset_sse_starlette_appstatus() -> None:
    """sse-starlette initializes a global asyncio.Event which breaks across test loops."""
    from sse_starlette.sse import AppStatus
    import asyncio
    AppStatus.should_exit_event = asyncio.Event()


@pytest.fixture(autouse=True)
def mock_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the LangGraph execution so we don't need real LLMs or DB queries in API tests."""
    
    # We mock astream_events to yield some sample events
    class MockGraph:
        async def astream_events(self, state: dict[str, Any], version: str) -> AsyncGenerator[dict[str, Any], None]:
            yield {"event": "on_chain_start", "name": "guardrail"}
            yield {"event": "on_chain_end", "name": "guardrail", "data": {"output": {}}}
            
            yield {"event": "on_chain_start", "name": "generate"}
            yield {"event": "on_chain_end", "name": "generate", "data": {"output": {"generated_sql": "SELECT 1"}}}
            
            yield {"event": "on_chain_start", "name": "validate"}
            yield {"event": "on_chain_end", "name": "validate", "data": {"output": {"validated_sql": "SELECT 1"}}}
            
            yield {"event": "on_chain_start", "name": "execute"}
            yield {"event": "on_chain_end", "name": "execute", "data": {"output": {"execution_columns": ["col"], "execution_row_count": 1, "execution_truncated": False}}}
            
            yield {"event": "on_chain_start", "name": "answer"}
            yield {"event": "on_chain_end", "name": "answer", "data": {"output": {"answer": "The answer is 1", "status": "completed"}}}

    monkeypatch.setattr(conversations, "build_graph", lambda *args, **kwargs: MockGraph())

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_sse_streaming_query(
    auth_client: AsyncClient, sample_conversation: Conversation, db: AsyncSession
) -> None:
    """The query endpoint streams SSE events and persists the run and steps."""
    
    events = []
    
    async with auth_client.stream(
        "POST",
        f"/conversations/{sample_conversation.id}/query",
        json={"question": "What is the meaning of life?"}
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
                
    # Verify the sequence of events
    assert any(e["type"] == "node_started" and e["node"] == "guardrail" for e in events)
    assert any(e["type"] == "node_finished" and e["node"] == "guardrail" for e in events)
    assert any(e["type"] == "sql_generated" and e["sql"] == "SELECT 1" for e in events)
    
    final_event = next(e for e in events if e["type"] == "final")
    assert final_event["status"] == "completed"
    assert final_event["answer"] == "The answer is 1"
    assert final_event["sql"] == "SELECT 1"
    
    # Verify DB persistence
    run_id = final_event["run_id"]
    run = await db.scalar(select(Run).where(Run.id == run_id))
    assert run is not None
    assert run.status == "completed"
    assert run.question == "What is the meaning of life?"
    assert run.final_sql == "SELECT 1"
    
    # Verify steps
    steps = (await db.scalars(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.seq))).all()
    assert len(steps) == 5
    assert steps[0].node == "guardrail"
    assert steps[0].status == "completed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_non_streaming_query(
    auth_client: AsyncClient, sample_conversation: Conversation
) -> None:
    """The query endpoint falls back to JSON when stream=False."""
    
    response = await auth_client.post(
        f"/conversations/{sample_conversation.id}/query?stream=false",
        json={"question": "What is the meaning of life?"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["answer"] == "The answer is 1"
    assert data["sql"] == "SELECT 1"
    assert "run_id" in data


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sse_streaming_disconnect_still_persists(
    auth_client: AsyncClient, sample_conversation: Conversation, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the client disconnects mid-stream, the background task still completes and persists the run."""
    import asyncio
    
    class SlowMockGraph:
        async def astream_events(self, state: dict[str, Any], version: str) -> AsyncGenerator[dict[str, Any], None]:
            yield {"event": "on_chain_start", "name": "generate"}
            # Simulate processing delay so the client has time to disconnect
            await asyncio.sleep(0.2)
            yield {"event": "on_chain_end", "name": "generate", "data": {"output": {"generated_sql": "SELECT 1", "status": "completed"}}}
            
    monkeypatch.setattr(conversations, "build_graph", lambda *args, **kwargs: SlowMockGraph())
    
    async with auth_client.stream(
        "POST",
        f"/conversations/{sample_conversation.id}/query",
        json={"question": "Disconnect mid-stream"}
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            # Break immediately to close the connection mid-stream
            break
                
    # Wait for the background task to finish
    await asyncio.sleep(0.3)
    
    # Verify the run was persisted despite the client disconnect
    run = await db.scalar(select(Run).where(Run.question == "Disconnect mid-stream"))
    assert run is not None
    assert run.status == "completed"
    assert run.final_sql == "SELECT 1"
