"""LangGraph agent: guardrail → generate → validate → execute → answer.

Stage 4 additions:
  S4.4: input guardrail node
  S4.5: repair loop with shared budget
  S4.6: SSE streaming (see api/conversations.py)

Failure at any node returns a controlled error state.  Validation or
execution failures are routed to the repair node, which decrements the
shared budget and retries from validate.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.contextualize import contextualize
from app.agent.charts import choose_chart
from app.agent.nodes import (
    AnswerOutput,
    GenerateOutput,
    RepairOutput,
    ResultSummary,
    build_result_summary,
    run_answer_node,
    run_generate_node,
    run_repair_node,
)
from app.agent.schema_renderer import render_schema_ddl
from app.config import get_settings
from app.database.models import Connection
from app.guardrails.input_guard import GuardrailError, check_input
from app.guardrails.sql_validator import ValidationError, rewrap_validated, validate_sql
from app.llm.client import FakeLLM, LLMClient, LLMProviderError, TokenUsage
from app.tools.execution import ExecutionError, ExecutionResult, execute
from app.tools.retrieval import retrieve_schema

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
    history: list[dict[str, str]]
    intent: str
    standalone_question: str
    clarification: str
    retrieved_schema_ids: list[str]
    retrieval_latency_ms: int

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
    verification_warning: str
    chart_spec: dict[str, Any]
    answer: str
    answer_assumptions: list[str]

    # --- Control flow ---
    status: Literal["running", "completed", "failed"]
    error: str
    error_kind: str

    # --- Repair loop (S4.5) ---
    repair_budget_remaining: int
    repair_history: list[str]  # previous SQL strings tried (for duplicate detection)
    repair_attempts_summary: list[str]  # human-readable attempt summaries for error messages

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
    # Initialise repair budget on first entry
    settings = get_settings()
    budget = state.get("repair_budget_remaining")
    if budget is None:
        budget = settings.MAX_REPAIR_ATTEMPTS
    return {
        "repair_budget_remaining": budget,
        "repair_history": state.get("repair_history", []),
        "repair_attempts_summary": state.get("repair_attempts_summary", []),
    }


async def generate_node(state: dict[str, Any], *, llm: FakeLLM | LLMClient) -> dict[str, Any]:
    """Call the LLM to produce SQL from the question + schema."""
    try:
        result: GenerateOutput
        usage: TokenUsage
        result, usage = await run_generate_node(
            llm=llm,
            question=state.get("standalone_question") or state["question"],
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


async def contextualize_node(state: dict[str, Any], *, llm: FakeLLM | LLMClient) -> dict[str, Any]:
    try:
        result, usage = await contextualize(
            llm, state["question"], state.get("history", []), state.get("current_date")
        )
    except LLMProviderError:
        return {"intent": "DATABASE_QUERY", "standalone_question": state["question"]}
    return {
        "intent": result.intent,
        "standalone_question": result.standalone_question,
        "clarification": result.clarification or "",
        "total_tokens": state.get("total_tokens", 0) + usage.total_tokens,
        "total_cost": state.get("total_cost", 0.0) + usage.cost_usd,
    }


async def retrieve_node(state: dict[str, Any], *, db: AsyncSession) -> dict[str, Any]:
    # Existing callers/tests may already have a vetted schema context.
    if state.get("schema_ddl"):
        return {}
    result = await retrieve_schema(db, state["connection_id"], state["standalone_question"])
    return {
        "schema_ddl": result.ddl,
        "retrieved_schema_ids": result.table_ids,
        "retrieval_latency_ms": result.latency_ms,
    }


async def schema_context_node(
    state: dict[str, Any], *, connection: Connection, db: AsyncSession
) -> dict[str, Any]:
    return {"schema_ddl": await render_schema_ddl(connection, db)}


async def validate_node(
    state: dict[str, Any], *, connection: Connection, db: AsyncSession
) -> dict[str, Any]:
    """Validate the generated SQL; sets validated_sql or flags for repair."""
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
        "chart_spec": choose_chart(result.columns, result.rows).model_dump(),
    }


async def verify_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic result checks that can trigger the existing repair budget."""
    if state.get("execution_row_count", 0) == 0:
        return {
            "status": "failed",
            "error": "Query returned no rows; re-check filters or dates.",
            "error_kind": "empty_result",
        }
    if state.get("execution_columns") and all(
        "nulls=" in line and "nulls=0" not in line
        for line in state.get("result_stats", "").splitlines()
    ):
        return {
            "status": "failed",
            "error": "All result columns are null.",
            "error_kind": "all_null",
        }
    warning = "Result was truncated." if state.get("execution_truncated") else ""
    return {"verification_warning": warning}


async def repair_node(state: dict[str, Any], *, llm: FakeLLM | LLMClient) -> dict[str, Any]:
    """Attempt to repair a failed SQL statement (S4.5).

    Consumes one unit from *repair_budget_remaining*.  If budget is exhausted
    or the LLM returns a duplicate SQL (already tried), the run is terminated
    with a controlled failure message listing all previous attempts.

    On success, updates *generated_sql* and resets *validated_sql* so the
    graph re-enters the validate→execute path.
    """
    budget: int = state.get("repair_budget_remaining", 0)
    history: list[str] = list(state.get("repair_history", []))
    attempts_summary: list[str] = list(state.get("repair_attempts_summary", []))

    last_sql = state.get("generated_sql", "")
    if last_sql and last_sql not in history:
        history.append(last_sql)

    failure_type = state.get("error_kind", "unknown")
    error_message = state.get("error", "Unknown error")

    attempt_label = f"Attempt {len(history)}: [{failure_type}] {error_message[:120]}"
    attempts_summary.append(attempt_label)

    if budget <= 0:
        return {
            "status": "failed",
            "error": (
                "Repair budget exhausted. All attempts failed:\n" + "\n".join(attempts_summary)
            ),
            "error_kind": "repair_budget_exhausted",
            "repair_budget_remaining": 0,
            "repair_history": history,
            "repair_attempts_summary": attempts_summary,
        }

    # Consume budget
    budget -= 1

    # Call the LLM for a repair
    try:
        result: RepairOutput
        usage: TokenUsage
        result, usage = await run_repair_node(
            llm=llm,
            question=state["question"],
            schema_ddl=state.get("schema_ddl", ""),
            dialect=state.get("dialect", "postgresql"),
            current_date=state.get("current_date") or datetime.date.today().isoformat(),
            glossary=state.get("glossary") or None,
            previous_sqls=history,
            failure_type=failure_type,
            error_message=error_message,
        )
    except LLMProviderError as exc:
        return {
            "status": "failed",
            "error": f"LLM repair failed: {exc}",
            "error_kind": "llm_error",
            "repair_budget_remaining": budget,
            "repair_history": history,
            "repair_attempts_summary": attempts_summary,
        }

    new_sql = result.sql.strip()

    # Detect duplicate SQL — short-circuit even if budget remains
    if not new_sql or new_sql in history:
        return {
            "status": "failed",
            "error": (
                "Repair produced a duplicate or empty SQL.  Stopping to avoid a loop.\n"
                "Attempts so far:\n" + "\n".join(attempts_summary)
            ),
            "error_kind": "repair_duplicate_sql",
            "repair_budget_remaining": budget,
            "repair_history": history,
            "repair_attempts_summary": attempts_summary,
        }

    return {
        # Feed the new SQL back into the validate→execute cycle
        "generated_sql": new_sql,
        "validated_sql": "",  # must be re-validated
        "tables_used": result.tables_used,
        "generate_assumptions": result.assumptions,
        # Reset the failure state so routing can re-enter validate
        "status": "running",
        "error": "",
        "error_kind": "",
        # Budget and history updated
        "repair_budget_remaining": budget,
        "repair_history": history,
        "repair_attempts_summary": attempts_summary,
        "total_tokens": state.get("total_tokens", 0) + usage.total_tokens,
        "total_cost": state.get("total_cost", 0.0) + usage.cost_usd,
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
    return "contextualize" if state.get("status") != "failed" else END


def _route_after_contextualize(state: dict[str, Any]) -> str:
    if state.get("intent") == "DATABASE_QUERY":
        return "retrieve"
    if state.get("intent") == "SCHEMA_QUESTION":
        return "schema_context"
    return "intent_answer"


async def intent_answer_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent")
    if intent == "CLARIFICATION_REQUIRED":
        answer = state.get("clarification") or "Could you clarify what you mean?"
    elif intent == "SCHEMA_QUESTION":
        answer = state.get("schema_ddl") or "No schema metadata is available."
    else:
        answer = "I can help with questions about the connected database, but not that request."
    return {"answer": answer, "answer_assumptions": [], "status": "completed"}


def _route_after_generate(state: dict[str, Any]) -> str:
    return "validate" if state.get("status") != "failed" else END


def _route_after_validate(state: dict[str, Any]) -> str:
    """Route to execute on success, or to repair if budget remains or we need to exhaust it."""
    if state.get("status") != "failed":
        return "execute"
    budget = state.get("repair_budget_remaining", 0)
    history = state.get("repair_history", [])
    # If budget is 0 and history is empty, it's ablation mode -> end immediately.
    if budget == 0 and not history:
        return END
    return "repair"


def _route_after_execute(state: dict[str, Any]) -> str:
    """Route to answer on success, or to repair if budget remains or we need to exhaust it."""
    if state.get("status") != "failed":
        return "verify"
    budget = state.get("repair_budget_remaining", 0)
    history = state.get("repair_history", [])
    if budget == 0 and not history:
        return END
    return "repair"


def _route_after_verify(state: dict[str, Any]) -> str:
    if state.get("status") != "failed":
        return "answer"
    if state.get("repair_budget_remaining", 0) == 0:
        return "answer"
    return "repair"


def _route_after_repair(state: dict[str, Any]) -> str:
    """On a successful repair, re-enter validate.  On duplicate/budget-gone, END."""
    return "validate" if state.get("status") != "failed" else END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

#: Backstop to prevent infinite loops.  LangGraph raises RecursionError if
#: the graph takes more steps than this.  It is intentionally larger than
#: MAX_REPAIR_ATTEMPTS * (validate + execute + repair) to avoid premature
#: termination for legitimate long paths, while still bounding runaway loops.
_RECURSION_LIMIT = 50


def build_graph(
    llm: FakeLLM | LLMClient,
    connection: Connection,
    db: AsyncSession,
) -> Any:
    """Build and compile the agent graph.

    Pipeline: guardrail → generate → validate → execute → answer
                                          ↑             |
                                          └── repair ───┘
              (repair consumes budget and retries validate)

    Returns the compiled LangGraph object.  The caller is responsible for
    supplying a checkpointer when invoking.
    """

    async def _guardrail(state: dict[str, Any]) -> dict[str, Any]:
        return await guardrail_node(state)

    async def _generate(state: dict[str, Any]) -> dict[str, Any]:
        return await generate_node(state, llm=llm)

    async def _contextualize(state: dict[str, Any]) -> dict[str, Any]:
        return await contextualize_node(state, llm=llm)

    async def _retrieve(state: dict[str, Any]) -> dict[str, Any]:
        return await retrieve_node(state, db=db)

    async def _schema_context(state: dict[str, Any]) -> dict[str, Any]:
        return await schema_context_node(state, connection=connection, db=db)

    async def _validate(state: dict[str, Any]) -> dict[str, Any]:
        return await validate_node(state, connection=connection, db=db)

    async def _execute(state: dict[str, Any]) -> dict[str, Any]:
        return await execute_node(state, connection=connection)

    async def _repair(state: dict[str, Any]) -> dict[str, Any]:
        return await repair_node(state, llm=llm)

    async def _verify(state: dict[str, Any]) -> dict[str, Any]:
        return await verify_node(state)

    async def _answer(state: dict[str, Any]) -> dict[str, Any]:
        return await answer_node(state, llm=llm)

    builder: Any = StateGraph(AgentState)
    builder.add_node("guardrail", _guardrail)
    builder.add_node("generate", _generate)
    builder.add_node("contextualize", _contextualize)
    builder.add_node("retrieve", _retrieve)
    builder.add_node("schema_context", _schema_context)
    builder.add_node("intent_answer", intent_answer_node)
    builder.add_node("validate", _validate)
    builder.add_node("execute", _execute)
    builder.add_node("verify", _verify)
    builder.add_node("repair", _repair)
    builder.add_node("answer", _answer)

    builder.set_entry_point("guardrail")
    builder.add_conditional_edges(
        "guardrail", _route_after_guardrail, {"contextualize": "contextualize", END: END}
    )
    builder.add_conditional_edges(
        "contextualize",
        _route_after_contextualize,
        {
            "retrieve": "retrieve",
            "schema_context": "schema_context",
            "intent_answer": "intent_answer",
        },
    )
    builder.add_edge("retrieve", "generate")
    builder.add_edge("schema_context", "intent_answer")
    builder.add_edge("intent_answer", END)
    builder.add_conditional_edges(
        "generate", _route_after_generate, {"validate": "validate", END: END}
    )
    builder.add_conditional_edges(
        "validate",
        _route_after_validate,
        {"execute": "execute", "repair": "repair", END: END},
    )
    builder.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"verify": "verify", "repair": "repair", END: END},
    )
    builder.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"answer": "answer", "repair": "repair"},
    )
    builder.add_conditional_edges(
        "repair",
        _route_after_repair,
        {"validate": "validate", END: END},
    )
    builder.add_edge("answer", END)

    return builder.compile()
