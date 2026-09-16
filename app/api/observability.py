from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.observability.metrics import metrics_registry
from app.services.persistence import postgres_repository


router = APIRouter(prefix="/observability", tags=["observability"])
prometheus_router = APIRouter(tags=["observability"])


@router.get("/metrics/summary")
async def metrics_summary() -> dict:
    return await metrics_registry.summary()


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict:
    settings = get_settings()
    if not settings.persistence_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trace persistence is disabled",
        )
    result = await postgres_repository.get_trace(trace_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return result


@prometheus_router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    return await metrics_registry.prometheus_text()
