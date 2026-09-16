import json
from pathlib import Path

from app.rag.models import KnowledgeDocument


def load_documents(path_value: str) -> list[KnowledgeDocument]:
    root = Path(path_value)
    if not root.exists():
        return []

    files = [root] if root.is_file() else sorted(root.glob("**/*.jsonl"))
    documents: list[KnowledgeDocument] = []
    seen_ids: set[str] = set()

    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    document = KnowledgeDocument.model_validate(payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"Invalid knowledge record: {path}:{line_number}") from exc
                if document.document_id in seen_ids:
                    raise ValueError(f"Duplicate document_id: {document.document_id}")
                seen_ids.add(document.document_id)
                documents.append(document)

    return documents
