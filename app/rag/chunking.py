import hashlib

from app.rag.models import KnowledgeChunk, KnowledgeDocument


_BOUNDARIES = ("\n", "。", "！", "？", ".", "!", "?")


def _best_end(text: str, start: int, candidate_end: int, min_ratio: float = 0.6) -> int:
    if candidate_end >= len(text):
        return len(text)
    lower = start + int((candidate_end - start) * min_ratio)
    best = -1
    for boundary in _BOUNDARIES:
        position = text.rfind(boundary, lower, candidate_end)
        best = max(best, position)
    return best + 1 if best >= lower else candidate_end


def chunk_document(
    document: KnowledgeDocument,
    *,
    max_chars: int = 700,
    overlap_chars: int = 100,
) -> list[KnowledgeChunk]:
    if max_chars < 100:
        raise ValueError("max_chars must be >= 100")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be >= 0 and < max_chars")

    text = "\n".join(line.strip() for line in document.content.splitlines() if line.strip())
    if not text:
        return []

    chunks: list[KnowledgeChunk] = []
    start = 0
    index = 0
    while start < len(text):
        candidate_end = min(len(text), start + max_chars)
        end = _best_end(text, start, candidate_end)
        chunk_text = text[start:end].strip()
        if chunk_text:
            digest = hashlib.sha1(
                f"{document.document_id}:{index}:{chunk_text}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"chk_{digest}",
                    document_id=document.document_id,
                    title=document.title,
                    text=chunk_text,
                    category=document.category,
                    source=document.source,
                    source_url=document.source_url,
                    updated_at=document.updated_at,
                    tags=document.tags,
                )
            )
            index += 1
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap_chars)
        start = next_start

    return chunks


def chunk_documents(
    documents: list[KnowledgeDocument],
    *,
    max_chars: int = 700,
    overlap_chars: int = 100,
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for document in documents:
        chunks.extend(
            chunk_document(
                document,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
        )
    return chunks
