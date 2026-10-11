import httpx
import pytest

from app.config import Settings
from app.llm.embedding import EmbedderClient, EmbeddingDimensionMismatchError, FakeEmbedderClient


@pytest.mark.asyncio
async def test_fake_embedder():
    settings = Settings(EMBEDDING_DIM=10)
    embedder = FakeEmbedderClient(settings)

    vecs = await embedder.aembed(["apple", "banana"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 10

    # Deterministic check
    vecs2 = await embedder.aembed(["apple", "banana"])
    assert vecs == vecs2

    await embedder.aclose()


@pytest.mark.asyncio
async def test_embedder_dimension_mismatch(respx_mock):
    settings = Settings(EMBEDDING_DIM=1024, EMBEDDING_MODEL="bge-m3")

    respx_mock.post("http://localhost:11434/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1] * 50]})
    )

    embedder = EmbedderClient(settings)
    with pytest.raises(EmbeddingDimensionMismatchError, match="Expected dimension 1024"):
        await embedder.aembed(["test text"])

    await embedder.aclose()


@pytest.mark.asyncio
async def test_embedder_empty_input():
    settings = Settings(EMBEDDING_DIM=10)
    embedder = EmbedderClient(settings)
    assert await embedder.aembed([]) == []
    await embedder.aclose()
