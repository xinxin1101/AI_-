import asyncio

from app.core.config import Settings, get_settings
from app.rag.chunking import chunk_documents
from app.rag.embeddings import create_embedding_provider
from app.rag.loader import load_documents
from app.rag.models import Citation, RAGResult, RetrievalHit
from app.rag.retrieval import HybridRetriever
from app.rag.vector_store import create_vector_store


LOW_CONFIDENCE_ANSWER = (
    "当前知识库没有检索到足够可靠的资料来回答这个问题。"
    "如果问题涉及开放时间、票价、天气、交通班次等会变化的信息，请以对应官方渠道的最新公告为准。"
)


class RAGService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.embedding_provider = create_embedding_provider(self.settings)
        self.vector_store = create_vector_store(self.settings)
        self.retriever = HybridRetriever(
            self.settings, self.embedding_provider, self.vector_store
        )
        self._initialized = False
        self._lock = asyncio.Lock()
        self.document_count = 0
        self.chunk_count = 0

    async def _ensure_initialized(self) -> None:
        if self._initialized or not self.settings.rag_enabled:
            return
        async with self._lock:
            if self._initialized:
                return
            await self.reindex()

    async def reindex(self) -> tuple[int, int]:
        documents = load_documents(self.settings.rag_knowledge_path)
        chunks = chunk_documents(
            documents,
            max_chars=self.settings.rag_chunk_size_chars,
            overlap_chars=self.settings.rag_chunk_overlap_chars,
        )
        await self.retriever.index(chunks)
        self.document_count = len(documents)
        self.chunk_count = len(chunks)
        self._initialized = True
        return self.document_count, self.chunk_count

    def _citation(self, hit: RetrievalHit, index: int) -> Citation:
        snippet = hit.chunk.text.strip().replace("\n", " ")
        if len(snippet) > self.settings.rag_citation_snippet_chars:
            snippet = snippet[: self.settings.rag_citation_snippet_chars].rstrip() + "…"
        return Citation(
            citation_id=f"C{index}",
            document_id=hit.chunk.document_id,
            chunk_id=hit.chunk.chunk_id,
            title=hit.chunk.title,
            source=hit.chunk.source,
            source_url=hit.chunk.source_url,
            updated_at=hit.chunk.updated_at,
            snippet=snippet,
        )

    async def retrieve(self, query: str) -> RAGResult:
        if not self.settings.rag_enabled:
            return RAGResult(grounded=False, confidence=0.0)
        await self._ensure_initialized()
        hits = await self.retriever.retrieve(query)
        if not hits:
            return RAGResult(grounded=False, confidence=0.0)

        confidence = max(0.0, min(1.0, hits[0].rerank_score))
        if confidence < self.settings.rag_confidence_threshold:
            return RAGResult(
                grounded=False,
                confidence=confidence,
                hits=hits,
            )

        citations = [self._citation(hit, index) for index, hit in enumerate(hits, start=1)]
        context_blocks: list[str] = []
        current_chars = 0
        selected_hits: list[RetrievalHit] = []
        selected_citations: list[Citation] = []
        for citation, hit in zip(citations, hits, strict=True):
            block = (
                f"[{citation.citation_id}] 标题：{citation.title}\n"
                f"来源：{citation.source}\n"
                f"内容：{hit.chunk.text}\n"
            )
            if context_blocks and current_chars + len(block) > self.settings.rag_max_context_chars:
                break
            context_blocks.append(block)
            current_chars += len(block)
            selected_hits.append(hit)
            selected_citations.append(citation)

        return RAGResult(
            grounded=True,
            confidence=confidence,
            context="\n".join(context_blocks),
            citations=selected_citations,
            hits=selected_hits,
        )


rag_service = RAGService()
