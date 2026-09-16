def reciprocal_rank(retrieved_ids: list[str], expected_ids: set[str]) -> float:
    for rank, document_id in enumerate(retrieved_ids, start=1):
        if document_id in expected_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int) -> float:
    if not expected_ids:
        return 0.0
    return 1.0 if any(document_id in expected_ids for document_id in retrieved_ids[:k]) else 0.0


def keyword_coverage(text: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    return sum(1 for term in expected_terms if term in text) / len(expected_terms)
