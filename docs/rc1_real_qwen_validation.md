# RC1 Real Qwen End-to-End Validation

RC1 validates the staged backend with a real Qwen provider while keeping AMap optional.

## Validated topology

```text
Qwen3.5-Omni-Flash (DashScope OpenAI-compatible API)
+ Qdrant 1.19.1
+ Redis 7.4
+ PostgreSQL 17 + Alembic
+ LangGraph
+ P3.6 multi-turn Context Resolver
+ Open-Meteo
```

The RC1 workflow reads `LLM_API_KEY` from a GitHub Actions repository secret and reads `LLM_BASE_URL` / `LLM_MODEL` from repository variables. It never prints the secret value.

## Current acceptance

Validated on workflow run `35112488607` before this documentation-only commit:

- provider streaming smoke: success
- model: `qwen3.5-omni-flash`
- provider-reported usage captured: yes
- direct provider smoke TTFT: `1299.844 ms`
- direct provider smoke total latency: `1376.645 ms`
- six real service E2E cases: `6/6` success
- E2E client-side P50: `1855.801 ms`
- E2E client-side P95: `4296.723 ms`
- traces with provider token usage: `5/6`
- total provider-reported tokens for those five traces: `2915`
- grounded cases: `5`
- low-confidence fallback cases: `1`
- tool cases: `2`
- tool success rate: `1.0`
- retry rate: `0.0`
- circuit-open rate: `0.0`
- fallback rate: `0.1667`

The OOD fallback intentionally bypasses Qwen, so its token usage is null rather than estimated.

## Multi-turn proof

The two-turn session keeps the same `session_id`:

```text
User: 介绍一下象鼻山。
User: 那它明天天气怎么样？
```

The second turn resolves to:

```text
象鼻山明天天气怎么样？
```

with `context_resolved=true`, reason `pronoun_reference`, intent `realtime_weather`, a successful weather tool call, and a persisted PostgreSQL trace.

## Bugs found by RC1

RC1 first exposed two issues that deterministic mocks had not revealed:

1. the provider smoke script treated the `LLMUsage` dataclass as a Pydantic model; this was fixed with dataclass serialization;
2. Open-Meteo fuzzy geocoding returned a non-Guilin coordinate for the Chinese name `桂林`, and normal multi-request tool execution was being miscounted as a retry. The Guilin-domain canonical weather coordinate is now pinned and provider `attempts` reports retry depth rather than the count of distinct HTTP operations.

The final weather requests use `25.2742, 110.2964`, and normal weather calls report `attempts=1`.

## Boundaries

- Qwen is real and called over the public DashScope compatible endpoint.
- Qdrant, Redis and PostgreSQL are real containers in CI.
- Open-Meteo is a real public-network provider call.
- Embeddings are still the deterministic hash provider and reranking is still local; RC1 must not be described as validating a production semantic embedding/reranker stack.
- AMap remains optional and is not part of RC1.
- Six scenarios are a release-candidate smoke/evidence set, not a production-quality accuracy benchmark.
- Latency values come from GitHub-hosted CI and are useful as an RC baseline, not an SLA.
