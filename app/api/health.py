from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.services.backend import backend_service


router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/ready")
async def ready(response: Response) -> dict:
    dependencies = await backend_service.dependency_health()
    ready_ok = bool(dependencies["redis"]) and bool(dependencies["postgres"])
    if not ready_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready_ok else "degraded", "dependencies": dependencies}
