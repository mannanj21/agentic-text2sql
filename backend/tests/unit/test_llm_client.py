import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.client import FakeLLM, LLMClient, LLMProviderError, TokenUsage


class Reply(BaseModel):
    answer: str


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5432/test",
        "ENCRYPTION_KEY": "j7ZZ0R23U8_dAt-AEuSvdEvtdgxHZhVNPHkmjkuxUQQ=",
        "SESSION_SECRET": "test-session-secret",
        "LLM_PROVIDER": "gemini",
        "LLM_API_KEY": "not-a-real-key",
        "LLM_MAX_RETRIES": 2,
    }
    values.update(overrides)
    return Settings(**values)


def gemini_response(content: str) -> dict[str, object]:
    return {
        "candidates": [{"content": {"parts": [{"text": content}]}}],
        "usageMetadata": {
            "promptTokenCount": 7,
            "candidatesTokenCount": 3,
            "totalTokenCount": 10,
        },
    }


@pytest.mark.asyncio
async def test_retries_rate_limit_then_returns_structured_response() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "limited"})
        return httpx.Response(200, json=gemini_response('{"answer":"ok"}'))

    sleeps: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = LLMClient(
        settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=capture_sleep,
        random_fn=lambda: 0.0,
    )
    parsed, usage = await client.complete_structured(
        "fast", [{"role": "user", "content": "Hi"}], Reply
    )

    assert parsed == Reply(answer="ok")
    assert usage == TokenUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10, cost_usd=0.0)
    assert calls == 2
    assert sleeps == [0.5]
    await client.aclose()


@pytest.mark.asyncio
async def test_malformed_json_reasks_once_then_raises_controlled_error() -> None:
    responses = iter(
        [
            httpx.Response(200, json=gemini_response("not json")),
            httpx.Response(200, json=gemini_response("still not json")),
        ]
    )
    client = LLMClient(
        settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: next(responses))),
        sleep=lambda _: None,
    )

    with pytest.raises(LLMProviderError, match="valid structured output"):
        await client.complete_structured("fast", [{"role": "user", "content": "Hi"}], Reply)
    await client.aclose()


@pytest.mark.asyncio
async def test_cache_records_then_replays_without_a_provider_call(tmp_path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=gemini_response('{"answer":"cached"}'))

    record = LLMClient(
        settings(LLM_CACHE_MODE="record"),
        cache_dir=tmp_path,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    first, _ = await record.complete_structured("fast", [{"role": "user", "content": "Hi"}], Reply)
    await record.aclose()
    replay = LLMClient(settings(LLM_CACHE_MODE="replay"), cache_dir=tmp_path)
    second, _ = await replay.complete_structured("fast", [{"role": "user", "content": "Hi"}], Reply)

    assert first == second == Reply(answer="cached")
    assert calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 1
    await replay.aclose()


@pytest.mark.asyncio
async def test_replay_cache_miss_is_controlled_error(tmp_path) -> None:
    client = LLMClient(settings(LLM_CACHE_MODE="replay"), cache_dir=tmp_path)
    with pytest.raises(LLMProviderError, match="cache entry is missing"):
        await client.complete_structured("fast", [{"role": "user", "content": "Hi"}], Reply)
    await client.aclose()


@pytest.mark.asyncio
async def test_fake_llm_supports_node_scripts_and_call_sequence() -> None:
    fake = FakeLLM({"generate": ['{"answer":"first"}', Reply(answer="second")]})
    first, first_usage = await fake.complete_structured("fast", [], Reply, node="generate")
    second, second_usage = await fake.complete_structured("fast", [], Reply, node="generate")

    assert (first, second) == (Reply(answer="first"), Reply(answer="second"))
    assert first_usage == second_usage == TokenUsage.zero()


def test_cache_key_does_not_contain_api_key() -> None:
    key = LLMClient(settings()).cache_key(
        "gemini-2.5-flash", [{"role": "user", "content": "Hi"}], Reply
    )
    assert len(key) == 64
    assert "not-a-real-key" not in key
    assert json.loads(json.dumps({"key": key}))["key"] == key
