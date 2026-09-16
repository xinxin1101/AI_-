import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from app.core.config import Settings
from app.tools.base import ToolExecutionError


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class ProviderHTTPResult:
    payload: dict[str, Any]
    attempts: int
    latency_ms: float
    status_code: int


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_seconds: float,
        clock=time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock() - self._opened_at >= self.recovery_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def before_call(self) -> None:
        if self.state == CircuitState.OPEN:
            raise ToolExecutionError("provider circuit breaker is open")

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        current = self.state
        if current == CircuitState.HALF_OPEN:
            self._failures = self.failure_threshold
            self._opened_at = self._clock()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()


class ResilientHTTPClient:
    _RETRYABLE_STATUS = {408, 425, 429}

    def __init__(
        self,
        settings: Settings,
        provider_name: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.provider_name = provider_name
        self.transport = transport
        self.breaker = CircuitBreaker(
            failure_threshold=settings.tool_circuit_failure_threshold,
            recovery_seconds=settings.tool_circuit_recovery_seconds,
        )

    @property
    def circuit_state(self) -> str:
        return self.breaker.state.value

    def record_success(self) -> None:
        self.breaker.record_success()

    def record_provider_failure(self) -> None:
        self.breaker.record_failure()

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in ResilientHTTPClient._RETRYABLE_STATUS or status_code >= 500

    async def _sleep_before_retry(self, retry_number: int) -> None:
        delay = min(
            self.settings.tool_retry_max_delay_seconds,
            self.settings.tool_retry_base_delay_seconds * (2 ** max(retry_number - 1, 0)),
        )
        if delay > 0:
            await asyncio.sleep(delay)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> ProviderHTTPResult:
        self.breaker.before_call()
        started = time.monotonic()
        attempts_total = self.settings.tool_retry_attempts + 1

        for attempt in range(1, attempts_total + 1):
            try:
                timeout = httpx.Timeout(self.settings.tool_timeout_seconds)
                async with httpx.AsyncClient(
                    timeout=timeout,
                    transport=self.transport,
                    headers={"User-Agent": self.settings.tool_http_user_agent},
                ) as client:
                    response = await client.get(url, params=params)

                if self._is_retryable_status(response.status_code):
                    if attempt < attempts_total:
                        await self._sleep_before_retry(attempt)
                        continue
                    self.breaker.record_failure()
                    raise ToolExecutionError(
                        f"{self.provider_name} transient HTTP {response.status_code}"
                    )

                if response.status_code >= 400:
                    raise ToolExecutionError(
                        f"{self.provider_name} non-retryable HTTP {response.status_code}"
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    self.breaker.record_failure()
                    raise ToolExecutionError(
                        f"{self.provider_name} returned invalid JSON"
                    ) from exc
                if not isinstance(payload, dict):
                    self.breaker.record_failure()
                    raise ToolExecutionError(
                        f"{self.provider_name} returned a non-object JSON payload"
                    )
                return ProviderHTTPResult(
                    payload=payload,
                    attempts=attempt,
                    latency_ms=(time.monotonic() - started) * 1000,
                    status_code=response.status_code,
                )
            except ToolExecutionError:
                raise
            except httpx.TransportError as exc:
                if attempt < attempts_total:
                    await self._sleep_before_retry(attempt)
                    continue
                self.breaker.record_failure()
                raise ToolExecutionError(
                    f"{self.provider_name} transport request failed"
                ) from exc

        self.breaker.record_failure()
        raise ToolExecutionError(f"{self.provider_name} request failed")
