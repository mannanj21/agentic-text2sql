"""Conversations, query, runs, and history endpoints."""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_graph
from app.agent.schema_renderer import render_schema_ddl
from app.auth import current_user
from app.config import get_settings
from app.database.core import get_db
from app.database.models import Connection, Conversation, Message, Run, RunStep, User
from app.llm.client import LLMClient
from app.persistence.tracing import RunRecorder

router = APIRouter(tags=["Conversations"])
CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

settings = get_settings()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _owned_conversation(conv_id: str, user_id: str, db: AsyncSession) -> Conversation:
    conv = await db.scalar(
        select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id)
    )
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


async def _owned_connection(conn_id: str, user_id: str, db: AsyncSession) -> Connection:
    conn = await db.scalar(
        select(Connection).where(Connection.id == conn_id, Connection.user_id == user_id)
    )
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return conn


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    connection_id: str
    title: str | None = Field(default=None, max_length=200)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationResponse(BaseModel):
    id: str
    connection_id: str
    title: str | None
    created_at: datetime.datetime

    @classmethod
    def from_model(cls, conv: Conversation) -> ConversationResponse:
        return cls(
            id=conv.id,
            connection_id=conv.connection_id,
            title=conv.title,
            created_at=conv.created_at,
        )


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class RunStepResponse(BaseModel):
    seq: int
    node: str
    status: str
    latency_ms: int | None
    tokens_in: int | None
    tokens_out: int | None
    cost: float | None
    error: str | None

    @classmethod
    def from_model(cls, step: RunStep) -> RunStepResponse:
        return cls(
            seq=step.seq,
            node=step.node,
            status=step.status,
            latency_ms=step.latency_ms,
            tokens_in=step.tokens_in,
            tokens_out=step.tokens_out,
            cost=step.cost,
            error=step.error,
        )


class RunResponse(BaseModel):
    id: str
    conversation_id: str
    question: str
    status: str
    total_latency_ms: int | None
    tokens: int | None
    cost: float | None
    final_sql: str | None
    answer: str | None
    error: str | None
    steps: list[RunStepResponse]

    @classmethod
    def from_model(cls, run: Run) -> RunResponse:
        answer = None
        if run.result_meta and isinstance(run.result_meta, dict):
            answer = run.result_meta.get("answer")
        return cls(
            id=run.id,
            conversation_id=run.conversation_id,
            question=run.question,
            status=run.status,
            total_latency_ms=run.total_latency_ms,
            tokens=run.tokens,
            cost=run.cost,
            final_sql=run.final_sql,
            answer=answer,
            error=run.error,
            steps=[RunStepResponse.from_model(s) for s in (run.steps or [])],
        )


class QueryResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    sql: str | None
    columns: list[str]
    row_count: int
    truncated: bool
    error: str | None


class HistoryItem(BaseModel):
    conversation_id: str
    run_id: str
    question: str
    status: str
    created_at: datetime.datetime | None


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, db: DbSession
) -> ConversationResponse:
    # Verify the connection belongs to this user
    await _owned_connection(body.connection_id, user.id, db)
    conv = Conversation(user_id=user.id, connection_id=body.connection_id, title=body.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.from_model(conv)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationResponse]:
    convs = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.created_at.desc())
        )
    ).all()
    return [ConversationResponse.from_model(c) for c in convs]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> None:
    conv = await _owned_conversation(conversation_id, user.id, db)
    await db.delete(conv)
    await db.commit()


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: str, body: ConversationRename, user: CurrentUser, db: DbSession
) -> ConversationResponse:
    conv = await _owned_conversation(conversation_id, user.id, db)
    conv.title = body.title
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.from_model(conv)


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/query", response_model=QueryResponse)
async def query_conversation(
    conversation_id: str,
    body: QueryRequest,
    user: CurrentUser,
    db: DbSession,
) -> QueryResponse:
    """Run a text-to-SQL query in a conversation (non-streaming for Stage 3)."""
    conv = await _owned_conversation(conversation_id, user.id, db)
    connection = await _owned_connection(conv.connection_id, user.id, db)

    # Render schema DDL for the LLM context
    schema_ddl = await render_schema_ddl(connection, db)

    # Build LLM client
    llm = LLMClient(settings)

    # Persist user message
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.question,
    )
    db.add(user_msg)
    await db.flush()

    # Run the graph under the RunRecorder
    async with RunRecorder(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
        question=body.question,
    ) as recorder:
        initial_state: dict[str, Any] = {
            "question": body.question,
            "connection_id": conv.connection_id,
            "conversation_id": conversation_id,
            "user_id": user.id,
            "schema_ddl": schema_ddl,
            "dialect": "postgresql",
            "current_date": datetime.date.today().isoformat(),
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

        # Record individual node steps
        async with recorder.step("generate"):
            pass  # Graph handles its own execution; step is used for timing

        graph = build_graph(llm, connection)
        final_state: dict[str, Any] = await graph.ainvoke(initial_state)

        run = recorder.run
        assert run is not None

        # Persist final SQL and result metadata onto the run row
        run.final_sql = final_state.get("validated_sql") or final_state.get("generated_sql")
        run.result_meta = {
            "answer": final_state.get("answer"),
            "assumptions": final_state.get("answer_assumptions", []),
        }
        run.result_preview = {
            "columns": final_state.get("execution_columns", []),
            "row_count": final_state.get("execution_row_count", 0),
            "truncated": final_state.get("execution_truncated", False),
        }

        if final_state.get("status") == "failed":
            run.status = "failed"
            run.error = final_state.get("error", "Unknown error")

    # Persist assistant message
    if final_state.get("answer"):
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=final_state["answer"],
            run_id=recorder.run_id,
        )
        db.add(assistant_msg)

    await db.commit()
    await llm.aclose()

    return QueryResponse(
        run_id=recorder.run_id,
        status=final_state.get("status", "failed"),
        answer=final_state.get("answer") or None,
        sql=run.final_sql,
        columns=final_state.get("execution_columns", []),
        row_count=final_state.get("execution_row_count", 0),
        truncated=final_state.get("execution_truncated", False),
        error=final_state.get("error") or None,
    )


# ---------------------------------------------------------------------------
# Runs and history
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, user: CurrentUser, db: DbSession) -> RunResponse:
    """Retrieve a single run with its trace steps (owner only)."""
    run = await db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user.id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    # Eagerly load steps
    steps = (
        await db.scalars(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.seq))
    ).all()
    run.steps = list(steps)
    return RunResponse.from_model(run)


@router.get("/history", response_model=list[HistoryItem])
async def get_history(user: CurrentUser, db: DbSession) -> list[HistoryItem]:
    """Return recent runs for the current user, newest first."""
    runs = (
        await db.scalars(
            select(Run)
            .where(Run.user_id == user.id)
            .order_by(Run.id.desc())
            .limit(settings.HISTORY_TURNS * 10)
        )
    ).all()
    return [
        HistoryItem(
            conversation_id=r.conversation_id,
            run_id=r.id,
            question=r.question,
            status=r.status,
            created_at=None,
        )
        for r in runs
    ]
