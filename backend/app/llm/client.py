"""Provider-agnostic, structured LLM client with safe local response caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

ModelTier = Literal["fast", "strong"]
Message = Mapping[str, str]
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMProviderError(RuntimeError):
    """A provider, cache, or structured-output request could not be completed."""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    @classmethod
    def zero(cls) -> TokenUsage:
        return cls()


class LLMClient:
    """Complete messages as a Pydantic model through Gemini, Ollama, or fake LLMs."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_dir: Path | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        self.settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS)
        self._owns_http = http_client is None
        self._cache_dir = cache_dir or Path(__file__).resolve().parents[3] / "evaluation" / "cache"
        self._sleep = sleep or asyncio.sleep
        self._random = random_fn

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def complete_structured(
        self,
        model_tier: ModelTier,
        messages: Sequence[Message],
        schema: type[SchemaT],
        *,
        node: str | None = None,
    ) -> tuple[SchemaT, TokenUsage]:
        """Return a schema-validated response; one repair request follows invalid output."""
        del node  # Nodes are only meaningful to FakeLLM.
        model = self._model_for(model_tier)
        cache_key = self.cache_key(model, messages, schema)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return self._parse_cached(cached, schema)
        if self.settings.LLM_CACHE_MODE == "replay":
            raise LLMProviderError("LLM replay cache entry is missing.")

        request_messages = list(messages)
        for structured_attempt in range(2):
            raw, usage = await self._request(model, request_messages, schema)
            try:
                parsed = schema.model_validate_json(raw)
            except ValidationError as exc:
                if structured_attempt:
                    raise LLMProviderError(
                        "Provider did not return valid structured output."
                    ) from exc
                request_messages.append(
                    {
                        "role": "user",
                        "content": "Return only valid JSON matching the requested schema.",
                    }
                )
                continue
            if self.settings.LLM_CACHE_MODE == "record":
                self._write_cache(cache_key, parsed, usage)
            return parsed, usage
        raise AssertionError("unreachable")

    def cache_key(self, model: str, messages: Sequence[Message], schema: type[BaseModel]) -> str:
        payload = {
            "provider": self.settings.LLM_PROVIDER,
            "model": model,
            "messages": list(messages),
            "schema": schema.model_json_schema(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _model_for(self, tier: ModelTier) -> str:
        return self.settings.FAST_MODEL if tier == "fast" else self.settings.STRONG_MODEL

    async def _request(
        self, model: str, messages: Sequence[Message], schema: type[BaseModel]
    ) -> tuple[str, TokenUsage]:
        for attempt in range(self.settings.LLM_MAX_RETRIES + 1):
            try:
                if self.settings.LLM_PROVIDER == "gemini":
                    return await self._gemini(model, messages, schema)
                if self.settings.LLM_PROVIDER == "ollama":
                    return await self._ollama(model, messages, schema)
                raise LLMProviderError("The fake provider must use FakeLLM.")
            except (httpx.TransportError, LLMProviderError) as exc:
                if attempt >= self.settings.LLM_MAX_RETRIES or not self._is_retryable(exc):
                    raise
                await self._sleep((0.5 * (2**attempt)) + (self._random() * 0.1))
        raise AssertionError("unreachable")

    async def _gemini(
        self, model: str, messages: Sequence[Message], schema: type[BaseModel]
    ) -> tuple[str, TokenUsage]:
        api_key = self._api_key()
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
            if message["role"] != "system"
        ]
        system = next(
            (message["content"] for message in messages if message["role"] == "system"), None
        )
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema.model_json_schema(),
            },
        }
        if system is not None:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        response = await self._http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json=payload,
        )
        self._raise_for_status(response)
        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Gemini returned no response content.") from exc
        metadata = data.get("usageMetadata", {})
        return str(text), self._usage(
            metadata.get("promptTokenCount", 0),
            metadata.get("candidatesTokenCount", 0),
            metadata.get("totalTokenCount", 0),
            model,
        )

    async def _ollama(
        self, model: str, messages: Sequence[Message], schema: type[BaseModel]
    ) -> tuple[str, TokenUsage]:
        response = await self._http.post(
            f"{self.settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": list(messages),
                "format": schema.model_json_schema(),
                "stream": False,
            },
        )
        self._raise_for_status(response)
        data = response.json()
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMProviderError("Ollama returned no response content.") from exc
        prompt = int(data.get("prompt_eval_count", 0) or 0)
        completion = int(data.get("eval_count", 0) or 0)
        return str(text), self._usage(prompt, completion, prompt + completion, model)

    def _api_key(self) -> str:
        if self.settings.LLM_API_KEY is None or not self.settings.LLM_API_KEY.get_secret_value():
            raise LLMProviderError("LLM_API_KEY is required when LLM_PROVIDER=gemini.")
        return self.settings.LLM_API_KEY.get_secret_value()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise LLMProviderError(f"LLM provider HTTP {response.status_code}")

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, httpx.TransportError) or any(
            code in str(error)
            for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")
        )

    def _usage(self, prompt: int, completion: int, total: int, model: str) -> TokenUsage:
        # Free-tier Gemini defaults cost $0; paid pricing can be supplied when configured later.
        prices_per_million: dict[str, tuple[float, float]] = {}
        input_price, output_price = prices_per_million.get(model, (0.0, 0.0))
        cost = (prompt * input_price + completion * output_price) / 1_000_000
        return TokenUsage(prompt, completion, total, cost)

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        if self.settings.LLM_CACHE_MODE == "off":
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMProviderError("LLM cache entry could not be read.") from exc

    def _write_cache(self, key: str, parsed: BaseModel, usage: TokenUsage) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{key}.json"
        cache_entry = {"response": parsed.model_dump(mode="json"), "usage": asdict(usage)}
        path.write_text(json.dumps(cache_entry, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _parse_cached(cached: dict[str, Any], schema: type[SchemaT]) -> tuple[SchemaT, TokenUsage]:
        try:
            return schema.model_validate(cached["response"]), TokenUsage(**cached["usage"])
        except (KeyError, TypeError, ValidationError) as exc:
            raise LLMProviderError("LLM cache entry has an invalid shape.") from exc


class FakeLLM:
    """Deterministic scripted LLM for agent and end-to-end tests."""

    def __init__(self, scripts: Mapping[str, Sequence[BaseModel | str | Exception]]) -> None:
        self._scripts = {node: list(responses) for node, responses in scripts.items()}

    async def complete_structured(
        self,
        model_tier: ModelTier,
        messages: Sequence[Message],
        schema: type[SchemaT],
        *,
        node: str | None = None,
    ) -> tuple[SchemaT, TokenUsage]:
        del model_tier, messages
        script = self._scripts.get(node or "default", [])
        if not script:
            raise LLMProviderError(f"No FakeLLM response scripted for node {node or 'default'}.")
        response = script.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, BaseModel):
            return schema.model_validate(response.model_dump()), TokenUsage.zero()
        try:
            return schema.model_validate_json(response), TokenUsage.zero()
        except ValidationError as exc:
            raise LLMProviderError("FakeLLM response did not match the requested schema.") from exc
