import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings, get_settings


SYSTEM_PROMPT = """你是桂林文旅 AI 智能客服。
你的职责是帮助游客理解桂林旅游相关问题，并保持回答简洁、友好、可执行。
当前系统仍处于 P0 阶段，尚未接入官方文旅知识库和实时工具。对于开放时间、票价、天气、交通班次等可能变化的信息，不要假装拥有实时数据；应明确提醒用户后续以官方最新信息为准。
不要声称已经完成订票、支付、酒店预订或其他系统并未提供的动作。
"""


class LLMProviderError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _messages(self, history: list[dict[str, str]], message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": message},
        ]

    def _payload(self, history: list[dict[str, str]], message: str, *, stream: bool) -> dict:
        return {
            "model": self.settings.llm_model,
            "messages": self._messages(history, message),
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
            "stream": stream,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def _endpoint(self) -> str:
        return f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"

    def _mock_answer(self, message: str) -> str:
        return (
            "这是 P0 联调模式的模拟回复。已收到你的问题："
            f"“{message}”。当前接口、会话和流式链路已经可用；"
            "P1 接入桂林文旅知识库后，我会基于可追溯资料回答具体景点与行程问题。"
        )

    async def complete(self, history: list[dict[str, str]], message: str) -> str:
        if self.settings.llm_mock_mode:
            await asyncio.sleep(0)
            return self._mock_answer(message)

        if not self.settings.llm_api_key:
            raise LLMProviderError("LLM_API_KEY is required when LLM_MOCK_MODE=false")

        timeout = httpx.Timeout(self.settings.llm_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._endpoint(),
                    headers=self._headers(),
                    json=self._payload(history, message, stream=False),
                )
                response.raise_for_status()
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise LLMProviderError("LLM provider returned an empty answer")
                return answer
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("LLM provider request failed") from exc

    async def stream(self, history: list[dict[str, str]], message: str) -> AsyncIterator[str]:
        if self.settings.llm_mock_mode:
            answer = self._mock_answer(message)
            for index in range(0, len(answer), 6):
                await asyncio.sleep(0)
                yield answer[index : index + 6]
            return

        if not self.settings.llm_api_key:
            raise LLMProviderError("LLM_API_KEY is required when LLM_MOCK_MODE=false")

        timeout = httpx.Timeout(self.settings.llm_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    self._endpoint(),
                    headers=self._headers(),
                    json=self._payload(history, message, stream=True),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                            delta = event["choices"][0].get("delta", {}).get("content")
                        except (json.JSONDecodeError, KeyError, TypeError):
                            continue
                        if isinstance(delta, str) and delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise LLMProviderError("LLM provider stream failed") from exc


llm_client = LLMClient()
