# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构校企合作项目中的 **AI 客服服务模块**。当前 P1 在 P0 的 FastAPI/LLM/Session 基线上加入可追溯 RAG。项目只提供可被微信小程序调用的 AI 后端，不包含小程序 UI、票务、支付和酒店预订系统。

> 说明：这是基于原业务场景重新实现的工程版本，不是原生产源码。`data/knowledge/demo_guilin.jsonl` 仅用于开发和验收，不应被表述为原项目或景区官方生产数据。

## 当前能力

- `POST /api/v1/session` 创建会话
- `POST /api/v1/chat` 普通问答
- `POST /api/v1/chat/stream` SSE 流式问答
- `POST /api/v1/feedback` 用户反馈
- `GET /health` 健康检查
- JSONL 文旅知识文档模型与确定性 Chunking
- Dense + BM25 双路检索
- Reciprocal Rank Fusion（RRF）融合
- Rerank Top-K
- Citation 可追溯证据
- Confidence Gate：证据不足时不让模型自由编造事实
- Hash Embedding + Memory Vector Store：离线/CI 可重复验收
- OpenAI-compatible Embedding + Qdrant：真实部署可切换
- HTTP Reranker 接口：可接 BGE/Cohere 风格 `/rerank` 服务

## P1 架构

```text
微信小程序
   |
   | HTTPS / SSE
   v
FastAPI Chat API
   |
   +--> Session History
   |
   +--> RAG Service
          |
          +--> Knowledge Loader -> Chunker
          |
          +--> Dense Retrieval -> Vector Store (Memory / Qdrant)
          |
          +--> BM25 Retrieval
          |
          +--> RRF Fusion
          |
          +--> Reranker
          |
          +--> Confidence Gate
          |       |
          |       +-- low confidence -> safe fallback
          |
          +--> Context + Citations
                    |
                    v
                   LLM
                    |
                    v
             answer + citations
```

## 快速启动

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
# PowerShell
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger：`http://localhost:8000/docs`

默认配置不依赖任何外部 AI 服务：`LLM_MOCK_MODE=true`、`EMBEDDING_PROVIDER=hash`、`RAG_VECTOR_BACKEND=memory`。这条路径用于本地接口联调和 CI；Hash Embedding 不是语义模型，不应作为最终生产效果方案。

## 使用真实 Embedding + Qdrant

先把 `.env` 调整为：

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
EMBEDDING_API_KEY=your-key
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSION=1024
RAG_VECTOR_BACKEND=qdrant
QDRANT_URL=http://qdrant:6333
```

`EMBEDDING_DIMENSION` 必须和实际模型输出维度一致。Docker Compose 已包含 Qdrant。首次或知识数据变化后执行：

```bash
python -m scripts.reindex_rag
```

## 知识数据格式

每行一个 JSON 文档：

```json
{
  "document_id": "attraction_xxx",
  "title": "景点标题",
  "content": "经过核验的正文",
  "category": "attraction",
  "source": "来源机构或页面名称",
  "source_url": "https://...",
  "updated_at": "2026-09-16",
  "tags": ["桂林", "景点"]
}
```

生产知识库应保存真实来源 URL 和更新时间，并优先使用政府、景区、运营方等一手来源。动态信息不要只靠静态 RAG，应在 P2 通过实时 Tool 查询。

## API 响应变化

P1 在保持 P0 字段兼容的基础上新增：

```json
{
  "trace_id": "tr_xxx",
  "session_id": "sess_xxx",
  "answer": "...",
  "grounded": true,
  "confidence": 0.81,
  "citations": [
    {
      "citation_id": "C1",
      "document_id": "...",
      "chunk_id": "...",
      "title": "...",
      "source": "...",
      "source_url": "...",
      "updated_at": "...",
      "snippet": "..."
    }
  ]
}
```

流式接口会在 `meta` 事件中先返回 `grounded`、`confidence` 和 `citations`，随后发送 `token` 事件。

## Confidence Gate

如果最高 rerank 分数低于 `RAG_CONFIDENCE_THRESHOLD`，系统不会把低质量检索结果交给模型，而是直接返回安全 fallback。这是为了降低文旅客服在票价、开放时间、交通等事实问题上的幻觉风险。

## 测试

```bash
python -m pytest -q
```

P1 Acceptance Tests 覆盖：Chunk 元数据、BM25/Dense 混合检索、RRF 去重融合、Rerank、低置信度 Gate、Citation、普通 Chat 和 SSE 元数据；同时保留全部 P0 API 回归测试。

## Roadmap

- **P0 ✅**：FastAPI + LLM + Chat/Stream + Session + Feedback
- **P1 🚧**：Knowledge + Hybrid RAG + Reranker + Citation + Confidence Gate
- **P2**：LangGraph + Intent Router + Tool Calling + 行程规划
- **P3**：Redis/PostgreSQL + Trace/Eval + Guardrail + 生产化部署
