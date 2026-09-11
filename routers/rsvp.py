"""RSVP token planning router.

Provides chunked token plans with opaque pacing weights for the dumb client player.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth import get_current_user_optional
from models import SavedText, User
from rsvp_engine import RSVPEngine, RSVPChunkResponse

router = APIRouter(prefix="/api/rsvp", tags=["rsvp"])


class RSVPPlanRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=100_000, description="Raw Persian text to process")
    text_id: Optional[int] = Field(default=None, description="Optional ID of saved text")
    chunk_index: int = Field(default=0, ge=0, description="0-indexed chunk number")
    chunk_size: int = Field(default=150, ge=1, le=500, description="Tokens per chunk")
    wpm: Optional[int] = Field(default=None, ge=60, le=1200, description="Optional target WPM for cognitive pacing adaptation")


@router.post("/plan", response_model=RSVPChunkResponse)
async def get_token_plan(
    request: RSVPPlanRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    target_text = request.text
    saved = None

    # If text_id is provided, resolve from database
    if request.text_id is not None:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="برای دسترسی به متن‌های ذخیره‌شده باید وارد حساب خود شوید.",
            )
        saved = await SavedText.get_or_none(id=request.text_id, user=current_user)
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="متن مورد نظر پیدا نشد.",
            )
        target_text = saved.content

    if not target_text or not target_text.strip():
        return RSVPChunkResponse(
            chunk_index=0,
            total_chunks=0,
            total_tokens=0,
            has_more=False,
            tokens=[],
        )

    effective_wpm = request.wpm or (saved.wpm if saved and saved.wpm else 300)

    chunk = RSVPEngine.get_chunk(
        text=target_text,
        chunk_index=request.chunk_index,
        chunk_size=request.chunk_size,
        wpm=effective_wpm,
    )
    return chunk
