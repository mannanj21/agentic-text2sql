"""Embedding client for generating vector embeddings via Ollama (BGE-M3)."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.config import Settings


class EmbeddingDimensionMismatchError(ValueError):
    """Raised when the configured dimension doesn't match the DB schema/existing embeddings."""


class EmbedderClient:
    """Client for generating vector embeddings via Ollama."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.model = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM
        self.base_url = settings.OLLAMA_BASE_URL
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._owns_client = client is None

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        # Ollama supports batch embedding via the /api/embed endpoint
        response = await self._client.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": list(texts)},
        )

        response.raise_for_status()
        data = response.json()

        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise RuntimeError(f"Ollama returned no embeddings for {len(texts)} inputs.")

        # Verify dimension
        for i, emb in enumerate(embeddings):
            if len(emb) != self.dim:
                raise EmbeddingDimensionMismatchError(
                    f"Expected dimension {self.dim}, but Ollama returned {len(emb)} for input {i}."
                )

        result: list[list[float]] = embeddings
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class FakeEmbedderClient(EmbedderClient):
    """Fake embedder for deterministic tests without hitting Ollama."""

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = []
        for text in texts:
            # Deterministic vector based on string hash, normalized
            val = float(hash(text) % 1000) / 1000.0
            emb = [val] * self.dim
            embeddings.append(emb)

        return embeddings
