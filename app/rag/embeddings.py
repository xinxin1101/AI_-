import hashlib
import math
from typing import Protocol

import httpx

from app.core.config import Settings
from app.rag.text import tokenize


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    dimension: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic local fallback for tests and offline development.

    This is not a semantic embedding model. Production should configure an
    OpenAI-compatible embedding endpoint such as a hosted BGE embedding service.
    """

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dimension = settings.embedding_dimension

    def _endpoint(self) -> str:
        return f"{self.settings.embedding_base_url.rstrip('/')}/embeddings"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.embedding_api_key}",
            "Content-Type": "application/json",
        }

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.embedding_api_key:
            raise EmbeddingProviderError("EMBEDDING_API_KEY is required")
        try:
            async with httpx.AsyncClient(timeout=self.settings.embedding_timeout_seconds) as client:
                response = await client.post(
                    self._endpoint(),
                    headers=self._headers(),
                    json={"model": self.settings.embedding_model, "input": texts},
                )
                response.raise_for_status()
                payload = response.json()
                ordered = sorted(payload["data"], key=lambda item: item["index"])
                vectors = [item["embedding"] for item in ordered]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Embedding provider request failed") from exc

        if len(vectors) != len(texts):
            raise EmbeddingProviderError("Embedding provider returned an unexpected vector count")
        if vectors and len(vectors[0]) != self.dimension:
            raise EmbeddingProviderError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vectors[0])}"
            )
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "hash":
        return HashEmbeddingProvider(settings.embedding_dimension)
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(settings)
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
