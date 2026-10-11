"""Optional structured SQL planning."""

from __future__ import annotations

from pydantic import BaseModel

from app.llm.client import FakeLLM, LLMClient, TokenUsage


class QueryPlan(BaseModel):
    tables: list[str] = []
    joins: list[str] = []
    filters: list[str] = []
    aggregation: str | None = None
    group_by: list[str] = []
    limit: int | None = None


async def plan_query(
    llm: FakeLLM | LLMClient, question: str, schema_ddl: str
) -> tuple[QueryPlan, TokenUsage]:
    return await llm.complete_structured(
        "fast",
        [
            {
                "role": "user",
                "content": (f"Plan this SQL query.\nSchema:\n{schema_ddl}\nQuestion: {question}"),
            }
        ],
        QueryPlan,
        node="plan",
    )
