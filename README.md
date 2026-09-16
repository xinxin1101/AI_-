# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构本人曾参与的校企合作文旅项目中的 **AI 客服服务模块**。代码是基于原业务场景重新实现的工程版本，不是原生产源码；当前只提供可被微信小程序调用的 AI 后端，不包含小程序 UI、票务、支付和酒店预订系统。

## 当前阶段

- **P0 ✅** FastAPI + LLM + Session + `/chat` + `/chat/stream` + Feedback + Docker/CI
- **P1 ✅** Dense + BM25 + RRF + Reranker + Citation + Confidence Gate + Qdrant
- **P1.5 🚧** 官方来源 Registry + Knowledge Pipeline + Freshness Gate + RAG Eval
- **P2** LangGraph + Intent Router + Tool Calling + 实时天气/路线/行程规划
- **P3** Redis/PostgreSQL + Trace/Eval 平台化 + Guardrail + 生产部署

P1.5 详细设计见 [`docs/p1_5_knowledge_eval.md`](docs/p1_5_knowledge_eval.md)。

## P1.5 数据链路

```text
Official/Government Source Registry
              |
              v
       Fetch + HTML Extract
              |
              v
       Provenance Snapshot
              |
              v
  Normalized KnowledgeDocument
              |
       Expiry/Freshness Filter
              |
              v
 Dense + BM25 -> RRF -> Rerank
              |
       Confidence/Freshness Gate
              |
              v
        Context + Citation
              |
              v
             LLM
```

`data/knowledge/verified/official_guilin_seed.jsonl` 是按公开一手来源重新整理的 **验证种子语料**，保留来源 URL、发布方、来源级别和核验时间；它不是原项目生产知识库。开放时间、票价、天气、班次等高时效信息不会因为曾经出现在静态网页中就永久进入回答，过期记录会在索引前被剔除，实时类问题还需要新的动态证据。

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

默认使用 Mock LLM、Hash Embedding 和内存向量库，因此不需要密钥即可跑 API、RAG 和 Eval。真实部署时可切 OpenAI-compatible Embedding + Qdrant。

## Knowledge Pipeline

只验证 Registry 和当前 verified corpus：

```bash
python -m scripts.build_knowledge
```

主动抓取 Registry 中启用的一手来源并生成 snapshot/refreshed JSONL：

```bash
python -m scripts.build_knowledge --live
```

外部站点抓取不放进 CI，避免网络波动影响工程验收。

## RAG Eval

```bash
python -m scripts.eval_rag
python -m scripts.eval_rag --fail-on-threshold
```

当前评测覆盖 Recall@5、MRR、Grounding/Fallback Accuracy、Citation Hit Rate、Evidence Coverage，以及 OOD/过期资料/实时问题的拒答行为。

## 后续千问模型接入

LLM 仍采用 OpenAI-compatible `/chat/completions`，模型名完全由环境变量控制。示例：

```env
LLM_MOCK_MODE=false
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your-key
LLM_MODEL=qwen3.5-omni-flash
LLM_FORCE_STREAM=true
LLM_MODALITIES=text
LLM_EXTRA_BODY_JSON={"enable_thinking":false}
```

以后更换模型时只修改 `LLM_MODEL` 等配置，不修改 `/chat` Controller。对于要求 provider streaming 的模型，普通 `/chat` 会在服务端聚合流式结果；`/chat/stream` 仍直接输出 SSE。

## 测试

```bash
python -m pytest -q
```

P1.5 CI 会同时验证：P0/P1 回归、知识来源与过期过滤、RAG Eval 指标下限；P1 的 Qdrant 集成测试仍保留在前一阶段 CI 中。
