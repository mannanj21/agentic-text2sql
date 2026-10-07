"""Eval runner logic [S5.4]."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.compare import compare_results
from evaluation.metrics import EvalResult, MetricsReport, compute_metrics
from evaluation.validate_dataset import DatasetCase

# We import backend modules natively for eval execution.
from app.config import Settings
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, Run, User
from app.agent.graph import build_graph
from app.llm.client import LLMClient
from app.persistence.tracing import RunRecorder
from sqlalchemy import select


class RunnerContext:
    def __init__(self, settings: Settings, db, user: User, connections: dict[str, Connection], llm):
        self.settings = settings
        self.db = db
        self.user = user
        self.connections = connections
        self.llm = llm


async def setup_eval_context(settings: Settings) -> RunnerContext:
    db = AsyncSessionLocal()
    
    # Ensure an eval user exists
    user = await db.scalar(select(User).where(User.email == "eval@example.com"))
    if not user:
        user = User(email="eval@example.com", password_hash="eval")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Ensure connections exist (we assume target dbs are local for eval)
    # The passwords should match the local setup or be fake if mocked.
    connections = {}
    for db_name in ["ecommerce", "pagila"]:
        conn = await db.scalar(select(Connection).where(Connection.name == f"eval_{db_name}"))
        if not conn:
            conn = Connection(
                user_id=user.id,
                name=f"eval_{db_name}",
                host="localhost",
                port=5432,
                database=db_name,
                username="postgres",
                encrypted_password="dummy",  # Mocked out in tests or set to real encrypted
                allowed_schemas=["public"],
            )
            db.add(conn)
            await db.commit()
            await db.refresh(conn)
        connections[db_name] = conn

    llm = LLMClient(settings)
    return RunnerContext(settings, db, user, connections, llm)


async def run_case(ctx: RunnerContext, case: DatasetCase) -> EvalResult:
    """Run a single evaluation case through the graph and return the result metrics."""
    conn = ctx.connections[case.db]
    
    initial_state = {
        "question": case.question,
        "history": [],
    }
    
    latency = {"llm": 0.0, "db": 0.0, "other": 0.0}
    start_times = {}
    retries = 0
    final_sql = None
    final_answer = None
    pred_columns = []
    pred_row_count = 0
    error_msg = None
    
    # Re-use conversation_id = "eval-conv" to simplify
    conv_id = f"eval-{case.id}"
    
    try:
        async with RunRecorder(
            ctx.db,
            conversation_id=conv_id,
            user_id=ctx.user.id,
            question=case.question,
        ) as recorder:
            graph = build_graph(ctx.llm, conn, ctx.db)
            
            async for event in graph.astream_events(initial_state, version="v2"):
                kind = event["event"]
                name = event["name"]
                
                if name not in {"guardrail", "generate", "validate", "execute", "repair", "answer"}:
                    continue
                    
                if kind == "on_chain_start":
                    start_times[name] = time.time()
                    await recorder.start_step(name)
                elif kind == "on_chain_end":
                    step_duration = time.time() - start_times.pop(name, time.time())
                    
                    if name in ("generate", "repair"):
                        latency["llm"] += step_duration
                    elif name == "execute":
                        latency["db"] += step_duration
                    else:
                        latency["other"] += step_duration
                        
                    data = event["data"].get("output", {})
                    if isinstance(data, dict):
                        if name == "repair":
                            retries += 1
                        
                        if data.get("status") == "failed":
                            error_msg = data.get("error")
                            if name == "repair" and data.get("error_kind") == "repair_budget_exhausted":
                                pass
                                
                        if "validated_sql" in data:
                            final_sql = data["validated_sql"]
                        if "answer" in data:
                            final_answer = data["answer"]
                            
                    # End step in recorder
                    # We skip proper step ending object lookup for brevity, just getting the last one
                    if recorder.run.steps:
                        await recorder.end_step(recorder.run.steps[-1])
                        
            # Execute gold SQL directly on DB using our app.tools.execution function
            # Since this is an eval, we want to run the gold SQL to get gold rows
            gold_rows = []
            if case.gold_sql:
                from app.tools.execution import _run_query_internal
                try:
                    gold_cols, g_rows = await _run_query_internal(conn, ctx.db, case.gold_sql)
                    gold_rows = g_rows
                except Exception as e:
                    logging.warning(f"Failed to run gold SQL for {case.id}: {e}")
                    
            # Get predicted rows
            pred_rows = []
            if final_sql:
                from app.tools.execution import _run_query_internal
                try:
                    p_cols, p_rows = await _run_query_internal(conn, ctx.db, final_sql)
                    pred_rows = p_rows
                    pred_columns = [c["name"] for c in p_cols]
                    pred_row_count = len(p_rows)
                except Exception as e:
                    error_msg = str(e)

            # Compare results
            if case.expected_intent == "ANSWER" and case.gold_sql:
                comp = compare_results(gold_rows, pred_rows, order_sensitive=case.order_sensitive)
                accuracy = comp.exact_match
                lenient_acc = comp.lenient_match
                reason = comp.reason
            else:
                # If non-answer, check if the graph recognized the intent correctly
                # We do this by seeing if the final answer explicitly states it or if error_msg matches.
                # For now, let's just check if it returned the expected intent in the 'answer' node metadata 
                # (which we didn't implement fully yet for intent routing). Let's assume false for unsupported intents for now.
                accuracy = False
                lenient_acc = False
                reason = "Not implemented routing check"

            # Tokens & Cost from run
            tokens = sum(s.tokens for s in recorder.run.steps)
            cost = sum(s.cost for s in recorder.run.steps)
            
            return EvalResult(
                case_id=case.id,
                split=case.split,
                difficulty=case.difficulty,
                category=case.category,
                expected_intent=case.expected_intent,
                success=error_msg is None,
                accuracy=accuracy,
                lenient_accuracy=lenient_acc,
                expected_tables=set(case.expected_tables),
                used_tables=set(),  # To do: parse final_sql to extract tables
                retries=retries,
                tokens=tokens,
                cost=cost,
                latency_llm=latency["llm"],
                latency_db=latency["db"],
                latency_total=latency["llm"] + latency["db"] + latency["other"],
                error=error_msg,
                reason=reason,
            )
            
    except Exception as exc:
        return EvalResult(
            case_id=case.id, split=case.split, difficulty=case.difficulty, category=case.category,
            expected_intent=case.expected_intent, success=False, accuracy=False, lenient_accuracy=False,
            expected_tables=set(case.expected_tables), used_tables=set(), retries=0, tokens=0, cost=0.0,
            latency_llm=0.0, latency_db=0.0, latency_total=0.0, error=str(exc), reason="Exception"
        )
