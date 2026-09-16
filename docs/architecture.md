# P0 Architecture

## 1. Scope

P0 establishes a stable API boundary between the WeChat Mini Program and the AI backend. It deliberately does not implement RAG, ticketing, payment, booking, or production persistence.

## 2. Request flow

```text
Client
  |
  v
FastAPI Router
  |
  +--> validate request (Pydantic)
  |
  +--> resolve/create session
  |
  +--> load bounded conversation history
  |
  +--> LLMClient
  |      +--> mock mode (local acceptance)
  |      `--> OpenAI-compatible provider
  |
  +--> append assistant response
  |
  `--> JSON response or SSE events
```

## 3. Core modules

- `app/api/`: HTTP contract only; no provider-specific logic.
- `app/core/config.py`: environment-driven configuration.
- `app/services/llm.py`: single LLM adapter for normal and streaming completions.
- `app/services/session_store.py`: P0 in-memory conversation and feedback storage.
- `app/schemas/`: request/response contracts shared by API handlers.

## 4. Session semantics

A session contains a bounded list of `user` / `assistant` messages. The server keeps only the latest `SESSION_MAX_MESSAGES` items to prevent unbounded prompt growth.

P0 session data is process-local and ephemeral. This is intentional. Redis persistence and multi-instance consistency belong to a later production phase.

## 5. Streaming protocol

`POST /api/v1/chat/stream` uses Server-Sent Events (`text/event-stream`). Payloads are JSON encoded inside SSE data fields.

Example:

```text
event: meta
data: {"trace_id":"tr_xxx","session_id":"sess_xxx"}

event: token
data: {"delta":"你好"}

event: done
data: {"trace_id":"tr_xxx","session_id":"sess_xxx"}
```

## 6. Security baseline

- Model API keys remain server-side.
- Request fields have explicit length constraints.
- Browser CORS is configurable through environment variables.
- Provider errors are not exposed with secrets.
- No shell/file/database mutation tools exist in P0.

P0 does not claim to solve prompt injection. Tool permission boundaries are introduced when Tool Calling is added in P2.

## 7. P0 acceptance criteria

1. Service starts with no external dependency when `LLM_MOCK_MODE=true`.
2. `/health` returns `200`.
3. A session can be created and reused.
4. `/chat` returns `trace_id`, `session_id`, and an answer.
5. `/chat/stream` emits `meta`, `token`, and `done` events.
6. `/feedback` accepts feedback for an existing session.
7. Unknown feedback sessions return `404`.
8. Docker image starts the same FastAPI application.
