from fastapi import APIRouter, status

from app.schemas.chat import SessionCreateResponse
from app.services.backend import backend_service


router = APIRouter(prefix="/session", tags=["session"])


@router.post("", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session() -> SessionCreateResponse:
    session = await backend_service.create_session()
    return SessionCreateResponse(
        session_id=session.session_id,
        created_at=session.created_at,
    )
