import asyncio

from app.rag.service import rag_service


async def main() -> None:
    documents, chunks = await rag_service.reindex()
    print(f"RAG index ready: documents={documents}, chunks={chunks}")


if __name__ == "__main__":
    asyncio.run(main())
