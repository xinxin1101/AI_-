import math
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.core.config import Settings
from app.rag.models import KnowledgeChunk


class VectorStoreError(RuntimeError):
    pass


class VectorStore(Protocol):
    async def replace(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> None: ...

    async def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}

    async def replace(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> None:
        self._vectors = {
            chunk.chunk_id: vector for chunk, vector in zip(chunks, vectors, strict=True)
        }

    async def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]:
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        scored: list[tuple[str, float]] = []
        for chunk_id, vector in self._vectors.items():
            vector_norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            dot = sum(left * right for left, right in zip(query_vector, vector, strict=True))
            score = dot / (query_norm * vector_norm)
            scored.append((chunk_id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


class QdrantVectorStore:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.qdrant_url.rstrip("/")
        self.collection = settings.qdrant_collection
        self.api_key = settings.qdrant_api_key
        self.timeout = settings.qdrant_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    async def _ensure_collection(self, dimension: int) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.url}/collections/{self.collection}", headers=self._headers()
            )
            if response.status_code == 200:
                return
            if response.status_code != 404:
                raise VectorStoreError(f"Qdrant collection check failed: {response.status_code}")
            create = await client.put(
                f"{self.url}/collections/{self.collection}",
                headers=self._headers(),
                json={"vectors": {"size": dimension, "distance": "Cosine"}},
            )
            if create.status_code >= 400:
                raise VectorStoreError(f"Qdrant collection creation failed: {create.status_code}")

    async def replace(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        await self._ensure_collection(len(vectors[0]))
        points = [
            {
                "id": str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                "vector": vector,
                "payload": chunk.model_dump(),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(
                f"{self.url}/collections/{self.collection}/points",
                params={"wait": "true"},
                headers=self._headers(),
                json={"points": points},
            )
            if response.status_code >= 400:
                raise VectorStoreError(f"Qdrant upsert failed: {response.status_code}")

    async def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.url}/collections/{self.collection}/points/query",
                headers=self._headers(),
                json={"query": query_vector, "limit": top_k, "with_payload": True},
            )
            if response.status_code >= 400:
                raise VectorStoreError(f"Qdrant query failed: {response.status_code}")
            payload = response.json()
        points = payload.get("result", {}).get("points", [])
        results: list[tuple[str, float]] = []
        for point in points:
            chunk_id = point.get("payload", {}).get("chunk_id")
            score = point.get("score")
            if isinstance(chunk_id, str) and isinstance(score, (int, float)):
                results.append((chunk_id, float(score)))
        return results


def create_vector_store(settings: Settings) -> VectorStore:
    if settings.rag_vector_backend == "memory":
        return InMemoryVectorStore()
    if settings.rag_vector_backend == "qdrant":
        return QdrantVectorStore(settings)
    raise ValueError(f"Unsupported vector backend: {settings.rag_vector_backend}")
