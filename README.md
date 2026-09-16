# 桂林文旅 AI 智能客服（重构版）

本仓库用于重构校企合作项目中的 **AI 客服服务模块**。P0 阶段只实现可被微信小程序调用的 AI 后端 MVP，不包含小程序 UI、票务、支付、酒店预订等业务系统。

> 说明：这是基于原业务场景重新实现的工程版本，不是原生产源码。

## P0 目标

- FastAPI 服务可独立启动
- OpenAI-compatible LLM 统一客户端
- `POST /api/v1/session` 创建会话
- `POST /api/v1/chat` 普通聊天
- `POST /api/v1/chat/stream` SSE 流式聊天
- `POST /api/v1/feedback` 用户反馈
- `GET /health` 健康检查
- 内存 Session，保留有限轮对话上下文
- Docker / Docker Compose 一键启动
- 默认 Mock LLM，可在没有 API Key 的情况下完成接口联调

## 架构

```text
微信小程序 / Web 调试端
          |
          | HTTPS / SSE
          v
+-----------------------------+
|          FastAPI            |
|  CORS / Schema / Router     |
+-------------+---------------+
              |
      +-------+-------+
      |               |
      v               v
 Session Store      LLM Client
  (P0 memory)   (OpenAI-compatible)
      |               |
      +-------+-------+
              |
              v
        JSON / SSE Response
```

P0 详细设计见 [`docs/architecture.md`](docs/architecture.md)。

## 快速启动

### 1. 本地运行

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell 可以使用：

```powershell
Copy-Item .env.example .env
```

默认 `LLM_MOCK_MODE=true`，不配置密钥也可以完成 P0 联调。

API 文档：`http://localhost:8000/docs`

### 2. 接入真实模型

项目使用 OpenAI-compatible `/chat/completions` 协议。修改 `.env`：

```env
LLM_MOCK_MODE=false
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

密钥只放在服务端环境变量中，**不要写入微信小程序代码或提交到 Git**。

### 3. Docker Compose

```bash
docker compose up --build
```

## API 示例

### 创建会话

```http
POST /api/v1/session
Content-Type: application/json

{}
```

响应：

```json
{
  "session_id": "sess_xxx",
  "created_at": "2026-09-16T00:00:00Z"
}
```

### 普通聊天

```http
POST /api/v1/chat
Content-Type: application/json

{
  "session_id": "sess_xxx",
  "message": "桂林两天怎么玩？"
}
```

`session_id` 可省略；省略时服务端自动创建会话并在响应中返回。

### 流式聊天

```http
POST /api/v1/chat/stream
Content-Type: application/json

{
  "session_id": "sess_xxx",
  "message": "介绍一下桂林适合夜游的地方"
}
```

返回 `text/event-stream`，事件类型包括：

- `meta`：`trace_id`、`session_id`
- `token`：模型增量文本
- `done`：完成
- `error`：流式执行异常

### 用户反馈

```http
POST /api/v1/feedback
Content-Type: application/json

{
  "session_id": "sess_xxx",
  "trace_id": "tr_xxx",
  "rating": "up",
  "comment": "回答有帮助"
}
```

## 微信小程序调用

普通问答优先使用 `/chat`：

```javascript
wx.request({
  url: 'https://your-domain.example/api/v1/chat',
  method: 'POST',
  data: {
    session_id: wx.getStorageSync('tourism_session_id') || null,
    message: '桂林两天怎么玩？'
  },
  success(res) {
    wx.setStorageSync('tourism_session_id', res.data.session_id)
    console.log(res.data.answer)
  }
})
```

流式接口采用标准 SSE。微信小程序端可根据运行环境使用 chunked response 能力消费数据；在正式接入前建议先以 `/chat` 完成端到端联调。

## 测试

```bash
pytest -q
```

测试默认走 Mock LLM，不依赖外网或真实模型密钥。

## P0 边界

当前 Session 和 Feedback 都保存在单进程内存中，因此服务重启后会丢失，也不适合多实例部署。这是 P0 的明确边界。后续阶段会迁移到 Redis/PostgreSQL，并加入 RAG、混合检索、Reranker、Citation、Tool Calling、评测和可观测性。

## Roadmap

- **P0**：FastAPI + LLM + Chat/Stream + Session + Feedback
- **P1**：桂林文旅知识库 + Hybrid RAG + Reranker + Citation
- **P2**：LangGraph + Intent Router + Tool Calling + 行程规划
- **P3**：Redis/PostgreSQL + Trace/Eval + Guardrail + 生产化部署
