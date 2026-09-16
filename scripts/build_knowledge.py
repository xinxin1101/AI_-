import argparse
import asyncio

from app.core.config import Settings
from app.knowledge.pipeline import refresh_registry
from app.knowledge.registry import load_source_registry
from app.rag.loader import load_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or validate the Guilin tourism knowledge corpus")
    parser.add_argument("--live", action="store_true", help="Fetch enabled registry URLs and rebuild JSONL")
    parser.add_argument("--strict", action="store_true", help="Fail the live refresh on the first source error")
    args = parser.parse_args()
    settings = Settings()

    sources = load_source_registry(settings.knowledge_source_registry)
    documents = load_documents(settings.rag_knowledge_path, drop_expired=True)
    if not args.live:
        print(f"registry_sources={len(sources)} active_documents={len(documents)}")
        if not sources or not documents:
            raise SystemExit(1)
        return

    output = f"{settings.rag_knowledge_path.rstrip('/')}/refreshed_sources.jsonl"
    report = asyncio.run(
        refresh_registry(
            settings.knowledge_source_registry,
            output,
            settings.knowledge_snapshot_dir,
            timeout_seconds=settings.knowledge_http_timeout_seconds,
            strict=args.strict,
        )
    )
    print(report.model_dump_json(indent=2))
    if args.strict and report.failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
