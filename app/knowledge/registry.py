import json
from pathlib import Path

from app.knowledge.models import SourceSpec


def load_source_registry(path_value: str) -> list[SourceSpec]:
    path = Path(path_value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Source registry must be a JSON array")
    sources = [SourceSpec.model_validate(item) for item in payload]
    ids = [source.source_id for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source_id in source registry")
    return sources
