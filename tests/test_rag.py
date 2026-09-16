import asyncio

from app.core.config import Settings
from app.rag.chunking import chunk_document
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.models import KnowledgeDocument
from app.rag.retrieval import HybridRetriever, reciprocal_rank_fusion
from app.rag.vector_store import InMemoryVectorStore


def _settings() -> Settings:
    return Settings(
        rag_enabled=True,
        rag_vector_backend="memory",
        embedding_provider="hash",
        embedding_dimension=128,
        rag_dense_top_k=5,
        rag_bm25_top_k=5,
        rag_fused_top_k=5,
        rag_rerank_top_k=3,
        rag_confidence_threshold=0.35,
    )


def _chunks():
    documents = [
        KnowledgeDocument(
            document_id="elephant",
            title="象鼻山",
            content="象鼻山是桂林市区代表性景观之一，山体临水部分形似大象伸鼻饮水。",
            source="test",
        ),
        KnowledgeDocument(
            document_id="longji",
            title="龙脊梯田",
            content="龙脊梯田位于桂林市龙胜各族自治县，观赏体验具有明显季节性。",
            source="test",
        ),
    ]
    return [chunk for document in documents for chunk in chunk_document(document)]


def test_chunker_keeps_source_metadata() -> None:
    document = KnowledgeDocument(
        document_id="doc-1",
        title="测试景点",
        content="第一段。" * 80,
        category="attraction",
        source="official-test",
        source_url="https://example.invalid/test",
    )
    chunks = chunk_document(document, max_chars=120, overlap_chars=20)
    assert len(chunks) > 1
    assert all(chunk.document_id == "doc-1" for chunk in chunks)
    assert all(chunk.source == "official-test" for chunk in chunks)


def test_rrf_merges_and_deduplicates_rankings() -> None:
    fused = reciprocal_rank_fusion(
        [[("a", 0.9), ("b", 0.8)], [("b", 3.0), ("c", 2.0)]]
    )
    ids = [item[0] for item in fused]
    assert ids.count("b") == 1
    assert ids[0] == "b"


def test_hybrid_retrieval_prefers_elephant_trunk_document() -> None:
    settings = _settings()
    retriever = HybridRetriever(
        settings,
        HashEmbeddingProvider(settings.embedding_dimension),
        InMemoryVectorStore(),
    )

    async def scenario():
        await retriever.index(_chunks())
        return await retriever.retrieve("象鼻山在哪里？")

    hits = asyncio.run(scenario())
    assert hits
    assert hits[0].chunk.document_id == "elephant"
    assert hits[0].rerank_score >= settings.rag_confidence_threshold


def test_unknown_query_stays_below_confidence_gate() -> None:
    settings = _settings()
    retriever = HybridRetriever(
        settings,
        HashEmbeddingProvider(settings.embedding_dimension),
        InMemoryVectorStore(),
    )

    async def scenario():
        await retriever.index(_chunks())
        return await retriever.retrieve("火星基地量子电梯维护周期")

    hits = asyncio.run(scenario())
    assert not hits or hits[0].rerank_score < settings.rag_confidence_threshold
