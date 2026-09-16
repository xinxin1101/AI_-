import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import LLMProviderError, llm_client
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
        answer = await llm_client.complete(history, request.message)
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
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session = await session_store.get_or_create(request.session_id)
    history = await session_store.history(session.session_id)
    trace_id = _trace_id()

    async def event_generator() -> AsyncIterator[str]:
        chunks: list[str] = []
        yield _sse("meta", {"trace_id": trace_id, "session_id": session.session_id})

        try:
            async for chunk in llm_client.stream(history, request.message):
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
        yield _sse("done", {"trace_id": trace_id, "session_id": session.session_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
