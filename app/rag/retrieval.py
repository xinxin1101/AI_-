import math
from collections import Counter, defaultdict

import httpx

from app.core.config import Settings
from app.rag.embeddings import EmbeddingProvider
from app.rag.models import KnowledgeChunk, RetrievalHit
from app.rag.text import normalize_text, tokenize
from app.rag.vector_store import VectorStore


class BM25Index:
    def __init__(self) -> None:
        self._tokens: dict[str, list[str]] = {}
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0

    def build(self, chunks: list[KnowledgeChunk]) -> None:
        self._tokens = {chunk.chunk_id: tokenize(chunk.text) for chunk in chunks}
        document_count = len(self._tokens)
        self._avgdl = (
            sum(len(tokens) for tokens in self._tokens.values()) / document_count
            if document_count
            else 0.0
        )
        document_frequency: Counter[str] = Counter()
        for tokens in self._tokens.values():
            document_frequency.update(set(tokens))
        self._idf = {
            token: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    def search(self, query: str, top_k: int, *, k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
        query_tokens = tokenize(query)
        scored: list[tuple[str, float]] = []
        for chunk_id, tokens in self._tokens.items():
            if not tokens:
                continue
            frequencies = Counter(tokens)
            length = len(tokens)
            score = 0.0
            for token in query_tokens:
                tf = frequencies[token]
                if tf == 0:
                    continue
                idf = self._idf.get(token, 0.0)
                denominator = tf + k1 * (1 - b + b * length / (self._avgdl or 1.0))
                score += idf * (tf * (k1 + 1)) / denominator
            if score > 0:
                scored.append((chunk_id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


def reciprocal_rank_fusion(
    rankings: list[list[tuple[str, float]]], *, rrf_k: int = 60
) -> list[tuple[str, float]]:
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, (chunk_id, _score) in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


class LocalReranker:
    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        query_tokens = set(tokenize(query))
        max_rrf = max((hit.rrf_score for hit in hits), default=1.0) or 1.0
        normalized_query = normalize_text(query)

        for hit in hits:
            chunk_tokens = set(tokenize(hit.chunk.text))
            overlap = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
            phrase_bonus = 0.15 if len(normalized_query) >= 3 and normalized_query in normalize_text(hit.chunk.text) else 0.0
            evidence = min(1.0, overlap * 1.4 + phrase_bonus)
            dense_strength = max(0.0, min(1.0, (hit.dense_score - 0.15) / 0.85))
            rrf_strength = hit.rrf_score / max_rrf
            hit.rerank_score = min(
                1.0,
                0.65 * evidence + 0.25 * dense_strength + 0.10 * rrf_strength,
            )

        hits.sort(key=lambda item: item.rerank_score, reverse=True)
        return hits[:top_k]


class HTTPReranker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not self.settings.rerank_api_key:
            raise RuntimeError("RERANK_API_KEY is required when RERANK_MODE=http")
        headers = {
            "Authorization": f"Bearer {self.settings.rerank_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.settings.rerank_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.rerank_base_url.rstrip('/')}/rerank",
                headers=headers,
                json={
                    "model": self.settings.rerank_model,
                    "query": query,
                    "documents": [hit.chunk.text for hit in hits],
                    "top_n": min(top_k, len(hits)),
                },
            )
            response.raise_for_status()
            payload = response.json()
        reranked: list[RetrievalHit] = []
        for item in payload.get("results", []):
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if isinstance(index, int) and 0 <= index < len(hits) and isinstance(score, (int, float)):
                hit = hits[index]
                hit.rerank_score = max(0.0, min(1.0, float(score)))
                reranked.append(hit)
        return reranked[:top_k]


class HybridRetriever:
    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.bm25 = BM25Index()
        self.chunks: dict[str, KnowledgeChunk] = {}
        self.local_reranker = LocalReranker()
        self.http_reranker = HTTPReranker(settings)

    async def index(self, chunks: list[KnowledgeChunk]) -> None:
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self.bm25.build(chunks)
        vectors = await self.embedding_provider.embed_documents([chunk.text for chunk in chunks])
        await self.vector_store.replace(chunks, vectors)

    async def retrieve(self, query: str) -> list[RetrievalHit]:
        if not self.chunks:
            return []
        query_vector = await self.embedding_provider.embed_query(query)
        dense = await self.vector_store.search(query_vector, self.settings.rag_dense_top_k)
        lexical = self.bm25.search(query, self.settings.rag_bm25_top_k)
        fused = reciprocal_rank_fusion([dense, lexical])[: self.settings.rag_fused_top_k]

        dense_scores = dict(dense)
        lexical_scores = dict(lexical)
        hits = [
            RetrievalHit(
                chunk=self.chunks[chunk_id],
                dense_score=dense_scores.get(chunk_id, 0.0),
                bm25_score=lexical_scores.get(chunk_id, 0.0),
                rrf_score=rrf_score,
            )
            for chunk_id, rrf_score in fused
            if chunk_id in self.chunks
        ]

        if self.settings.rerank_mode == "http":
            return await self.http_reranker.rerank(query, hits, self.settings.rag_rerank_top_k)
        return self.local_reranker.rerank(query, hits, self.settings.rag_rerank_top_k)
