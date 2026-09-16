# P3.5 Production Hardening

P3.5 不新增文旅业务能力，而是把 P3 的 Redis/PostgreSQL/Trace 后端补成更适合真实部署和面试讲解的工程闭环。

## 1. Migration-first database lifecycle

P3 支持过 `DATABASE_AUTO_CREATE`，适合重构早期和 CI；P3.5 正式引入 Alembic：

```text
PostgreSQL healthy
  -> migrate container
  -> alembic upgrade head
  -> migration success
  -> FastAPI start
```

CI 在真实 PostgreSQL 上验证：

```text
upgrade head
-> downgrade base
-> upgrade head
-> migrated integration test
```

生产默认 `DATABASE_AUTO_CREATE=false`。已经由早期 P3 runtime DDL 建好的数据库需要先核验 schema，再决定是否 `alembic stamp 0001_initial_schema`；不能把 stamp 当成迁移本身。

## 2. Request correlation and structured logs

入口使用纯 ASGI `RequestContextMiddleware`，避免 `BaseHTTPMiddleware` 对 SSE/streaming 的潜在干扰。

每个请求建立应用 correlation ID：

```text
tr_<uuid>
  -> X-Trace-ID response header
  -> ContextVar
  -> JSON log
  -> ChatResponse.trace_id
  -> PostgreSQL traces.trace_id
  -> OpenTelemetry span attribute: guilin_ai.app_trace_id
```

JSON Log 同时包含 `trace_id`、`session_id`、method、path、status code、duration 等字段。应用 correlation ID 与 OpenTelemetry 原生 Trace ID 是两套不同标识，通过 span attribute 建立关联。

## 3. Privacy boundary

`PrivacyRedactor` 当前规则覆盖常见：

- 中国大陆手机号
- 邮箱
- 18 位身份证号
- Bearer token
- `api_key/token/secret/password` 等显式键值

脱敏发生在 PostgreSQL persistence boundary 与 JSON logging formatter，而不只是查询展示层。因此 messages、feedback、trace request/error、tool summary、citation snippet/source URL 在写库前会处理。

边界必须明确：Redis 中的短期对话窗口为了继续给 LLM 提供原始多轮上下文，当前仍可能包含用户原始文本，只通过 bounded history + TTL 控制生命周期。这不是完整 DLP，也不是合规认证实现；姓名、地址和自由文本中的所有敏感信息无法靠有限正则完整识别。

## 4. Retention

配置：

```env
TRACE_RETENTION_DAYS=30
MESSAGE_RETENTION_DAYS=30
FEEDBACK_RETENTION_DAYS=90
```

清理顺序：

```text
expired traces
  -> tool_calls/citations ON DELETE CASCADE
expired messages
expired feedback
orphan conversations
```

手工任务：

```bash
python -m scripts.retention_cleanup
```

单机可使用 `RETENTION_CLEANUP_ON_STARTUP=true`。多副本环境应优先使用单独 CronJob/调度任务，避免所有实例同时执行数据库清理。

## 5. API authentication and distributed rate limiting

P3.5 提供可选 `X-API-Key` 验证，比较使用 `hmac.compare_digest`；日志和 rate-limit identity 不保存原始 API Key。

Rate Limit 使用 Redis Fixed Window：

```text
identity = SHA256(API key or client host)
key = <prefix>:rate:<identity>:<window>
INCR + EXPIRE
```

超过阈值返回 `429`、`Retry-After`、`X-RateLimit-*`。该实现支持多 API 实例共享计数，但 fixed-window 边界可能存在瞬时 burst；公网部署仍建议配合 Nginx/API Gateway/WAF、TLS 和网络 ACL。

`/health`、`/ready`、`/metrics`、OpenAPI/docs 默认位于 bypass 列表，便于基础设施探针抓取。公网环境不应直接暴露这些地址，应在网络层限制来源；也可以调整 `SECURITY_BYPASS_PATHS`。

## 6. OpenTelemetry + Prometheus/Grafana

OpenTelemetry 可选启用：

```env
OTEL_ENABLED=true
OTEL_SERVICE_NAME=guilin-tourism-ai
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
```

Instrumented surfaces：

- FastAPI inbound HTTP
- HTTPX outbound HTTP
- application trace attributes: intent/grounded/fallback/tool count/citation count/latency/token usage

本地 observability overlay：

```text
FastAPI --OTLP/HTTP--> OTel Collector --OTLP/gRPC--> Tempo
   |
   +-- /metrics <-- Prometheus <-- Grafana
```

Grafana provisioning 提供 Prometheus/Tempo datasource 与基础 AI Overview Dashboard，展示 Trace window、P95、Fallback、Tool success、Latency 和 Intent distribution。

当前 CI 做 Compose merge/schema/config 校验，并未把完整 Grafana/Tempo UI 当成生产级托管平台验收。真实部署还应增加 Secret Manager、持久化容量、备份、TLS、认证、告警规则和平台级 SLA。

## 7. Load smoke

`scripts/load_test.py` 对真实启动的 FastAPI HTTP 服务发并发请求，并输出：

- request count / success / error rate
- duration
- throughput req/s
- P50 / P95 / max latency

P3.5 CI baseline：

```text
requests       80
concurrency    10
success        80
error_rate     0
throughput     172.653 req/s
P50            51.823 ms
P95            71.703 ms
max            90.772 ms
```

该结果只用于 deterministic regression：Mock LLM/Tool、Hash Embedding、memory vector/session，不应外推为真实 Qwen + Qdrant + Redis/PostgreSQL + live providers 的生产吞吐。

## 8. Acceptance gates

P3.5 CI 当前包含：

1. `acceptance`：P0-P3.5 deterministic tests + RAG Eval + Agent Eval。
2. `migrated-backend-integration`：真实 Redis/PostgreSQL，Alembic reversible migration，写库脱敏，Retention，Redis limit。
3. `qdrant-regression`：真实 Qdrant round-trip。
4. `deployment-config`：Base Compose + observability overlay + Grafana dashboard JSON validation。
5. `load-smoke`：80 请求/10 concurrency HTTP load smoke。
6. `open-meteo-live-smoke`：真实公共天气 Provider smoke；属于外部依赖，不代表高德 live 已完成。

## 9. Interview explanation

建议按这条线描述：

```text
业务问答
-> RAG / Agent / Tool
-> Provider reliability
-> Redis short-term state
-> PostgreSQL durable trace
-> request correlation
-> PII/retention
-> API auth/rate limit
-> metrics + OTel
-> migration + CI + load acceptance
```

P3.5 的价值不是“又用了几个组件”，而是把数据生命周期、安全边界、发布迁移、可观测性和容量回归变成可执行、可测试的工程约束。
