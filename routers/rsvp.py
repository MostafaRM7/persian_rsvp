"""RSVP token planning router.

Provides chunked token plans with opaque pacing weights for the dumb client player.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from auth import get_current_user_optional
from config import TRUST_PROXY_HEADERS
from limiter import TIER_RATE_LIMITS, quota_manager, rate_limiter
from models import SavedText, User
from rsvp_engine import RSVPEngine, RSVPChunkResponse
from rsvp_engine.pacing import PacingProfile

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
    http_request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    # 1. Resolve client identifier and plan tier for rate limiting & quotas.
    # X-Forwarded-For is only honored when TRUST_PROXY_HEADERS is enabled (§12):
    # otherwise any anonymous client could spoof it to mint fresh identifiers
    # and bypass quotas and rate limits.
    client_ip = "127.0.0.1"
    if http_request.client:
        client_ip = http_request.client.host
    if TRUST_PROXY_HEADERS and "x-forwarded-for" in http_request.headers:
        client_ip = http_request.headers["x-forwarded-for"].split(",")[0].strip()

    if current_user:
        client_id = f"user:{current_user.id}"
        tier = getattr(current_user, "plan_tier", "free") or "free"
    else:
        client_id = f"ip:{client_ip}"
        tier = "anonymous"

    # 2. Enforce sliding-window rate limiting per client.
    # Pre-consume a window slot so 429s cannot be retried for free (§12);
    # advertise the reset point via Retry-After (RFC 6585 §3).
    max_requests, window_seconds = TIER_RATE_LIMITS.get(tier, TIER_RATE_LIMITS["free"])
    reset_seconds = rate_limiter.check(key=client_id, tier=tier)
    response.headers["Retry-After"] = str(max(1, int(round(window_seconds - reset_seconds))))

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

    # Effective WPM resolution priority:
    # 1. request.wpm (if explicitly given)
    # 2. saved.wpm (if saved text specified and has wpm)
    # 3. current_user.preferred_wpm (if authenticated)
    # 4. default 300
    effective_wpm = (
        request.wpm
        or (saved.wpm if saved and saved.wpm else None)
        or (current_user.preferred_wpm if current_user and current_user.preferred_wpm else None)
        or 300
    )

    profile = None
    if current_user and getattr(current_user, "personalization_enabled", True):
        profile = PacingProfile(
            pause_intensity=getattr(current_user, "pause_intensity", 1.0),
            difficulty_tolerance=getattr(current_user, "difficulty_tolerance", 0.0),
            personalization_enabled=True,
        )

    chunk = RSVPEngine.get_chunk(
        text=target_text,
        chunk_index=request.chunk_index,
        chunk_size=request.chunk_size,
        wpm=effective_wpm,
        profile=profile,
    )

    # 3. Enforce tier quota and record usage accounting per §12
    tokens_in_chunk = len(chunk.tokens)
    if tokens_in_chunk > 0:
        await quota_manager.check_and_consume(
            user=current_user,
            identifier=client_id,
            tokens_count=tokens_in_chunk,
        )

    return chunk

