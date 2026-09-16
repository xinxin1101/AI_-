# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构本人曾参与的校企合作文旅项目中的 **AI 客服服务模块**。代码是基于原业务场景重新实现的工程版本，不是原生产源码；当前只提供可被微信小程序调用的 AI 后端，不包含小程序 UI、票务、支付和酒店预订系统。

## 当前阶段

- **P0 ✅** FastAPI + LLM + Session + `/chat` + `/chat/stream` + Feedback + Docker/CI
- **P1 ✅** Dense + BM25 + RRF + Reranker + Citation + Confidence Gate + Qdrant
- **P1.5 ✅** 一手来源 Registry + Knowledge Pipeline + Freshness Gate + RAG Eval
- **P2 ✅** LangGraph + Intent Router + Tool Calling + 实时天气/景点/路线 + 行程规划
- **P2.5 ✅** Provider Contract + Timeout/Retry/Circuit Breaker + Router/Tool Eval
- **P3 ✅** Redis Session + PostgreSQL Persistence + Trace + Metrics + Readiness
- **P3.5 ✅ Core** Alembic + JSON Log + PII Redaction/Retention + OpenTelemetry + Prometheus/Grafana + API Auth/Rate Limit + Load Smoke

设计文档：`docs/p1_5_knowledge_eval.md`、`docs/p2_agent_tools.md`、`docs/p2_5_provider_reliability.md`、`docs/p3_production_observability.md`、`docs/p3_5_production_hardening.md`。

## 生产请求链路

```text
微信小程序
   -> Request Trace Context / X-Trace-ID
   -> API Key + Rate Limit
   -> FastAPI
   -> Redis short-term session window
   -> LangGraph / RAG / Tool Calling
   -> Provider Reliability Layer
   -> Evidence Merge
   -> configurable Qwen/OpenAI-compatible LLM
   -> response

同时：
request
   -> structured JSON log (trace_id/session_id)
   -> PostgreSQL durable trace
        | conversations
        | messages
        | feedback
        | traces
        | tool_calls
        | citations
   -> Prometheus metrics
   -> OpenTelemetry -> Collector -> Tempo
   -> Grafana
```

Redis 只保存带 TTL 的最近对话窗口；PostgreSQL 保存长期可追溯记录。PostgreSQL 审计字段和结构化日志在 P3.5 会对手机号、邮箱、身份证号以及常见 token/secret 形式进行规则脱敏。Redis 为了维持短期多轮上下文仍保存原始消息，因此需要依赖 TTL、网络隔离和访问控制；当前规则脱敏也不等同于完整 DLP/合规方案。

## 本地启动

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger：`http://localhost:8000/docs`。

默认使用 `SESSION_BACKEND=memory`、`PERSISTENCE_ENABLED=false`、Mock LLM/Tool、Hash Embedding，便于无需外部 Key 地运行确定性测试。

## 数据库 Migration

生产/Compose 不再依赖应用启动时建表：

```bash
alembic upgrade head
alembic current
```

回滚验证：

```bash
alembic downgrade base
alembic upgrade head
```

`docker compose up --build` 会先运行一次 `migrate` 服务，迁移成功后再启动 API。

如果已有 P3 `DATABASE_AUTO_CREATE=true` 创建的旧开发数据库，应先核对表结构后执行 `alembic stamp 0001_initial_schema`，不要在未知 schema 上直接 stamp。全新环境直接 `alembic upgrade head`。

## API Auth / Rate Limit

```env
API_AUTH_ENABLED=true
API_KEYS=replace-with-strong-random-key
RATE_LIMIT_ENABLED=true
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

受保护接口使用：

```http
X-API-Key: replace-with-strong-random-key
```

当前限流为 Redis Fixed Window，实现简单、可跨 API 实例共享，但窗口边界附近可能出现短时突发；更严格的公网网关策略仍建议由 API Gateway/Nginx/WAF 补充。

## Privacy / Retention

```env
PII_REDACTION_ENABLED=true
TRACE_RETENTION_DAYS=30
MESSAGE_RETENTION_DAYS=30
FEEDBACK_RETENTION_DAYS=90
```

手工清理：

```bash
python -m scripts.retention_cleanup
```

也可以设置 `RETENTION_CLEANUP_ON_STARTUP=true`，但多副本部署更推荐由单独 CronJob/定时任务调用清理脚本，避免每个副本同时做 retention。

## Observability

基础接口：

- `GET /health`：进程存活
- `GET /ready`：Redis/PostgreSQL 依赖就绪
- `GET /metrics`：Prometheus exposition
- `GET /api/v1/observability/metrics/summary`：P50/P95、Tool/Fallback/Intent 等窗口指标
- `GET /api/v1/observability/traces/{trace_id}`：PostgreSQL Trace 明细

结构化 JSON Log 会携带应用 `trace_id`/`session_id`；HTTP 响应同时返回 `X-Trace-ID`。启用 OpenTelemetry 后，应用 `trace_id` 会作为 span attribute 写入分布式 Trace，以便和 PostgreSQL/Application Log 做关联；它不是 OpenTelemetry 自身 128-bit Trace ID 的替代品。

完整本地可观测栈：

```bash
docker compose \
  -f docker-compose.yml \
  -f deploy/observability/docker-compose.observability.yml \
  up --build
```

包含 Prometheus、Grafana、OpenTelemetry Collector 和 Tempo。示例 Grafana 管理员密码仅用于本地演示，真实部署必须更换并通过私有网络/Secret 管理保护 `/metrics`、Grafana 和 Collector。

## Provider Reliability / Eval

```bash
python -m scripts.build_knowledge
python -m scripts.eval_rag --fail-on-threshold
python -m scripts.eval_agent --fail-on-threshold
python -m scripts.live_provider_smoke --open-meteo
```

高德真实 smoke 仍需要 `AMAP_API_KEY`。当前 RAG/Router 的 `1.0` 仅代表小型确定性回归集，不是生产准确率声明。

## Load Smoke

```bash
python -m scripts.load_test \
  --self-host \
  --requests 80 \
  --concurrency 10 \
  --max-p95-ms 5000 \
  --max-error-rate 0.01
```

当前 GitHub Runner 的确定性 Mock 基线：80/80 成功，错误率 0，P50 `51.823 ms`、P95 `71.703 ms`、吞吐 `172.653 req/s`。该结果使用 Mock LLM/Tool、Hash Embedding、内存向量库/Session，只用于检测工程回归；不能代表真实千问、Qdrant、Redis/PostgreSQL 与公网 Provider 的端到端生产性能。

## 千问模型

模型名完全环境变量化：

```env
LLM_MOCK_MODE=false
LLM_BASE_URL=https://your-openai-compatible-provider/v1
LLM_API_KEY=your-key
LLM_MODEL=qwen3.5-omni-flash
LLM_FORCE_STREAM=true
LLM_MODALITIES=text
```

以后更换千问型号只改 `LLM_MODEL` 等 Provider 配置，不修改 Agent Graph、RAG 或 API Controller。

## P3.5 CI

当前硬化验收分为独立 Job：

```text
acceptance
migrated-backend-integration
qdrant-regression
deployment-config
load-smoke
open-meteo-live-smoke
```

其中 Alembic 会对真实 PostgreSQL 执行 `upgrade -> downgrade -> upgrade`；迁移后的集成测试验证 PostgreSQL 脱敏/Retention 与 Redis 分布式限流；部署 Job 校验 Compose/Grafana 配置；Load Job 对真实启动的 FastAPI 进程发送并发 HTTP 请求。
