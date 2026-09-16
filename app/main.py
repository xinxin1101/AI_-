from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, feedback, health, observability, session
from app.core.config import get_settings
from app.services.backend import backend_service


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await backend_service.startup()
    try:
        yield
    finally:
        await backend_service.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="Production-oriented Guilin tourism AI customer-service backend rebuild.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(observability.prometheus_router)
app.include_router(session.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(observability.router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": "0.3.0",
        "docs": "/docs",
    }
