from __future__ import annotations

import asyncio
import json
from time import perf_counter

from app.core.config import get_settings
from app.services.llm import LLMClient


async def main() -> None:
    settings = get_settings()
    if settings.llm_mock_mode:
        raise SystemExit("RC1 requires LLM_MOCK_MODE=false")
    if not settings.llm_api_key:
        raise SystemExit("RC1 requires LLM_API_KEY")
    if not settings.llm_force_stream:
        raise SystemExit("RC1 expects LLM_FORCE_STREAM=true for the selected Omni model")

    client = LLMClient(settings)
    client.reset_usage()
    started = perf_counter()
    first_token_at: float | None = None
    chunks: list[str] = []

    async for chunk in client.stream(
        [],
        "这是一次接口连通性测试。请只用一句简短中文回复，说明桂林是一座旅游城市。",
    ):
        if first_token_at is None:
            first_token_at = perf_counter()
        chunks.append(chunk)

    completed = perf_counter()
    answer = "".join(chunks).strip()
    usage = client.consume_usage()
    if not answer:
        raise SystemExit("Qwen provider returned an empty answer")

    result = {
        "provider": "openai-compatible-qwen",
        "model": settings.llm_model,
        "stream": True,
        "answer_chars": len(answer),
        "answer_preview": answer[:160],
        "ttft_ms": round(((first_token_at or completed) - started) * 1000, 3),
        "total_latency_ms": round((completed - started) * 1000, 3),
        "usage": usage.model_dump() if usage else None,
        "usage_reported": usage is not None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
