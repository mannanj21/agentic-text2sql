from app.agent.planner import QueryPlan, plan_query
from app.llm.client import FakeLLM


async def test_planner_returns_structured_plan() -> None:
    plan, _usage = await plan_query(
        FakeLLM({"plan": [QueryPlan(tables=["public.orders"], aggregation="count")]}),
        "count orders",
        "CREATE TABLE public.orders (id int);",
    )
    assert plan.tables == ["public.orders"]
    assert plan.aggregation == "count"
