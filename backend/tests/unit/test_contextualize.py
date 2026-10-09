from app.agent.contextualize import ContextOutput
from app.agent.graph import contextualize_node, intent_answer_node
from app.llm.client import FakeLLM


async def test_contextualize_uses_fast_router_response() -> None:
    llm = FakeLLM(
        {
            "contextualize": [
                ContextOutput(intent="DATABASE_QUERY", standalone_question="sales last month")
            ]
        }
    )
    result = await contextualize_node(
        {"question": "and last month?", "history": []}, llm=llm
    )
    assert result["intent"] == "DATABASE_QUERY"
    assert result["standalone_question"] == "sales last month"


async def test_contextualize_failure_defaults_to_database_query() -> None:
    result = await contextualize_node({"question": "sales", "history": []}, llm=FakeLLM({}))
    assert result == {"intent": "DATABASE_QUERY", "standalone_question": "sales"}


async def test_non_query_intents_do_not_need_sql() -> None:
    result = await intent_answer_node(
        {"intent": "CLARIFICATION_REQUIRED", "clarification": "Which year?"}
    )
    assert result["status"] == "completed"
    assert result["answer"] == "Which year?"
