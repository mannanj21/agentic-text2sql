"""Conversations, query, runs, and history endpoints."""

from __future__ import annotations

import asyncio
import datetime
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import build_graph
from app.auth import current_user
from app.config import get_settings
from app.database.core import AsyncSessionLocal, get_db
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


async def _put_event(
    queue: asyncio.Queue[dict[str, Any] | None] | None, event_type: str, **data: Any
) -> None:
    if queue is not None:
        await queue.put({"type": event_type, **data})


async def background_run_graph(
    initial_state: dict[str, Any],
    conversation_id: str,
    user_id: str,
    connection_id: str,
    queue: asyncio.Queue[dict[str, Any] | None] | None,
) -> None:
    # Use a new DB session for the background task
    async with AsyncSessionLocal() as db:
        # Re-fetch connection
        connection = await db.scalar(select(Connection).where(Connection.id == connection_id))
        if not connection:
            await _put_event(queue, "error", error="Connection not found")
            if queue:
                await queue.put(None)
            return

        llm = LLMClient(settings)
        final_state = initial_state.copy()

        try:
            async with RunRecorder(
                db,
                conversation_id=conversation_id,
                user_id=user_id,
                question=initial_state["question"],
            ) as recorder:
                graph = build_graph(llm, connection, db)

                active_steps = {}
                async for event in graph.astream_events(initial_state, version="v2"):
                    kind = event["event"]
                    name = event["name"]

                    if name not in {
                        "guardrail",
                        "contextualize",
                        "retrieve",
                        "schema_context",
                        "generate",
                        "validate",
                        "execute",
                        "repair",
                        "answer",
                    }:
                        continue

                    if kind == "on_chain_start":
                        await _put_event(queue, "node_started", node=name)
                        active_steps[name] = await recorder.start_step(name)
                    elif kind == "on_chain_end":
                        await _put_event(queue, "node_finished", node=name)
                        step = active_steps.pop(name, None)

                        state_update = event["data"].get("output", {})
                        if isinstance(state_update, dict):
                            final_state.update(state_update)

                            if name in ("generate", "repair") and state_update.get("generated_sql"):
                                await _put_event(
                                    queue, "sql_generated", sql=state_update["generated_sql"]
                                )

                            if state_update.get("status") == "failed":
                                if step:
                                    await recorder.end_step(
                                        step, Exception(state_update.get("error", "Unknown error"))
                                    )
                                if (
                                    name == "repair"
                                    and state_update.get("error_kind") != "repair_budget_exhausted"
                                ):
                                    await _put_event(
                                        queue, "attempt_failed", error=state_update.get("error")
                                    )
                                else:
                                    await _put_event(
                                        queue, "error", error=state_update.get("error")
                                    )
                            else:
                                if step:
                                    await recorder.end_step(step)
                        else:
                            if step:
                                await recorder.end_step(step)

                run = recorder.run
                assert run is not None
                run.final_sql = final_state.get("validated_sql") or final_state.get("generated_sql")
                run.intent = final_state.get("intent")
                run.standalone_question = final_state.get("standalone_question")
                run.result_meta = {
                    "answer": final_state.get("answer"),
                    "assumptions": final_state.get("answer_assumptions", []),
                    "retrieved_schema_ids": final_state.get("retrieved_schema_ids", []),
                    "retrieval_latency_ms": final_state.get("retrieval_latency_ms", 0),
                }
                run.result_preview = {
                    "columns": final_state.get("execution_columns", []),
                    "row_count": final_state.get("execution_row_count", 0),
                    "truncated": final_state.get("execution_truncated", False),
                }

                if final_state.get("status") == "failed":
                    run.status = "failed"
                    run.error = final_state.get("error", "Unknown error")

                if final_state.get("answer"):
                    assistant_msg = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=final_state["answer"],
                        run_id=recorder.run_id,
                    )
                    db.add(assistant_msg)

                await db.commit()

            # Emit final event OUTSIDE the RunRecorder so __aexit__ sets status="completed"
            run = recorder.run
            assert run is not None  # always set after __aenter__
            await _put_event(
                queue,
                "final",
                run_id=recorder.run_id,
                status=run.status,
                answer=final_state.get("answer"),
                sql=run.final_sql,
                columns=final_state.get("execution_columns", []),
                row_count=final_state.get("execution_row_count", 0),
                truncated=final_state.get("execution_truncated", False),
                error=run.error,
            )

        except BaseException as exc:
            await _put_event(queue, "error", error=str(exc))
        finally:
            await llm.aclose()
            if queue:
                await queue.put(None)


@router.post("/conversations/{conversation_id}/query")
async def query_conversation(
    conversation_id: str,
    body: QueryRequest,
    user: CurrentUser,
    db: DbSession,
    stream: bool = True,
) -> Any:
    """Run a text-to-SQL query in a conversation."""
    conv = await _owned_conversation(conversation_id, user.id, db)
    await _owned_connection(conv.connection_id, user.id, db)

    history_runs = (
        await db.scalars(
            select(Run)
            .where(Run.conversation_id == conversation_id, Run.user_id == user.id)
            .order_by(Run.id.desc())
            .limit(settings.HISTORY_TURNS)
        )
    ).all()
    history = [
        {
            "question": run.question,
            "sql": run.final_sql or "",
            "answer_summary": str((run.result_meta or {}).get("answer", ""))[:500],
        }
        for run in reversed(history_runs)
    ]

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.question,
    )
    db.add(user_msg)
    await db.commit()

    initial_state: dict[str, Any] = {
        "question": body.question,
        "connection_id": conv.connection_id,
        "conversation_id": conversation_id,
        "user_id": user.id,
        "schema_ddl": "",
        "history": history,
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

    queue: asyncio.Queue[dict[str, Any] | None]
    if stream:
        queue = asyncio.Queue()
        # Use create_task so the run continues even if the client disconnects.
        # Store the reference to prevent the task from being garbage-collected.
        _bg_task = asyncio.create_task(  # noqa: RUF006
            background_run_graph(
                initial_state,
                conversation_id,
                user.id,
                conv.connection_id,
                queue,
            )
        )

        async def event_generator() -> Any:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield {"data": json.dumps(event)}

        return EventSourceResponse(event_generator())
    else:
        # Non-streaming JSON fallback
        queue = asyncio.Queue()
        await background_run_graph(
            initial_state, conversation_id, user.id, conv.connection_id, queue
        )

        final_event = None
        while not queue.empty():
            event = await queue.get()
            if event is not None and event.get("type") == "final":
                final_event = event

        if not final_event:
            raise HTTPException(status_code=500, detail="Run failed without final event")

        return QueryResponse(**final_event)


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
