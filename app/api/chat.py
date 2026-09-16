import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.rag.service import LOW_CONFIDENCE_ANSWER, rag_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import LLMProviderError, llm_client
from app.services.session_store import session_store


router = APIRouter(tags=["chat"])


def _trace_id() -> str:
    return f"tr_{uuid4().hex}"


def _sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


async def _text_chunks(text: str, size: int = 12) -> AsyncIterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = await session_store.get_or_create(request.session_id)
    history = await session_store.history(session.session_id)
    trace_id = _trace_id()
    rag_result = await rag_service.retrieve(request.message)

    if rag_service.settings.rag_enabled and not rag_result.grounded:
        answer = LOW_CONFIDENCE_ANSWER
    else:
        try:
            answer = await llm_client.complete(
                history,
                request.message,
                context=rag_result.context or None,
            )
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
        grounded=rag_result.grounded,
        confidence=round(rag_result.confidence, 4),
        citations=rag_result.citations,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session = await session_store.get_or_create(request.session_id)
    history = await session_store.history(session.session_id)
    trace_id = _trace_id()
    rag_result = await rag_service.retrieve(request.message)

    async def event_generator() -> AsyncIterator[str]:
        chunks: list[str] = []
        yield _sse(
            "meta",
            {
                "trace_id": trace_id,
                "session_id": session.session_id,
                "grounded": rag_result.grounded,
                "confidence": round(rag_result.confidence, 4),
                "citations": [item.model_dump() for item in rag_result.citations],
            },
        )

        try:
            if rag_service.settings.rag_enabled and not rag_result.grounded:
                stream = _text_chunks(LOW_CONFIDENCE_ANSWER)
            else:
                stream = llm_client.stream(
                    history,
                    request.message,
                    context=rag_result.context or None,
                )
            async for chunk in stream:
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
                "grounded": rag_result.grounded,
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
