import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.agent.service import agent_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import LLMProviderError
from app.services.session_store import session_store


router = APIRouter(tags=["chat"])


def _trace_id() -> str:
    return f"tr_{uuid4().hex}"


def _sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = await session_store.get_or_create(request.session_id)
    history = await session_store.history(session.session_id)
    trace_id = _trace_id()
    try:
        prepared, answer = await agent_service.complete(history, request.message)
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider is temporarily unavailable",
        ) from exc

    await session_store.append_message(session.session_id, "user", request.message)
    await session_store.append_message(session.session_id, "assistant", answer)

    return ChatResponse(
        trace_id=trace_id,
        session_id=session.session_id,
        answer=answer,
        grounded=prepared.grounded,
        confidence=round(prepared.confidence, 4),
        citations=prepared.citations,
        intent=prepared.intent.value,
        gate_reason=prepared.gate_reason,
        tool_calls=prepared.tool_calls,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session = await session_store.get_or_create(request.session_id)
    history = await session_store.history(session.session_id)
    trace_id = _trace_id()
    prepared = await agent_service.prepare(history, request.message)

    async def event_generator() -> AsyncIterator[str]:
        chunks: list[str] = []
        yield _sse(
            "meta",
            {
                "trace_id": trace_id,
                "session_id": session.session_id,
                "grounded": prepared.grounded,
                "confidence": round(prepared.confidence, 4),
                "citations": [item.model_dump() for item in prepared.citations],
                "intent": prepared.intent.value,
                "gate_reason": prepared.gate_reason,
                "tool_calls": [item.model_dump() for item in prepared.tool_calls],
            },
        )

        try:
            async for chunk in agent_service.stream(prepared, history, request.message):
                chunks.append(chunk)
                yield _sse("token", {"delta": chunk})
        except LLMProviderError:
            yield _sse(
                "error",
                {
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "message": "AI provider is temporarily unavailable",
                },
            )
            return

        answer = "".join(chunks)
        await session_store.append_message(session.session_id, "user", request.message)
        await session_store.append_message(session.session_id, "assistant", answer)
        yield _sse(
            "done",
            {
                "trace_id": trace_id,
                "session_id": session.session_id,
                "grounded": prepared.grounded,
                "intent": prepared.intent.value,
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
