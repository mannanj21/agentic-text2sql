import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database.core import AsyncSessionLocal
from app.database.models import Connection, Conversation, Run, RunAttempt, RunStep, User
from app.logging import run_id_ctx
from app.persistence.tracing import RunRecorder


async def make_conversation() -> tuple[str, str]:
    async with AsyncSessionLocal() as db:
        user = User(email=f"trace-{uuid.uuid4()}@example.com", password_hash="hash")
        connection = Connection(
            user=user,
            name="trace",
            host="localhost",
            port=5432,
            database="db",
            username="user",
            encrypted_password="encrypted",
        )
        conversation = Conversation(user=user, connection=connection)
        db.add_all([user, connection, conversation])
        await db.commit()
        return conversation.id, user.id


@pytest.mark.integration
async def test_recorder_orders_steps_aggregates_usage_and_records_attempts() -> None:
    conversation_id, user_id = await make_conversation()
    async with AsyncSessionLocal() as db:
        async with RunRecorder(
            db, conversation_id=conversation_id, user_id=user_id, question="q"
        ) as trace:
            assert run_id_ctx.get() == trace.run_id
            async with trace.step("generate") as step:
                step.tokens_in, step.tokens_out, step.cost = 10, 5, 0.02
            async with trace.step("validate", tool="validator"):
                pass
            await trace.record_attempt(attempt_no=1, sql="SELECT 1", outcome="success")
        run = await db.get(Run, trace.run_id)
        steps = (await db.scalars(select(RunStep).where(RunStep.run_id == trace.run_id))).all()
        attempts = (
            await db.scalars(select(RunAttempt).where(RunAttempt.run_id == trace.run_id))
        ).all()
    assert run is not None and run.status == "completed"
    assert run.total_latency_ms is not None and run.total_latency_ms > 0
    assert (run.tokens, run.cost) == (15, 0.02)
    assert [(step.seq, step.status) for step in steps] == [(1, "completed"), (2, "completed")]
    assert attempts[0].sql == "SELECT 1"
    assert run_id_ctx.get() is None


@pytest.mark.integration
async def test_recorder_persists_failure_and_cancellation() -> None:
    conversation_id, user_id = await make_conversation()
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError):
            async with (
                RunRecorder(
                    db, conversation_id=conversation_id, user_id=user_id, question="bad"
                ) as trace,
                trace.step("generate"),
            ):
                raise ValueError("bad response")
        failed = await db.get(Run, trace.run_id)
        with pytest.raises(asyncio.CancelledError):
            async with RunRecorder(
                db, conversation_id=conversation_id, user_id=user_id, question="cancel"
            ) as cancelled:
                raise asyncio.CancelledError()
        cancelled_run = await db.get(Run, cancelled.run_id)
    assert failed is not None and failed.status == "failed" and failed.error == "bad response"
    assert cancelled_run is not None and cancelled_run.status == "cancelled"
