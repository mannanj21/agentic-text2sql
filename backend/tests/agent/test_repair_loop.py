"""Agent tests for S4.5: repair loop and shared budget logic."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_graph
from app.agent.nodes import AnswerOutput, GenerateOutput, RepairOutput
from app.llm.client import FakeLLM
from app.tools.execution import ExecutionError, ExecutionResult

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
    conn.allowed_schemas = ["public"]
    return conn


def _fake_db() -> AsyncMock:
    """Return an async DB session whose metadata query has no sensitive columns."""
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result
    return db


@pytest.fixture(autouse=True)
def _stub_validator_explain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep graph tests unit-level while the validator owns the EXPLAIN boundary."""
    from app.guardrails import sql_validator

    monkeypatch.setattr(sql_validator, "explain", AsyncMock())


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_loop_succeeds_after_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validation failure is repaired successfully."""
    from app.agent import graph as graph_mod

    # Execute is called exactly once with the *repaired* SQL
    mock_execute = AsyncMock(
        return_value=ExecutionResult(columns=["count"], rows=[[42]], row_count=1, truncated=False)
    )
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    # 1. Generate yields bad SQL
    # 2. Validation fails
    # 3. Repair yields good SQL
    # 4. Validation succeeds
    # 5. Execute succeeds
    # 6. Answer succeeds
    fake = FakeLLM(
        {
            "generate": [
                GenerateOutput(sql="DELETE FROM public.t", tables_used=[], assumptions=[])
            ],
            "repair": [
                RepairOutput(
                    sql="SELECT count(*) FROM public.t",
                    tables_used=["public.t"],
                    assumptions=["Changed DELETE to SELECT"],
                )
            ],
            "answer": [AnswerOutput(answer="There are **42** rows.", assumptions=[])],
        }
    )

    graph = build_graph(fake, _fake_connection(), _fake_db())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "completed"
    assert "42" in final["answer"]
    assert final["repair_budget_remaining"] == 2  # Consumed 1 of 3
    assert len(final["repair_history"]) == 1
    assert final["repair_history"][0] == "DELETE FROM public.t"
    assert "unauthorized_node" in final["repair_attempts_summary"][0]
    assert mock_execute.call_count == 1


@pytest.mark.asyncio
async def test_repair_loop_succeeds_after_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An execution error (e.g. timeout) is repaired successfully."""
    from app.agent import graph as graph_mod

    # First execute call raises ExecutionError, second succeeds
    mock_execute = AsyncMock(
        side_effect=[
            ExecutionError("timeout", "Statement timeout"),
            ExecutionResult(columns=["count"], rows=[[42]], row_count=1, truncated=False),
        ]
    )
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    fake = FakeLLM(
        {
            "generate": [
                GenerateOutput(
                    sql="SELECT count(*) FROM public.t, public.t t2", tables_used=[], assumptions=[]
                )
            ],
            "repair": [
                RepairOutput(
                    sql="SELECT count(*) FROM public.t",
                    tables_used=["public.t"],
                    assumptions=["Removed cartesian join to fix timeout"],
                )
            ],
            "answer": [AnswerOutput(answer="There are **42** rows.", assumptions=[])],
        }
    )

    graph = build_graph(fake, _fake_connection(), _fake_db())
    final = await graph.ainvoke(_base_state())

    assert final["status"] == "completed"
    assert final["repair_budget_remaining"] == 2
    assert "timeout" in final["repair_attempts_summary"][0]
    assert mock_execute.call_count == 2


@pytest.mark.asyncio
async def test_repair_budget_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the LLM repeatedly fails, the run stops with a controlled failure listing attempts."""
    from app.agent import graph as graph_mod

    mock_execute = AsyncMock(side_effect=ExecutionError("syntax", "Bad syntax"))
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    fake = FakeLLM(
        {
            "generate": [GenerateOutput(sql="SELECT 1", tables_used=[], assumptions=[])],
            "repair": [
                RepairOutput(sql="SELECT 2", tables_used=[], assumptions=[]),
                RepairOutput(sql="SELECT 3", tables_used=[], assumptions=[]),
                RepairOutput(sql="SELECT 4", tables_used=[], assumptions=[]),
                RepairOutput(
                    sql="SELECT 5", tables_used=[], assumptions=[]
                ),  # Should not be reached
            ],
            "answer": [],
        }
    )

    # Initial state sets repair budget to 2 for a quicker test
    graph = build_graph(fake, _fake_connection(), _fake_db())
    final = await graph.ainvoke(_base_state(repair_budget_remaining=2))

    assert final["status"] == "failed"
    assert final["error_kind"] == "repair_budget_exhausted"
    assert final["repair_budget_remaining"] == 0
    assert len(final["repair_history"]) == 3
    assert "Attempt 1:" in final["error"]
    assert "Attempt 2:" in final["error"]
    assert "Attempt 3:" in final["error"]
    assert "exhausted" in final["error"].lower()


@pytest.mark.asyncio
async def test_repair_duplicate_sql_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    """If repair returns SQL we have already tried, the loop terminates early."""
    from app.agent import graph as graph_mod

    mock_execute = AsyncMock()
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    # Validation will fail both times for DELETE
    fake = FakeLLM(
        {
            "generate": [
                GenerateOutput(sql="DELETE FROM public.t", tables_used=[], assumptions=[])
            ],
            "repair": [
                # LLM stubbornly returns the exact same bad SQL
                RepairOutput(sql="DELETE FROM public.t", tables_used=[], assumptions=[])
            ],
            "answer": [],
        }
    )

    graph = build_graph(fake, _fake_connection(), _fake_db())
    # Start with plenty of budget
    final = await graph.ainvoke(_base_state(repair_budget_remaining=5))

    assert final["status"] == "failed"
    assert final["error_kind"] == "repair_duplicate_sql"
    # Budget was only decremented once
    assert final["repair_budget_remaining"] == 4
    assert mock_execute.call_count == 0


@pytest.mark.asyncio
async def test_repair_zero_budget_no_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    """If budget starts at 0 (e.g. ablation), no repair is attempted."""
    from app.agent import graph as graph_mod

    mock_execute = AsyncMock()
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    fake = FakeLLM(
        {
            "generate": [
                GenerateOutput(sql="DELETE FROM public.t", tables_used=[], assumptions=[])
            ],
            "repair": [RepairOutput(sql="SELECT 1", tables_used=[], assumptions=[])],
            "answer": [],
        }
    )

    graph = build_graph(fake, _fake_connection(), _fake_db())
    final = await graph.ainvoke(_base_state(repair_budget_remaining=0))

    assert final["status"] == "failed"
    # Should be the validation error directly, not a repair error
    assert final["error_kind"] == "unauthorized_node"
    assert mock_execute.call_count == 0
    # No repair attempts made
    assert len(final.get("repair_history", [])) == 0


@pytest.mark.asyncio
async def test_repair_recursion_limit_backstop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Graph recursion_limit bounds runaway loops (test requires LangGraph config)."""
    from langgraph.errors import GraphRecursionError

    from app.agent import graph as graph_mod

    # Force execution error every time
    mock_execute = AsyncMock(side_effect=ExecutionError("timeout", "timeout"))
    monkeypatch.setattr(graph_mod, "execute", mock_execute)

    # Return slightly different SQL each time to defeat the duplicate check
    repair_outputs = [
        RepairOutput(sql=f"SELECT {i}", tables_used=[], assumptions=[]) for i in range(1, 100)
    ]

    fake = FakeLLM(
        {
            "generate": [GenerateOutput(sql="SELECT 0", tables_used=[], assumptions=[])],
            "repair": repair_outputs,
            "answer": [],
        }
    )

    graph = build_graph(fake, _fake_connection(), _fake_db())
    # Set a ridiculously high budget but a small recursion limit
    config = {"recursion_limit": 5}

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(_base_state(repair_budget_remaining=100), config)
