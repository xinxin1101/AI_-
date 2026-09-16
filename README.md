# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构本人曾参与的校企合作文旅项目中的 **AI 客服服务模块**。代码是基于原业务场景重新实现的工程版本，不是原生产源码；当前只提供可被微信小程序调用的 AI 后端，不包含小程序 UI、票务、支付和酒店预订系统。

## 当前阶段

- **P0 ✅** FastAPI + LLM + Session + `/chat` + `/chat/stream` + Feedback + Docker/CI
- **P1 ✅** Dense + BM25 + RRF + Reranker + Citation + Confidence Gate + Qdrant
- **P1.5 ✅** 一手来源 Registry + Knowledge Pipeline + Freshness Gate + RAG Eval
- **P2 ✅** LangGraph + Intent Router + Tool Calling + 实时天气/景点/路线 + 行程规划
- **P2.5 🚧** Live Provider Contract + Timeout/Retry/Circuit Breaker + Router/Tool Eval
- **P3** Redis/PostgreSQL + Trace/Eval 平台化 + Guardrail + 生产部署

设计文档：
- `docs/p1_5_knowledge_eval.md`
- `docs/p2_agent_tools.md`
- `docs/p2_5_provider_reliability.md`

## Agent 请求链路

```text
微信小程序
   -> FastAPI
   -> LangGraph rag_probe
   -> Intent Router
        | knowledge        -> P1.5 RAG
        | realtime_weather -> Weather Tool
        | scenic_info      -> Scenic POI Tool
        | route            -> Route Tool
        | itinerary        -> Itinerary Planner
   -> Tool Parameter Guard
   -> Provider Reliability Layer
        | Timeout
        | bounded Retry
        | Circuit Breaker
        | Response Contract
   -> Evidence Merge (RAG + Tool -> [C#])
   -> configurable Qwen/OpenAI-compatible LLM
   -> answer + citations + intent + tool_calls
```

P1.5 的 `fresh_evidence_required` 会继续进入实时 Tool 路径。例如“明天去漓江会下雨吗？”不会使用静态网页猜天气，而会进入 Weather Tool。

## 快速启动

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger：`http://localhost:8000/docs`

默认 `LLM_MOCK_MODE=true`、`TOOL_MOCK_MODE=true`、Hash Embedding + 内存向量库，不需要 Key 即可跑完整 Agent acceptance。Mock Tool 返回内容明确标记为开发模拟数据，不应作为真实旅游信息使用。

## Live Provider

天气：

```env
TOOL_MOCK_MODE=false
WEATHER_PROVIDER=open_meteo
```

景点 POI 与路线：

```env
TOOL_MOCK_MODE=false
SCENIC_PROVIDER=amap
ROUTE_PROVIDER=amap
AMAP_API_KEY=your-web-service-key
AMAP_REGION=桂林
AMAP_CITYCODE_DEFAULT=0773
```

P2.5 的 Provider 层默认只对网络错误、408/425/429 与 5xx 进行有限重试；高德 `status=0` 业务错误不会盲目重试。连续失败达到阈值后 Circuit Breaker 会 fail-fast，恢复窗口到期后再进行 half-open 探测。

## Eval

```bash
python -m scripts.build_knowledge
python -m scripts.eval_rag --fail-on-threshold
python -m scripts.eval_agent --fail-on-threshold
```

Agent Eval 覆盖：

- Intent Accuracy
- Tool Selection Accuracy
- knowledge / weather / scenic / route / itinerary
- `fresh_evidence_required`
- 多意图优先级

这些指标用于回归，不等同于生产准确率。

## Live Smoke

Open-Meteo：

```bash
python -m scripts.live_provider_smoke --open-meteo
```

高德（需要 Web 服务 Key）：

```bash
AMAP_API_KEY=your-key python -m scripts.live_provider_smoke --amap
```

CI 的确定性 acceptance 不依赖公网。P2.5 另设非阻塞 Open-Meteo live smoke；高德 live smoke 只有仓库配置 `AMAP_API_KEY` secret 时才执行。

## 后续千问模型接入

LLM 仍采用 OpenAI-compatible `/chat/completions`，模型名完全由环境变量控制：

```env
LLM_MOCK_MODE=false
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your-key
LLM_MODEL=qwen3.5-omni-flash
LLM_FORCE_STREAM=true
LLM_MODALITIES=text
LLM_EXTRA_BODY_JSON={"enable_thinking":false}
```

以后更换型号只改 `LLM_MODEL` 等配置，不修改 Agent Graph 或 `/chat` Controller。

## 测试

```bash
python -m pytest -q
```

P2.5 CI 会同时验证 P0-P2 回归、Provider Contract、Intent/Tool Eval、RAG Eval 阈值以及真实 Qdrant round-trip。
