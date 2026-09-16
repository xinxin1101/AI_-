# RC2 Feature Freeze Acceptance

## Status

**RC2 acceptance: PASS**

RC2 is the final release-candidate validation stage for the Guilin tourism AI customer-service rebuild. The scope of this stage is scenario-based acceptance and reliability hardening only; it does not introduce a new product/Agent feature layer.

Validated code head before this acceptance record:

```text
308cc92ac226c0b91f2a866df2d5c06db10cfce5
```

GitHub Actions validation:

```text
Workflow: RC2 Scenario Acceptance
Run:      35117213413
Result:   completed / success
```

Both jobs passed on the same head:

- `regression`: success
- `real-scenario-acceptance`: success
- `Run 30-scenario real acceptance gate`: success

## Scenario set

The RC2 maintained scenario set contains **30 user turns across 24 conversations** and covers:

- normal grounded tourism knowledge questions
- multi-turn follow-up and omitted-subject resolution
- long-conversation reference resolution
- real weather Tool calls
- knowledge-insufficient / out-of-scope questions
- Prompt Injection attempts
- provider-unavailable fail-closed behavior
- itinerary requests

Category distribution from the accepted run:

| Category | Cases | Answer correctness | Contract pass |
| --- | ---: | ---: | ---: |
| itinerary | 2 | 100.00% | 100.00% |
| knowledge | 8 | 100.00% | 100.00% |
| long_conversation | 5 | 100.00% | 100.00% |
| multiturn | 3 | 100.00% | 100.00% |
| out_of_scope | 3 | 100.00% | 100.00% |
| prompt_injection | 3 | 100.00% | 100.00% |
| provider_failure | 2 | 100.00% | 100.00% |
| weather | 4 | 100.00% | 100.00% |

## Frozen acceptance metrics

All configured Feature Freeze gates passed without lowering the thresholds.

| Metric | RC2 accepted result |
| --- | ---: |
| Scenario success | 30 / 30 |
| Answer correctness | 100.00% |
| Citation compliance | 100.00% |
| RAG grounding accuracy | 100.00% |
| Fallback accuracy | 100.00% |
| Intent accuracy | 100.00% |
| Tool selection accuracy | 100.00% |
| Tool outcome accuracy | 100.00% |
| Multi-turn context resolution | 100.00% |
| Prompt-Injection safety pass | 100.00% |
| Trace persistence | 100.00% |
| Successful-tool retry rate | 0.00% |

The gate thresholds remained:

- scenarios >= 30
- conversations >= 20
- answer correctness >= 90%
- citation compliance >= 85%
- grounding accuracy >= 97%
- fallback / intent / tool selection / tool outcome / context resolution / Prompt-Injection / trace persistence = 100%
- successful-tool retry rate <= 10%

## Real-provider latency and token evidence

Measured on the GitHub-hosted runner in accepted run `35117213413`:

| Metric | Result |
| --- | ---: |
| LLM TTFT P50 | 937.544 ms |
| LLM TTFT P95 | 1569.299 ms |
| End-to-end latency P50 | 1429.886 ms |
| End-to-end latency P95 | 3807.735 ms |
| End-to-end max | 3966.975 ms |
| Provider-reported token turns | 22 |
| Provider-reported total tokens | 15,984 |
| Tokens / known LLM turn | 726.55 |

The remaining 8 turns intentionally followed fallback/fail-closed paths and therefore did not require a normal LLM generation path. Token figures are provider-reported values only; no character-count approximation is used.

## Tool / fallback observations

The accepted run recorded 11 raw Tool calls. Raw Tool success rate was **72.73%** because the scenario set intentionally contains provider-failure cases. This is expected and must not be reported as a production provider availability statistic.

For Tool calls expected to succeed, successful-tool retry rate was **0.00%**. The process-local metrics snapshot also recorded:

- fallback rate: `0.2667`
- retry rate: `0.0`
- circuit-open rate: `0.0`
- intent distribution: knowledge 19, realtime_weather 6, itinerary 2, scenic_info 2, route 1

## Defects found and fixed during RC2

RC2 was deliberately used as an acceptance gate rather than a demonstration-only benchmark. Earlier runs failed and exposed defects that were fixed before freeze:

1. Long conversations could drift from the primary subject (`龙脊梯田`) to a later contextual place mention (`桂林`). Context resolution now preserves the intended tourism subject in this pattern.
2. A failed realtime Route/Scenic Tool could leave static RAG evidence marked grounded, allowing the LLM to invent realtime route/opening details. Realtime Tool failure now fails closed instead of using static evidence as a substitute.
3. Prompt-Injection suffixes could contaminate lexical retrieval. Retrieval-query sanitization now removes recognized trailing control instructions while keeping the user's factual query.
4. Deterministic Hash Embedding could collide on out-of-domain entities and incorrectly ground an unrelated question. RC2 adds a lexical metadata anchor before accepting Hash-based grounding.
5. A single-citation grounded answer could occasionally omit the `[C1]` marker. A bounded citation repair is applied only when exactly one citation is available.
6. Open-Meteo fuzzy geocoding was unreliable for some Guilin-domain place names. Canonical coordinates are pinned for known Guilin locations, including Longji Terrace.
7. Repeated weather turns could unnecessarily repeat public-provider forecast requests. A short-lived in-process forecast cache reuses a freshly retrieved forecast for the same coordinates while preserving a real external call for cache misses.
8. Superseded RC2 CI runs could waste provider calls. The workflow uses a concurrency group with `cancel-in-progress` so only the newest branch head should continue acceptance execution.

No acceptance threshold was reduced to obtain the final PASS.

## What was real in RC2

The real scenario job used:

- real configured Qwen/OpenAI-compatible LLM endpoint and repository Secret-backed API key
- real streaming `/chat/stream` path for TTFT measurement
- real Redis session backend
- real PostgreSQL schema migrated through Alembic and real trace persistence
- real Qdrant service
- real Open-Meteo requests on weather cache misses
- the actual FastAPI service started under Uvicorn

## Important boundaries

The following statements remain intentionally out of scope:

- The 100% values are **RC2 results on a maintained 30-turn / 24-conversation acceptance set**, not a claim of 100% production-user accuracy.
- RC2 still uses the deterministic **Hash Embedding** provider and **local reranker** in this acceptance workflow. It does not validate a production semantic embedding/reranking stack.
- GitHub-hosted runner latency is a repeatable release-candidate baseline, not an SLA.
- The two provider-failure scenarios intentionally exercise fail-closed behavior; raw Tool success rate therefore must not be interpreted as provider availability.
- AMap remains unavailable in this RC2 workflow because no `AMAP_API_KEY` is supplied. RC2 validates correct fail-closed behavior for those cases rather than claiming live AMap integration.
- Prompt-Injection coverage is limited to the maintained RC2 attack cases and layered guards; this is not a security certification.
- The short-lived weather cache is process-local and is not a distributed cache-consistency design.
- This repository remains a personal rebuild of the AI customer-service component from the Guilin tourism school-enterprise collaboration scenario, not the original production codebase or production knowledge database.

## Feature Freeze decision

**Feature Freeze is now authorized after the RC2 PASS.**

After this point, normal project work should not add P4/P5-style Agent features. Changes should be limited to:

- acceptance-blocking bug fixes
- security/reliability fixes
- documentation and demo packaging
- reproducible validation evidence
- resume-safe quantified summaries
- architecture/interview material

Any material functional expansion should be treated as a separate post-freeze decision rather than silently extending RC2.

## Post-freeze deliverables

The next project outputs are documentation/evidence work rather than feature development:

1. final acceptance report
2. runnable Demo / evidence capture
3. resume-safe quantified bullets
4. final architecture diagram
5. interview-ready architecture and trade-off explanation

This document is the RC2 baseline used for those outputs.