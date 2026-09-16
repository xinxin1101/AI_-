from fastapi import APIRouter, HTTPException, status

from app.schemas.chat import FeedbackRequest, FeedbackResponse
from app.services.backend import backend_service


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def create_feedback(request: FeedbackRequest) -> FeedbackResponse:
    accepted = await backend_service.add_feedback(
        session_id=request.session_id,
        trace_id=request.trace_id,
        rating=request.rating,
        comment=request.comment,
    )
    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return FeedbackResponse(accepted=True)
