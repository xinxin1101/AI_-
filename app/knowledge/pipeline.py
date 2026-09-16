import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.knowledge.models import PipelineReport, SourceSnapshot, SourceSpec
from app.knowledge.registry import load_source_registry
from app.rag.models import KnowledgeDocument


def _same_site(source_url: str, final_url: str) -> bool:
    source_host = (urlparse(source_url).hostname or "").lower().removeprefix("www.")
    final_host = (urlparse(final_url).hostname or "").lower().removeprefix("www.")
    return bool(source_host and final_host and (final_host == source_host or final_host.endswith("." + source_host)))


def extract_html_text(html: str, selector: str | None = None) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    root = soup.select_one(selector) if selector else (soup.find("main") or soup.body or soup)
    if root is None:
        return title, ""
    lines = [line.strip() for line in root.get_text("\n", strip=True).splitlines() if line.strip()]
    return title, "\n".join(lines)


async def fetch_source(spec: SourceSpec, *, timeout_seconds: float = 30.0) -> SourceSnapshot:
    if not spec.url.startswith(("https://", "http://")):
        raise ValueError(f"Unsupported source URL: {spec.url}")
    headers = {"User-Agent": "GuilinTourismAI-KnowledgeBot/1.0 (+research rebuild)"}
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
        response = await client.get(spec.url)
        response.raise_for_status()
    if not _same_site(spec.url, str(response.url)):
        raise ValueError(f"Cross-site redirect rejected for {spec.source_id}: {response.url}")
    title, text = extract_html_text(response.text, spec.content_selector)
    if len(text) < 40:
        raise ValueError(f"Extracted text is too short for {spec.source_id}")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SourceSnapshot(
        source_id=spec.source_id,
        source_url=str(response.url),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        title=title or spec.name,
        text=text,
        content_hash=digest,
        status_code=response.status_code,
    )


def snapshot_to_document(spec: SourceSpec, snapshot: SourceSnapshot) -> KnowledgeDocument:
    if spec.source_id != snapshot.source_id:
        raise ValueError("Source spec and snapshot source_id mismatch")
    return KnowledgeDocument(
        document_id=f"src_{spec.source_id}",
        title=spec.name,
        content=snapshot.text,
        category=spec.category,
        source=spec.name,
        source_url=snapshot.source_url,
        updated_at=snapshot.fetched_at[:10],
        tags=spec.tags,
        source_id=spec.source_id,
        publisher=spec.publisher,
        authority_level=spec.authority_level,
        freshness_class=spec.freshness_class,
        source_verified_at=snapshot.fetched_at,
        content_hash=snapshot.content_hash,
    )


def write_documents(path_value: str, documents: list[KnowledgeDocument]) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document.model_dump(), ensure_ascii=False) + "\n")


def write_snapshot(directory: str, snapshot: SourceSnapshot) -> None:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{snapshot.source_id}.json"
    path.write_text(json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


async def refresh_registry(
    registry_path: str,
    output_path: str,
    snapshot_dir: str,
    *,
    timeout_seconds: float = 30.0,
    strict: bool = False,
) -> PipelineReport:
    specs = [spec for spec in load_source_registry(registry_path) if spec.enabled]
    documents: list[KnowledgeDocument] = []
    failures: dict[str, str] = {}
    fetched = 0
    for spec in specs:
        try:
            snapshot = await fetch_source(spec, timeout_seconds=timeout_seconds)
            write_snapshot(snapshot_dir, snapshot)
            documents.append(snapshot_to_document(spec, snapshot))
            fetched += 1
        except Exception as exc:  # individual source isolation is intentional
            failures[spec.source_id] = str(exc)
            if strict:
                raise
    if documents:
        write_documents(output_path, documents)
    return PipelineReport(
        source_count=len(specs),
        fetched_count=fetched,
        document_count=len(documents),
        failures=failures,
    )
