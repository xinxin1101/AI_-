import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.agent.service import agent_service
from app.observability.context import current_trace_id, session_id_var
from app.observability.tracing import trace_recorder
from app.rag.service import LOW_CONFIDENCE_ANSWER
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.backend import backend_service
from app.services.llm import LLMProviderError


router = APIRouter(tags=["chat"])


def _trace_id() -> str:
    return current_trace_id()


def _sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = await backend_service.get_or_create(request.session_id)
    session_id_var.set(session.session_id)
    history = await backend_service.history(session.session_id)
    trace_id = _trace_id()
    trace = trace_recorder.start(trace_id, session.session_id, request.message)
    prepared = None
    agent_service.llm.reset_usage()
    try:
        prepared = await agent_service.prepare(history, request.message)
        if prepared.can_generate:
            answer = await agent_service.llm.complete(
                history,
                request.message,
                context=prepared.context,
            )
        else:
            answer = prepared.fallback_answer or LOW_CONFIDENCE_ANSWER
        usage = agent_service.llm.consume_usage()
    except LLMProviderError as exc:
        usage = agent_service.llm.consume_usage()
        await trace_recorder.finish(
            trace,
            prepared=prepared,
            status="error",
            usage=usage,
            error="llm_provider_error",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider is temporarily unavailable",
        ) from exc

    await backend_service.append_message(
        session.session_id,
        "user",
        request.message,
        trace_id=trace_id,
    )
    await backend_service.append_message(
        session.session_id,
        "assistant",
        answer,
        trace_id=trace_id,
    )
    await trace_recorder.finish(
        trace,
        prepared=prepared,
        status="success",
        usage=usage,
    )

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
        standalone_query=prepared.standalone_query,
        context_resolved=prepared.context_resolved,
        context_resolution_reason=prepared.context_resolution_reason,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session = await backend_service.get_or_create(request.session_id)
    session_id_var.set(session.session_id)
    history = await backend_service.history(session.session_id)
    trace_id = _trace_id()
    trace = trace_recorder.start(trace_id, session.session_id, request.message)
    agent_service.llm.reset_usage()
    prepared = await agent_service.prepare(history, request.message)

    async def event_generator() -> AsyncIterator[str]:
        session_id_var.set(session.session_id)
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
                "standalone_query": prepared.standalone_query,
                "context_resolved": prepared.context_resolved,
                "context_resolution_reason": prepared.context_resolution_reason,
            },
        )

        try:
            async for chunk in agent_service.stream(prepared, history, request.message):
                chunks.append(chunk)
                yield _sse("token", {"delta": chunk})
        except LLMProviderError:
            await trace_recorder.finish(
                trace,
                prepared=prepared,
                status="error",
                usage=agent_service.llm.consume_usage(),
                error="llm_provider_error",
            )
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
        await backend_service.append_message(
            session.session_id,
            "user",
            request.message,
            trace_id=trace_id,
        )
        await backend_service.append_message(
            session.session_id,
            "assistant",
            answer,
            trace_id=trace_id,
        )
        await trace_recorder.finish(
            trace,
            prepared=prepared,
            status="success",
            usage=agent_service.llm.consume_usage(),
        )
        yield _sse(
            "done",
            {
                "trace_id": trace_id,
                "session_id": session.session_id,
                "grounded": prepared.grounded,
                "intent": prepared.intent.value,
                "context_resolved": prepared.context_resolved,
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
