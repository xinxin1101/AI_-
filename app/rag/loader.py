import json
from datetime import date
from pathlib import Path

from app.rag.models import KnowledgeDocument


def _is_expired(expires_at: str | None, *, today: date | None = None) -> bool:
    if not expires_at:
        return False
    try:
        expiry = date.fromisoformat(expires_at[:10])
    except ValueError:
        return False
    return expiry < (today or date.today())


def load_documents(
    path_value: str,
    *,
    drop_expired: bool = True,
    today: date | None = None,
) -> list[KnowledgeDocument]:
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
                    document = KnowledgeDocument.model_validate(json.loads(line))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"Invalid knowledge record: {path}:{line_number}") from exc
                if document.document_id in seen_ids:
                    raise ValueError(f"Duplicate document_id: {document.document_id}")
                seen_ids.add(document.document_id)
                if drop_expired and _is_expired(document.expires_at, today=today):
                    continue
                documents.append(document)

    return documents
