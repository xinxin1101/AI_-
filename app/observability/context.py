from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from time import perf_counter
from uuid import uuid4

from app.security.privacy import privacy_redactor


trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)


def current_trace_id() -> str:
    value = trace_id_var.get()
    return value or f"tr_{uuid4().hex}"


def current_session_id() -> str | None:
    return session_id_var.get()


def bind_session_id(session_id: str) -> Token:
    return session_id_var.set(session_id)


def reset_session_id(token: Token) -> None:
    session_id_var.reset(token)


class RequestContextMiddleware:
    """Pure ASGI middleware so SSE responses are not buffered by BaseHTTPMiddleware."""

    def __init__(self, app) -> None:
        self.app = app
        self.logger = logging.getLogger("app.request")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        trace_id = f"tr_{uuid4().hex}"
        trace_token = trace_id_var.set(trace_id)
        session_token = session_id_var.set(None)
        started = perf_counter()
        status_code = 500
        path = privacy_redactor.text(scope.get("path", "")) or ""
        method = scope.get("method", "")
        self.logger.info("request_started", extra={"event": "request_started", "method": method, "path": path})

        async def send_wrapper(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self.logger.exception("request_failed", extra={"event": "request_failed", "method": method, "path": path})
            raise
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 3)
            self.logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            session_id_var.reset(session_token)
            trace_id_var.reset(trace_token)
