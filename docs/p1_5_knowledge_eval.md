# P1.5 — Knowledge Pipeline + RAG Eval

P1.5 separates **where knowledge came from** from **how RAG retrieves it**.

## Source tiers

`data/sources/guilin_official_sources.json` is the source registry. Each entry records publisher, canonical URL, authority level, freshness class and refresh cadence. The initial registry prioritizes government pages and official scenic-area/operator websites.

## Verified seed corpus

`data/knowledge/verified/official_guilin_seed.jsonl` contains manually normalized, provenance-preserving facts verified against the registry on 2026-09-16. It is a rebuild corpus, not the historical production corpus.

Static facts can remain indexable until re-verification. Volatile facts such as opening hours can carry `expires_at`; expired records are dropped before indexing. Time-sensitive queries additionally require a fresh dynamic/volatile/realtime hit, otherwise the RAG service returns the safe fallback.

## Live refresh

`python -m scripts.build_knowledge --live` fetches enabled registry URLs, extracts visible HTML text, stores raw normalized snapshots in `data/snapshots/`, and writes refreshed JSONL. Live refresh is intentionally not part of CI because external sites should not make tests flaky.

## Evaluation

`eval/rag_eval.jsonl` contains positive retrieval cases, out-of-domain negatives and freshness-sensitive negatives. `python -m scripts.eval_rag` reports:

- Recall@5
- MRR
- grounding/fallback accuracy
- citation hit rate
- evidence keyword coverage

CI enforces minimum floors so retrieval changes cannot silently degrade the accepted baseline.

## Qwen model adapter

The LLM layer remains OpenAI-compatible and model-agnostic. `LLM_MODEL` is never hardcoded in business logic. For providers/models that require streaming, set `LLM_FORCE_STREAM=true`; `/chat` will aggregate streamed provider chunks while `/chat/stream` forwards them incrementally. `LLM_MODALITIES` and `LLM_EXTRA_BODY_JSON` carry provider-specific options without coupling the API layer to one model name.
