import json
from datetime import date

from app.knowledge.models import SourceSnapshot, SourceSpec
from app.knowledge.pipeline import extract_html_text, snapshot_to_document
from app.rag.loader import load_documents


def test_html_extraction_drops_script_and_navigation() -> None:
    html = """<html><head><title>景区</title><script>bad()</script></head><body><nav>菜单</nav><main><h1>象山</h1><p>桃花江与漓江交汇处。</p></main></body></html>"""
    title, text = extract_html_text(html)
    assert title == "景区"
    assert "象山" in text
    assert "桃花江" in text
    assert "bad" not in text
    assert "菜单" not in text


def test_snapshot_to_document_preserves_provenance() -> None:
    spec = SourceSpec(
        source_id="official-x",
        name="官方页面",
        publisher="官方机构",
        url="https://example.com/page",
        authority_level="government",
        freshness_class="static",
        tags=["桂林"],
    )
    snapshot = SourceSnapshot(
        source_id="official-x",
        source_url="https://example.com/page",
        fetched_at="2026-09-16T00:00:00+00:00",
        title="页面标题",
        text="这是经过抽取的公开资料正文。",
        content_hash="abc",
    )
    document = snapshot_to_document(spec, snapshot)
    assert document.source_id == "official-x"
    assert document.publisher == "官方机构"
    assert document.authority_level == "government"
    assert document.content_hash == "abc"


def test_loader_drops_expired_dynamic_records(tmp_path) -> None:
    path = tmp_path / "knowledge.jsonl"
    rows = [
        {"document_id":"fresh","title":"静态资料","content":"长期有效资料","expires_at":None},
        {"document_id":"expired","title":"过期资料","content":"旧开放时间","expires_at":"2025-01-01","freshness_class":"volatile"},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    documents = load_documents(str(path), today=date(2026, 9, 16))
    assert [document.document_id for document in documents] == ["fresh"]
