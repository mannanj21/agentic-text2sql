"""Persisted tracing for graph runs, node steps, and SQL attempts."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Run, RunAttempt, RunStep
from app.logging import run_id_ctx


class RunRecorder:
    """Own a run's lifecycle and record its graph-node execution trace."""

    def __init__(
        self, db: AsyncSession, *, conversation_id: str, user_id: str, question: str
    ) -> None:
        self.db = db
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.question = question
        self.run: Run | None = None
        self._started = 0.0
        self._run_token: object | None = None

    async def __aenter__(self) -> RunRecorder:
        self.run = Run(
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            question=self.question,
            status="running",
        )
        self.db.add(self.run)
        await self.db.flush()
        self._started = time.perf_counter()
        self._run_token = run_id_ctx.set(self.run.id)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, traceback
        assert self.run is not None
        self.run.total_latency_ms = max(1, int((time.perf_counter() - self._started) * 1000))
        if isinstance(exc, asyncio.CancelledError):
            self.run.status, self.run.error = "cancelled", "Run cancelled."
        elif exc is not None:
            self.run.status, self.run.error = "failed", str(exc)
        else:
            self.run.status = "completed"
        totals = await self.db.execute(
            select(
                func.coalesce(func.sum(RunStep.tokens_in), 0),
                func.coalesce(func.sum(RunStep.tokens_out), 0),
                func.coalesce(func.sum(RunStep.cost), 0.0),
            ).where(RunStep.run_id == self.run.id)
        )
        tokens_in, tokens_out, cost = totals.one()
        self.run.tokens = int(tokens_in or 0) + int(tokens_out or 0)
        self.run.cost = float(cost or 0.0)
        await self.db.commit()
        if self._run_token is not None:
            run_id_ctx.reset(self._run_token)  # type: ignore[arg-type]
        return False

    @property
    def run_id(self) -> str:
        if self.run is None:
            raise RuntimeError("RunRecorder has not been entered.")
        return self.run.id

    async def start_step(self, node: str, *, tool: str | None = None) -> RunStep:
        next_seq = await self.db.scalar(
            select(func.coalesce(func.max(RunStep.seq), 0) + 1).where(RunStep.run_id == self.run_id)
        )
        step = RunStep(
            run_id=self.run_id, seq=int(next_seq or 1), node=node, status="running", tool=tool
        )
        self.db.add(step)
        await self.db.flush()
        step._started_at = time.perf_counter()  # Store internally for timing
        return step

    async def end_step(self, step: RunStep, exc: BaseException | None = None) -> None:
        if isinstance(exc, asyncio.CancelledError):
            step.status = "cancelled"
            step.error = "Step cancelled."
        elif exc is not None:
            step.status = "failed"
            step.error = str(exc)
        else:
            step.status = "completed"
        started = getattr(step, "_started_at", time.perf_counter())
        step.latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        await self.db.flush()

    @asynccontextmanager
    async def step(self, node: str, *, tool: str | None = None) -> AsyncIterator[RunStep]:
        step = await self.start_step(node, tool=tool)
        try:
            yield step
        except BaseException as exc:
            await self.end_step(step, exc)
            raise
        else:
            await self.end_step(step)

    async def record_attempt(
        self,
        *,
        attempt_no: int,
        sql: str,
        outcome: str,
        failure_type: str | None = None,
        error: str | None = None,
    ) -> RunAttempt:
        attempt = RunAttempt(
            run_id=self.run_id,
            attempt_no=attempt_no,
            sql=sql,
            outcome=outcome,
            failure_type=failure_type,
            error=error,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt
