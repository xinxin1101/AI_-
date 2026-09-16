# Guilin Tourism AI Assistant — Final Acceptance Report

## 1. Final decision

**Acceptance result: PASS**

The project reached Feature Freeze at RC2. The frozen product baseline is:

```text
Branch: rc/rc2-scenario-acceptance
SHA:    9d865f3948e61857b11b2a98e791a05706c94295
PR:     #10 RC2: scenario acceptance and feature freeze
```

Final-head validation:

```text
Workflow: RC2 Scenario Acceptance
Run:      35118233319
Result:   completed / success
```

This report is a post-freeze evidence document. It does not reopen feature development.

## 2. System scope accepted

The accepted system is an independently rebuilt Guilin tourism AI customer-service backend with:

- FastAPI `/chat` and `/chat/stream` service interfaces
- RAG retrieval with BM25 + Dense abstraction + RRF + reranking + confidence/freshness gating
- structured citations and grounded-context generation
- LangGraph orchestration for knowledge, weather, scenic realtime information, route and itinerary intents
- guarded Tool parameters and fail-closed Tool behavior
- deterministic multi-turn context resolution before RAG / Intent / Tool parsing
- Redis short-term session state
- PostgreSQL durable messages, feedback, trace, Tool and Citation persistence
- Qdrant vector backend
- provider retry/circuit-breaker metadata
- structured JSON logs, application trace correlation and OpenTelemetry integration
- API key authentication and Redis rate limiting capabilities
- privacy masking and retention cleanup
- Alembic migration lifecycle
- Prometheus-compatible metrics and local Grafana/Tempo/Collector deployment configuration
- scenario acceptance and regression workflows

## 3. RC2 real scenario acceptance

Final-head RC2 Artifact (`35118233319`) measured:

| Metric | Result |
| --- | ---: |
| Scenarios | 30 |
| Conversations | 24 |
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
| LLM TTFT P50 | 945.780 ms |
| LLM TTFT P95 | 1470.068 ms |
| End-to-end latency P50 | 1528.341 ms |
| End-to-end latency P95 | 3369.343 ms |
| Provider-reported token turns | 22 |
| Provider-reported total tokens | 16,209 |
| Tokens / known LLM turn | 736.77 |

Scenario categories:

- knowledge: 8
- weather: 4
- multi-turn: 3
- long conversation: 5
- out-of-scope: 3
- Prompt Injection: 3
- provider failure: 2
- itinerary: 2

Every category reached 100% answer and contract pass on the final maintained acceptance set.

## 4. Acceptance gates

The Feature Freeze gate remained fixed during RC2:

- scenario count >= 30
- conversation count >= 20
- answer correctness >= 90%
- citation compliance >= 85%
- grounding accuracy >= 97%
- fallback accuracy = 100%
- intent accuracy = 100%
- Tool selection accuracy = 100%
- Tool outcome accuracy = 100%
- context-resolution accuracy = 100%
- Prompt-Injection maintained-case pass = 100%
- trace persistence = 100%
- successful-tool retry rate <= 10%

Failed RC2 runs were used to repair defects. Thresholds were not lowered to obtain PASS.

## 5. Real integration evidence

The final RC workflow exercised:

- real configured Qwen/OpenAI-compatible model endpoint
- Secret-backed LLM credential
- real SSE streaming path
- real Redis 7.4 service
- real PostgreSQL 17 service
- Alembic schema migration
- real Qdrant 1.19.1 service
- real Open-Meteo calls on weather cache miss
- actual Uvicorn/FastAPI process
- PostgreSQL trace read-back for scenario correlation

Previous staged acceptance also verified:

- Alembic `upgrade -> downgrade -> upgrade`
- migrated PostgreSQL + Redis round trips
- Qdrant real integration
- provider retry/circuit-breaker contracts
- API auth/rate-limit behavior
- privacy redaction and retention deletion
- deterministic concurrent HTTP load smoke

## 6. Defects discovered by acceptance

RC2 found and fixed issues that were not visible in the smaller RC1 smoke set:

1. long-conversation subject drift from the primary attraction to a contextual city mention;
2. realtime Tool failure leaving static RAG evidence eligible for realtime generation;
3. Prompt-Injection suffix text contaminating retrieval;
4. deterministic Hash Embedding collision causing out-of-domain false grounding;
5. occasional missing citation marker for one-citation answers;
6. fuzzy weather geocoding resolving Guilin-domain locations incorrectly;
7. repeated public-weather-provider calls increasing failure exposure;
8. superseded CI runs continuing expensive provider-backed acceptance.

These were corrected through bounded runtime safeguards and regression tests rather than threshold relaxation.

## 7. What is deliberately not claimed

This acceptance does **not** prove:

- 100% real-user production accuracy;
- production-grade semantic embedding quality — RC2 uses Hash Embedding in the maintained workflow;
- production-grade reranker quality — RC2 uses the local reranker;
- live AMap integration — no AMap API key is supplied in RC2;
- an SLA based on GitHub-hosted runner latency;
- security certification from three maintained Prompt-Injection cases;
- full DLP/compliance coverage from rule-based PII masking;
- Kubernetes/HA production deployment;
- that the repository is the original school-enterprise production source code or production knowledge database.

## 8. Feature Freeze policy

After RC2 PASS, normal changes are limited to:

- acceptance-blocking bug fixes;
- security/reliability fixes;
- docs/demo/evidence packaging;
- resume-safe metric extraction;
- architecture/interview material.

P4/P5-style feature expansion is explicitly outside the frozen baseline.

## 9. Final project status

```text
P0     FastAPI AI customer-service MVP                 PASS
P1     Hybrid RAG + citation                           PASS
P1.5   Verified knowledge + RAG evaluation             PASS
P2     LangGraph + guarded Tools                       PASS
P2.5   Provider reliability + routing evaluation       PASS
P3     Redis/PostgreSQL + trace/metrics                 PASS
P3.5   Migration/security/privacy/observability        PASS
P3.6   Multi-turn context resolution                   PASS
RC1    Real Qwen end-to-end validation                 PASS
RC2    30-turn / 24-conversation scenario acceptance   PASS

FEATURE FREEZE                                        ACTIVE
```

The next outputs are demonstration, resume, architecture and interview packaging rather than feature development.