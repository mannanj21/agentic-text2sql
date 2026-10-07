"""LangGraph agent: guardrail → generate → validate → execute → answer.

Stage 4 additions: input guardrail node (S4.4).
Repair loop and SSE streaming come in S4.5 and S4.6.
Failure at any node returns a controlled error state.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes import (
    AnswerOutput,
    GenerateOutput,
    ResultSummary,
    build_result_summary,
    run_answer_node,
    run_generate_node,
)
from app.database.models import Connection
from app.guardrails.input_guard import GuardrailError, check_input
from app.guardrails.sql_validator import ValidationError, rewrap_validated, validate_sql
from app.llm.client import FakeLLM, LLMClient, LLMProviderError, TokenUsage
from app.tools.execution import ExecutionError, ExecutionResult, execute

# ---------------------------------------------------------------------------
# Graph state (serializable — NO credentials, NO raw rows beyond preview cap)
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    """Typed, JSON-serialisable graph state.

    Design rules:
    - No credentials anywhere (connection_id is just a reference).
    - Raw query rows are never stored; only the ResultSummary (preview capped
      at PREVIEW_ROWS).
    - All fields are optional so partial states can be resumed.
    """

    # --- Inputs ---
    question: str
    connection_id: str
    conversation_id: str
    user_id: str
    schema_ddl: str
    dialect: str
    current_date: str
    glossary: str

    # --- Node outputs ---
    generated_sql: str
    tables_used: list[str]
    generate_assumptions: list[str]
    validated_sql: str
    execution_columns: list[str]
    execution_row_count: int
    execution_truncated: bool
    result_stats: str
    result_preview: str
    answer: str
    answer_assumptions: list[str]

    # --- Control flow ---
    status: Literal["running", "completed", "failed"]
    error: str
    error_kind: str

    # --- Bookkeeping ---
    total_tokens: int
    total_cost: float


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def guardrail_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic pre-LLM input check (S4.4).

    Checks: empty input, max length, control characters, suspicious Unicode,
    and basic injection heuristics.  Rejections are traced and returned as
    controlled failures so the graph can produce a structured error response.
    """
    question = state.get("question", "")
    try:
        check_input(question)
    except GuardrailError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "error_kind": exc.kind,
        }
    return {}


async def generate_node(state: dict[str, Any], *, llm: FakeLLM | LLMClient) -> dict[str, Any]:
    """Call the LLM to produce SQL from the question + schema."""
    try:
        result: GenerateOutput
        usage: TokenUsage
        result, usage = await run_generate_node(
            llm=llm,
            question=state["question"],
            schema_ddl=state["schema_ddl"],
            dialect=state.get("dialect", "postgresql"),
            current_date=state.get("current_date") or datetime.date.today().isoformat(),
            glossary=state.get("glossary") or None,
        )
    except LLMProviderError as exc:
        return {
            "status": "failed",
            "error": f"LLM generate failed: {exc}",
            "error_kind": "llm_error",
        }
    return {
        "generated_sql": result.sql,
        "tables_used": result.tables_used,
        "generate_assumptions": result.assumptions,
        "total_tokens": state.get("total_tokens", 0) + usage.total_tokens,
        "total_cost": state.get("total_cost", 0.0) + usage.cost_usd,
    }


async def validate_node(
    state: dict[str, Any], *, connection: Connection, db: AsyncSession
) -> dict[str, Any]:
    """Validate the generated SQL; sets validated_sql or fails."""
    sql = state.get("generated_sql", "")
    if not sql:
        return {
            "status": "failed",
            "error": "LLM returned an empty SQL statement.",
            "error_kind": "empty_sql",
        }
    try:
        validated = await validate_sql(sql, connection, db)
    except ValidationError as exc:
        return {
            "status": "failed",
            "error": f"SQL validation failed ({exc.kind}): {exc}",
            "error_kind": exc.kind,
        }
    return {"validated_sql": validated.sql}


async def execute_node(state: dict[str, Any], *, connection: Connection) -> dict[str, Any]:
    """Execute the validated SQL against the target database."""
    sql_str = state.get("validated_sql", "")
    if not sql_str:
        return {
            "status": "failed",
            "error": "No validated SQL to execute.",
            "error_kind": "missing_sql",
        }
    # Re-wrap through the guardrails re-wrap helper (safe: already validated above)
    validated = rewrap_validated(sql_str)
    try:
        result: ExecutionResult = await execute(connection, validated)
    except ExecutionError as exc:
        return {
            "status": "failed",
            "error": f"Query execution failed ({exc.kind}): {exc}",
            "error_kind": exc.kind,
        }
    summary: ResultSummary = build_result_summary(result.columns, result.rows)
    return {
        "execution_columns": result.columns,
        "execution_row_count": result.row_count,
        "execution_truncated": result.truncated,
        "result_stats": summary.stats,
        "result_preview": summary.rows_preview,
    }


async def answer_node(state: dict[str, Any], *, llm: FakeLLM | LLMClient) -> dict[str, Any]:
    """Ask the LLM to produce a natural-language answer from the result summary."""
    summary = ResultSummary(
        columns=state.get("execution_columns", []),
        row_count=state.get("execution_row_count", 0),
        truncated=state.get("execution_truncated", False),
        stats=state.get("result_stats", ""),
        rows_preview=state.get("result_preview", ""),
    )
    try:
        result: AnswerOutput
        usage: TokenUsage
        result, usage = await run_answer_node(
            llm=llm,
            question=state["question"],
            sql=state.get("validated_sql", state.get("generated_sql", "")),
            summary=summary,
        )
    except LLMProviderError as exc:
        return {
            "status": "failed",
            "error": f"LLM answer failed: {exc}",
            "error_kind": "llm_error",
        }
    return {
        "answer": result.answer,
        "answer_assumptions": result.assumptions,
        "status": "completed",
        "total_tokens": state.get("total_tokens", 0) + usage.total_tokens,
        "total_cost": state.get("total_cost", 0.0) + usage.cost_usd,
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def _route_after_guardrail(state: dict[str, Any]) -> str:
    return "generate" if state.get("status") != "failed" else END


def _route_after_generate(state: dict[str, Any]) -> str:
    return "validate" if state.get("status") != "failed" else END


def _route_after_validate(state: dict[str, Any]) -> str:
    return "execute" if state.get("status") != "failed" else END


def _route_after_execute(state: dict[str, Any]) -> str:
    return "answer" if state.get("status") != "failed" else END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(
    llm: FakeLLM | LLMClient,
    connection: Connection,
    db: AsyncSession,
) -> Any:
    """Build and compile the agent graph.

    Pipeline: guardrail → generate → validate → execute → answer

    Returns the compiled LangGraph object.  The caller is responsible for
    supplying a checkpointer when invoking.
    """

    async def _guardrail(state: dict[str, Any]) -> dict[str, Any]:
        return await guardrail_node(state)

    async def _generate(state: dict[str, Any]) -> dict[str, Any]:
        return await generate_node(state, llm=llm)

    async def _validate(state: dict[str, Any]) -> dict[str, Any]:
        return await validate_node(state, connection=connection, db=db)

    async def _execute(state: dict[str, Any]) -> dict[str, Any]:
        return await execute_node(state, connection=connection)

    async def _answer(state: dict[str, Any]) -> dict[str, Any]:
        return await answer_node(state, llm=llm)

    builder: Any = StateGraph(AgentState)
    builder.add_node("guardrail", _guardrail)
    builder.add_node("generate", _generate)
    builder.add_node("validate", _validate)
    builder.add_node("execute", _execute)
    builder.add_node("answer", _answer)

    builder.set_entry_point("guardrail")
    builder.add_conditional_edges(
        "guardrail", _route_after_guardrail, {"generate": "generate", END: END}
    )
    builder.add_conditional_edges(
        "generate", _route_after_generate, {"validate": "validate", END: END}
    )
    builder.add_conditional_edges(
        "validate", _route_after_validate, {"execute": "execute", END: END}
    )
    builder.add_conditional_edges("execute", _route_after_execute, {"answer": "answer", END: END})
    builder.add_edge("answer", END)

    return builder.compile()
