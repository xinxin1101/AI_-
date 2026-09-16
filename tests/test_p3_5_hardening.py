import asyncio
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.observability.context import RequestContextMiddleware, current_trace_id, trace_id_var
from app.observability.logging import JsonFormatter
from app.security.middleware import SecurityMiddleware
from app.security.privacy import PrivacyRedactor
from app.security.rate_limit import APIKeyAuthenticator, MemoryFixedWindowRateLimiter, SecurityService


def test_privacy_redactor_masks_common_sensitive_values() -> None:
    redactor = PrivacyRedactor(Settings(pii_redaction_enabled=True))
    text = "电话13800138000 邮箱alice@example.com 身份证110101199001011234 api_key=secret123 Bearer abcdefghijkl"
    masked = redactor.text(text)
    assert "138****8000" in masked
    assert "a***@example.com" in masked
    assert "110101********1234" in masked
    assert "api_key=***" in masked
    assert "Bearer ***" in masked
    assert "secret123" not in masked


def test_api_key_authenticator_uses_configured_keys() -> None:
    settings = Settings(api_auth_enabled=True, api_keys="alpha,beta")
    auth = APIKeyAuthenticator(settings)
    assert auth.verify("alpha") is True
    assert auth.verify("beta") is True
    assert auth.verify("wrong") is False
    assert auth.verify(None) is False


def test_memory_rate_limit_rejects_over_limit() -> None:
    settings = Settings(rate_limit_enabled=True, rate_limit_backend="memory", rate_limit_requests=2, rate_limit_window_seconds=60)
    limiter = MemoryFixedWindowRateLimiter(settings)

    async def scenario() -> None:
        assert (await limiter.check("user-a")).allowed is True
        assert (await limiter.check("user-a")).allowed is True
        third = await limiter.check("user-a")
        assert third.allowed is False
        assert third.remaining == 0

    asyncio.run(scenario())


def test_security_middleware_rejects_bad_key() -> None:
    settings = Settings(api_auth_enabled=True, api_keys="test-key", rate_limit_enabled=False)
    service = SecurityService(settings)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware, settings=settings, service=service)

    @app.get("/private")
    async def private() -> dict[str, bool]:
        return {"ok": True}

    asyncio.run(service.startup())
    try:
        client = TestClient(app)
        assert client.get("/private").status_code == 401
        assert client.get("/private", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/private", headers={"X-API-Key": "test-key"}).status_code == 200
    finally:
        asyncio.run(service.shutdown())


def test_security_middleware_returns_429_after_rate_limit() -> None:
    settings = Settings(
        api_auth_enabled=True,
        api_keys="test-key",
        rate_limit_enabled=True,
        rate_limit_backend="memory",
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
    )
    service = SecurityService(settings)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware, settings=settings, service=service)

    @app.get("/private")
    async def private() -> dict[str, bool]:
        return {"ok": True}

    asyncio.run(service.startup())
    try:
        client = TestClient(app)
        first = client.get("/private", headers={"X-API-Key": "test-key"})
        second = client.get("/private", headers={"X-API-Key": "test-key"})
        assert first.status_code == 200
        assert first.headers["x-ratelimit-remaining"] == "0"
        assert second.status_code == 429
        assert second.headers["retry-after"]
    finally:
        asyncio.run(service.shutdown())


def test_request_context_header_matches_application_trace_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/trace")
    async def trace() -> dict[str, str]:
        return {"trace_id": current_trace_id()}

    response = TestClient(app).get("/trace")
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == response.json()["trace_id"]
    assert response.json()["trace_id"].startswith("tr_")


def test_json_logging_contains_trace_and_redacts_message() -> None:
    settings = Settings(log_json=True, pii_redaction_enabled=True)
    formatter = JsonFormatter(settings)
    token = trace_id_var.set("tr_logging_test")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="contact alice@example.com or 13800138000",
            args=(),
            exc_info=None,
        )
        payload = json.loads(formatter.format(record))
    finally:
        trace_id_var.reset(token)
    assert payload["trace_id"] == "tr_logging_test"
    assert "a***@example.com" in payload["message"]
    assert "138****8000" in payload["message"]
