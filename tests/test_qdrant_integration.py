import asyncio

import httpx

from app.core.config import Settings
from app.rag.chunking import chunk_document
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.models import KnowledgeDocument
from app.rag.vector_store import QdrantVectorStore


async def _wait_for_qdrant(url: str) -> None:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{url}/healthz")
                if response.status_code < 500:
                    return
        except httpx.HTTPError as exc:
            last_error = exc
        await asyncio.sleep(0.5)
    raise AssertionError(f"Qdrant did not become ready: {last_error}")


def test_qdrant_upsert_and_query_round_trip() -> None:
    settings = Settings(
        qdrant_url="http://localhost:6333",
        qdrant_collection="guilin_tourism_ci",
        qdrant_timeout_seconds=10,
        embedding_dimension=128,
    )
    store = QdrantVectorStore(settings)
    embedder = HashEmbeddingProvider(settings.embedding_dimension)
    documents = [
        KnowledgeDocument(
            document_id="elephant-ci",
            title="象鼻山",
            content="象鼻山是桂林市区具有代表性的山水景观。",
            source="ci",
        ),
        KnowledgeDocument(
            document_id="longji-ci",
            title="龙脊梯田",
            content="龙脊梯田位于桂林市龙胜各族自治县。",
            source="ci",
        ),
    ]
    chunks = [chunk_document(document)[0] for document in documents]

    async def scenario():
        await _wait_for_qdrant(settings.qdrant_url)
        vectors = await embedder.embed_documents([chunk.text for chunk in chunks])
        await store.replace(chunks, vectors)
        query_vector = await embedder.embed_query("象鼻山桂林市区")
        return await store.search(query_vector, top_k=2)

    results = asyncio.run(scenario())
    assert results
    assert results[0][0] == chunks[0].chunk_id
    assert results[0][1] > results[1][1]
