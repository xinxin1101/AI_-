from __future__ import annotations

from starlette.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.security.rate_limit import SecurityService, security_service


class SecurityMiddleware:
    def __init__(
        self,
        app,
        *,
        settings: Settings | None = None,
        service: SecurityService | None = None,
    ) -> None:
        self.app = app
        self.settings = settings or get_settings()
        self.service = service or security_service

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.settings.security_bypass_path_list:
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        api_key = headers.get("x-api-key")
        if not self.service.auth.verify(api_key):
            response = JSONResponse(
                {"detail": "Invalid or missing API key"},
                status_code=401,
                headers={"WWW-Authenticate": "ApiKey"},
            )
            await response(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else None
        identity = self.service.auth.identity(api_key, client_host)
        decision = await self.service.rate_limit(identity)
        if decision is not None and not decision.allowed:
            response = JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={
                    "Retry-After": str(decision.reset_after_seconds),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message):
            if decision is not None and message.get("type") == "http.response.start":
                headers_out = list(message.get("headers", []))
                headers_out.extend(
                    [
                        (b"x-ratelimit-limit", str(decision.limit).encode("ascii")),
                        (b"x-ratelimit-remaining", str(decision.remaining).encode("ascii")),
                    ]
                )
                message["headers"] = headers_out
            await send(message)

        await self.app(scope, receive, send_wrapper)
