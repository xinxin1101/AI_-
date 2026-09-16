# Resume Quantification — Truthful Project Claims

## Recommended project title

**桂林文旅 AI 助手——智能客服模块｜校企合作项目 / 个人重构版**

Recommended one-line positioning:

> 基于 FastAPI + LangGraph + RAG + Qwen 构建文旅智能客服后端，完成混合检索、实时 Tool、Redis/PostgreSQL 持久化、Trace 可观测与多轮上下文解析，并通过真实 Provider 场景验收。

## Recommended resume bullets

### Version A — AI Application / Agent Development

- 基于 **FastAPI + LangGraph + Qwen(OpenAI-compatible)** 重构桂林文旅智能客服后端，设计 `RAG → Intent Router → Guarded Tool → Evidence Merge → LLM` 链路，支持知识问答、实时天气、路线/景区信息与行程规划，并对低置信度及 Provider 异常执行 fail-closed。
- 构建 **Dense + BM25 + RRF + Rerank + Confidence/Freshness Gate** 的可追溯 RAG，统一 RAG/Tool Citation；针对 RC2 暴露的 OOD 假 Grounding、Prompt Injection 检索污染及实时 Tool 失败后静态证据越权问题增加边界保护。
- 实现 **Redis 短期会话 + PostgreSQL Durable Trace + Qdrant** 的生产化后端，Trace 持久化 Tool/Citation/Token/Latency 等证据；补充 Alembic、结构化日志、PII 脱敏、Retention、API Key、Redis Rate Limit 与 OTel/Prometheus/Grafana/Tempo 配置。
- 在真实 Qwen、Redis、PostgreSQL、Qdrant、Open-Meteo 链路上完成 **30 turns / 24 conversations** RC2 验收，维护集达到 **30/30 PASS**，Citation/Grounding/Intent/Tool/Multi-turn/Trace 等冻结 Gate 均通过；最终 Head 测得 **TTFT P50/P95 945.8/1470.1 ms、E2E P50/P95 1528.3/3369.3 ms**。

### Version B — Backend / AI Full Stack

- 设计并实现 FastAPI AI 服务，提供 Session、Chat、SSE Streaming、Feedback、Health/Ready、Trace Lookup 与 Prometheus Metrics API；使用 Redis 保存有界短期会话，PostgreSQL 持久化 conversation/message/feedback/trace/tool/citation。
- 通过 Alembic 管理数据库 schema，加入 API Key 鉴权、Redis 分布式固定窗口限流、日志/持久化 PII 脱敏与数据保留策略；接入 OpenTelemetry FastAPI/HTTPX instrumentation，并提供 Prometheus + Grafana + Tempo + Collector 本地观测拓扑。
- 将知识 RAG、多轮上下文解析和实时 Provider Tool 统一进 LangGraph 执行链，在真实 Qwen/Redis/PostgreSQL/Qdrant/Open-Meteo 环境建立 30 场景验收 Gate，最终 30/30 通过，并记录 TTFT、P50/P95、Token、Tool Retry 与 Trace Evidence。

## Short 3-bullet version

- 基于 FastAPI + LangGraph + Qwen 重构文旅智能客服 Agent，构建 Hybrid RAG、Intent Router、实时 Tool、Citation 与多轮 Context Resolver，支持知识问答/天气/路线/行程规划及低置信度 fail-closed。
- 搭建 Redis + PostgreSQL + Qdrant 生产化数据链路，并实现 Alembic、Trace/Token/Tool 可观测、API Key、Redis Rate Limit、PII 脱敏、Retention 与 OTel/Prometheus/Grafana/Tempo 配置。
- 设计 30 turns / 24 conversations 的真实场景 RC2 验收集，在 Qwen + Redis + PostgreSQL + Qdrant + Open-Meteo 链路上实现 30/30 PASS；冻结基线 TTFT P50/P95 945.8/1470.1 ms，E2E P50/P95 1528.3/3369.3 ms。

## Metrics that are safe to quote

The following can be used if their scope is stated:

```text
RC2 maintained acceptance set: 30 turns / 24 conversations
Scenario acceptance: 30/30 PASS
Citation compliance: 100%
Grounding accuracy: 100%
Fallback accuracy: 100%
Intent accuracy: 100%
Tool selection accuracy: 100%
Tool outcome accuracy: 100%
Multi-turn context resolution: 100%
Trace persistence: 100%
Successful-tool retry rate: 0%
TTFT P50/P95: 945.780 / 1470.068 ms
E2E P50/P95: 1528.341 / 3369.343 ms
Provider-reported tokens: 16,209 total, 736.77 / known LLM turn
```

Recommended wording:

> 在维护的 30-turn / 24-conversation RC2 场景集上……

Not recommended:

> 模型线上准确率 100%。

## Claims to avoid

Do **not** write:

- “线上准确率 100%”
- “生产 QPS 169” — the old 169 req/s load smoke used Mock LLM/Tool and memory backends
- “已部署高可用生产集群”
- “已完成 AMap 真实联调”
- “使用生产级语义 Embedding/Reranker 完成 RC2”
- “实现完整 DLP/合规体系”
- “使用公司原始生产代码/生产知识库”
- “完成模型微调”
- “支持真实支付/订票闭环”

## Interview-safe explanation for 100% RC2 metrics

If asked why many RC2 metrics are 100%:

> 这里不是说模型真实线上准确率是 100%。RC2 是我维护的一组 30 个用户 turn、24 个 conversation 的 release-candidate 验收集，覆盖知识问答、多轮、天气、OOD、Prompt Injection 和 Provider failure。它的作用类似回归门禁，所以冻结时要求 Intent、Tool、Fallback、Trace 等契约必须全部通过。RC2 前几轮其实失败过，并暴露了长对话 subject 漂移、Hash Embedding 假 Grounding 和 Tool 失败后 LLM 编造实时路线等问题。我是修完这些问题后才达到最终 30/30 PASS，因此这个数字表示“当前维护验收集全绿”，而不是生产流量的统计准确率。

## Project ownership wording

Recommended:

> 校企合作项目中的文旅智能客服业务场景，当前仓库为个人独立重构版，重点重新实现 AI 后端、RAG、Agent 编排和生产工程链路。

Avoid:

> 这是原公司的完整生产系统。

The repository and its checked-in verified corpus are rebuild/validation assets, not the historical production source or production database.