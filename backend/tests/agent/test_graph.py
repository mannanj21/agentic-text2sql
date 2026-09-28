"""Agent tests for S3.6: graph happy path, failure routing, and state safety."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.graph import build_graph
from app.agent.nodes import AnswerOutput, GenerateOutput
from app.llm.client import FakeLLM, LLMProviderError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_connection() -> Any:
    """Return a minimal mock Connection object."""
    conn = MagicMock()
    conn.id = "conn-test"
    conn.host = "localhost"
    conn.port = 5432
    conn.database = "testdb"
    conn.username = "readonly"
    conn.encrypted_password = "ENC"  # noqa: S105
    return conn


def _base_state(**overrides: object) -> dict[str, Any]:
    state: dict[str, Any] = {
        "question": "How many rows?",
        "connection_id": "conn-test",
        "conversation_id": "conv-test",
        "user_id": "user-test",
        "schema_ddl": "CREATE TABLE public.t (id int PRIMARY KEY, name text);",
        "dialect": "postgresql",
        "current_date": "2026-01-15",
        "glossary": "",
        "status": "running",
        "error": "",
        "error_kind": "",
        "generated_sql": "",
        "tables_used": [],
        "generate_assumptions": [],
        "validated_sql": "",
        "execution_columns": [],
        "execution_row_count": 0,
        "execution_truncated": False,
        "result_stats": "",
        "result_preview": "",
        "answer": "",
        "answer_assumptions": [],
        "total_tokens": 0,
        "total_cost": 0.0,
    }
    state.update(overrides)
    return state


def _good_fake(valid_sql: str = "SELECT count(*) FROM public.t") -> FakeLLM:
    return FakeLLM(
        {
            "generate": [
                GenerateOutput(
                    sql=valid_sql,
                    tables_used=["public.t"],
                    assumptions=[],
                )
            ],
            "answer": [AnswerOutput(answer="There are **42** rows.", assumptions=[])],
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_completed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full graph run with a valid SQL statement completes successfully."""
    from app.agent import graph as graph_mod
    from app.tools.execution import ExecutionResult

    mock_execute = AsyncMock(
        return_value=ExecutionResult(columns=["count"], rows=[[42]], row_count=1, truncated=False)
    )
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    fake = _good_fake()
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "completed"
    assert "42" in final["answer"]
    assert final["validated_sql"] != ""
    assert mock_execute.called


@pytest.mark.asyncio
async def test_validation_failure_does_not_reach_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM produces invalid SQL, execute must never be called."""
    from app.agent import graph as graph_mod

    mock_execute = AsyncMock()
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    # LLM returns a non-SELECT statement
    fake = FakeLLM(
        {
            "generate": [
                GenerateOutput(
                    sql="DELETE FROM public.t",
                    tables_used=[],
                    assumptions=[],
                )
            ],
            "answer": [],
        }
    )
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "failed"
    assert mock_execute.call_count == 0, "execute must not be called when validation fails"


@pytest.mark.asyncio
async def test_execute_error_yields_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the executor raises ExecutionError, the graph returns a failed state."""
    from app.agent import graph as graph_mod
    from app.tools.execution import ExecutionError

    monkeypatch.setattr(
        graph_mod, "execute", AsyncMock(side_effect=ExecutionError("timeout", "Query timed out"))
    )

    fake = _good_fake()
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "failed"
    assert "timeout" in final.get("error_kind", "")


@pytest.mark.asyncio
async def test_llm_generate_error_yields_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM generate call fails, the graph returns a failed state."""
    from app.agent import graph as graph_mod

    mock_execute = AsyncMock()
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    fake = FakeLLM({"generate": [LLMProviderError("provider down")], "answer": []})
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "failed"
    assert mock_execute.call_count == 0


@pytest.mark.asyncio
async def test_state_contains_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """After graph execution, serialised state must not contain password material."""
    import json

    from app.agent import graph as graph_mod
    from app.tools.execution import ExecutionResult

    monkeypatch.setattr(
        graph_mod,
        "execute",
        AsyncMock(
            return_value=ExecutionResult(columns=["x"], rows=[[1]], row_count=1, truncated=False)
        ),
    )

    fake = _good_fake()
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    serialized = json.dumps(final)
    for word in ("password", "ENC", "api_key", "secret"):
        assert word not in serialized, f"Credential word '{word}' found in serialized state"


@pytest.mark.asyncio
async def test_state_contains_no_raw_rows_beyond_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw rows beyond the 20-row preview cap must not appear in state."""
    from app.agent import graph as graph_mod
    from app.tools.execution import ExecutionResult

    # Return 25 rows
    big_rows = [[f"secret_{i}"] for i in range(25)]
    monkeypatch.setattr(
        graph_mod,
        "execute",
        AsyncMock(
            return_value=ExecutionResult(columns=["x"], rows=big_rows, row_count=25, truncated=True)
        ),
    )

    fake = _good_fake("SELECT x FROM public.t")
    graph = build_graph(fake, _fake_connection())
    final = await graph.ainvoke(_base_state())

    # Rows 20-24 must not appear in the preview
    preview = final.get("result_preview", "")
    for i in range(20, 25):
        assert f"secret_{i}" not in preview, f"Row {i} leaked into state preview"
