from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.rag.models import Citation


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: datetime


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    trace_id: str
    session_id: str
    answer: str
    grounded: bool = False
    confidence: float = 0.0
    citations: list[Citation] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    accepted: bool = True
