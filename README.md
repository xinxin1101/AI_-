# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构本人曾参与的校企合作文旅项目中的 **AI 客服服务模块**。代码是基于原业务场景重新实现的工程版本，不是原生产源码；当前只提供可被微信小程序调用的 AI 后端，不包含小程序 UI、票务、支付和酒店预订系统。

## 当前阶段

- **P0 ✅** FastAPI + LLM + Session + `/chat` + `/chat/stream` + Feedback + Docker/CI
- **P1 ✅** Dense + BM25 + RRF + Reranker + Citation + Confidence Gate + Qdrant
- **P1.5 ✅** 一手来源 Registry + Knowledge Pipeline + Freshness Gate + RAG Eval
- **P2 ✅** LangGraph + Intent Router + Tool Calling + 实时天气/景点/路线 + 行程规划
- **P2.5 ✅** Live Provider Contract + Timeout/Retry/Circuit Breaker + Router/Tool Eval
- **P3 ✅ Core** Redis Session + PostgreSQL Persistence + Trace + Metrics + Readiness

设计文档：`docs/p1_5_knowledge_eval.md`、`docs/p2_agent_tools.md`、`docs/p2_5_provider_reliability.md`、`docs/p3_production_observability.md`。

## 生产请求链路

```text
微信小程序
   -> FastAPI
   -> Redis short-term session window
   -> LangGraph / RAG / Tool Calling
   -> Provider Reliability Layer
   -> Evidence Merge
   -> configurable Qwen/OpenAI-compatible LLM
   -> response

同时：
request
   -> trace_id
   -> PostgreSQL
        | conversations
        | messages
        | feedback
        | traces
        | tool_calls
        | citations
   -> bounded Metrics window
        | latency P50/P95
        | token usage (provider reported only)
        | tool success/retry/circuit-open rate
        | fallback rate
        | intent distribution
```

Redis 只保存带 TTL 的最近对话窗口；PostgreSQL 保存长期可追溯记录。两者职责分离。

## 快速启动

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger：`http://localhost:8000/docs`。

默认仍使用 `SESSION_BACKEND=memory`、`PERSISTENCE_ENABLED=false`、Mock LLM/Tool、Hash Embedding，因此不启动外部依赖也能跑确定性 acceptance。

生产后端配置示例：

```env
SESSION_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
SESSION_TTL_SECONDS=86400

PERSISTENCE_ENABLED=true
DATABASE_URL=postgresql://guilin:guilin@localhost:5432/guilin_ai
```

也可以直接：

```bash
docker compose up --build
```

Compose 包含 FastAPI、Qdrant、Redis、PostgreSQL。

## Observability

- `GET /health`：进程存活
- `GET /ready`：Redis/PostgreSQL 依赖就绪状态
- `GET /metrics`：Prometheus text exposition
- `GET /api/v1/observability/metrics/summary`：最近窗口的 P50/P95、Tool/Fallback/Intent 指标
- `GET /api/v1/observability/traces/{trace_id}`：PostgreSQL Trace 明细（需开启持久化）

LLM Token 只记录 Provider 实际返回的 `usage`。流式模型若支持 usage event，可设置 `LLM_CAPTURE_STREAM_USAGE=true`；不支持时保持未知，不使用字符数伪造 Token。

## Provider Reliability / Eval

```bash
python -m scripts.build_knowledge
python -m scripts.eval_rag --fail-on-threshold
python -m scripts.eval_agent --fail-on-threshold
python -m scripts.live_provider_smoke --open-meteo
```

高德真实 smoke 需要 `AMAP_API_KEY`。P2.5 的 Provider 层只对网络错误、408/425/429 与 5xx 做有限重试；业务/鉴权错误 fail-fast，并支持 Circuit Breaker。

当前 RAG/Router 的 1.0 指标仅代表小型确定性回归集，不是生产准确率声明。

## 千问模型

模型名完全环境变量化，例如：

```env
LLM_MOCK_MODE=false
LLM_BASE_URL=https://your-openai-compatible-provider/v1
LLM_API_KEY=your-key
LLM_MODEL=qwen3.5-omni-flash
LLM_FORCE_STREAM=true
LLM_MODALITIES=text
```

以后更换千问型号只改 `LLM_MODEL` 等 Provider 配置，不修改 Agent Graph、RAG 或 API Controller。

## 测试

```bash
python -m pytest -q
```

P3 CI 分别验证：P0-P3 deterministic regression、真实 Redis+PostgreSQL round-trip、真实 Qdrant regression，以及非阻塞 Open-Meteo 公网 smoke。
