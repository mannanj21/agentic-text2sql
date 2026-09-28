import os

import pytest
from pydantic import BaseModel

from app.config import get_settings
from app.llm.client import LLMClient


class SmokeReply(BaseModel):
    message: str


@pytest.mark.llm
@pytest.mark.asyncio
async def test_gemini_structured_output_smoke() -> None:
    """Run manually with LLM_PROVIDER=gemini and a local LLM_API_KEY."""
    if not os.environ.get("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY is required for the live Gemini smoke test")
    client = LLMClient(get_settings())
    try:
        reply, _ = await client.complete_structured(
            "fast", [{"role": "user", "content": "Reply with the word hello."}], SmokeReply
        )
    finally:
        await client.aclose()
    assert reply.message
