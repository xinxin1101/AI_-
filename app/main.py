from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, feedback, health, observability, session
from app.core.config import get_settings
from app.observability.context import RequestContextMiddleware
from app.observability.logging import configure_logging
from app.observability.otel import telemetry_runtime
from app.security.middleware import SecurityMiddleware
from app.security.rate_limit import security_service
from app.services.backend import backend_service


settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await security_service.startup()
    try:
        await backend_service.startup()
        try:
            yield
        finally:
            await backend_service.shutdown()
    finally:
        await security_service.shutdown()
        telemetry_runtime.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.3.5",
    description="Production-hardened Guilin tourism AI customer-service backend rebuild.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityMiddleware, settings=settings, service=security_service)
app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(observability.prometheus_router)
app.include_router(session.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(observability.router, prefix=settings.api_prefix)

telemetry_runtime.configure(app)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": "0.3.5",
        "docs": "/docs",
    }
