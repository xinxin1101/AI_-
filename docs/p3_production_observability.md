# P3 Production Backend & Observability

## 目标

P3 不继续堆 Agent 功能，而是把 P0-P2.5 的 AI 链路接入可恢复、可追溯、可观测的生产后端。

## 存储分层

```text
Redis
  - session metadata
  - recent message window
  - sliding TTL

PostgreSQL
  - conversations
  - messages
  - feedback
  - traces
  - tool_calls
  - citations
```

Redis 是短期上下文缓存，不承担审计；PostgreSQL 是长期事实记录。

## Trace Contract

每次 `/chat` 或 `/chat/stream` 都生成 `trace_id`，并记录：

- session_id / request message
- status / intent / grounded / confidence / gate_reason
- start/end/latency
- LLM model
- provider-reported prompt/completion/total token usage（若可用）
- fallback flag
- Tool Call: provider/status/attempts/latency/circuit_state
- Citation: RAG 或 Tool 来源、document/chunk、source URL、snippet

错误的 LLM 请求也写 Trace，status=`error`，不会只记录成功请求。

## Metrics

内存中维护有界 rolling window，不无限增长。当前导出：

- request latency P50 / P95
- known token total
- Tool success rate
- retry rate
- circuit-open rate
- fallback rate
- intent distribution

`/metrics` 提供 Prometheus text exposition；`/api/v1/observability/metrics/summary` 提供 JSON 摘要。

这里的窗口指标用于实时运行观察，不替代 PostgreSQL Trace 的长期分析。

## Health

- `/health`: liveness，只证明 API 进程存活。
- `/ready`: readiness；生产配置下检查 Redis 与 PostgreSQL。

应用启动时如果开启 PostgreSQL persistence，会创建连接池并按配置初始化 schema；关闭时释放 Redis/PostgreSQL 连接。

## Token Usage 边界

不使用 `字符数 / 4` 等估算值冒充真实 Token。非流式 OpenAI-compatible 响应如果包含 `usage` 会记录；流式 Provider 只有显式开启 `LLM_CAPTURE_STREAM_USAGE=true` 且 Provider 支持 usage event 时才记录。

## P3 Acceptance

CI 使用三类独立环境：

1. deterministic acceptance：memory session + persistence off，确保 P0-P2.5 行为不回归；
2. backend integration：真实 Redis + PostgreSQL，验证 Session、Message、Feedback、Trace、Tool Call 的 round-trip；
3. Qdrant integration：保留真实向量库回归；
4. Open-Meteo live smoke：验证公网 Provider，但外部网络故障不阻断核心 acceptance。

## 后续

P3 Core 完成后再考虑 P3.5/P4：

- Alembic/显式 migration 管理，而非 auto-create schema
- 日志 JSON 化与 request correlation middleware
- OpenTelemetry / Prometheus-Grafana
- trace sampling / retention policy / PII redaction
- Redis cache for retrieval/provider results
- rate limit / auth / API gateway
- Kubernetes/Nginx deployment and load test
