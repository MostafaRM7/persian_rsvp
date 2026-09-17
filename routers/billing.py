"""Billing, subscriptions, and usage accounting per §12.

The client is never the authority for subscription status, quota, feature
entitlement, or API limits: tier changes are validated server-side against
SUBSCRIPTION_TIERS, and usage is computed from persisted UsageRecord rows.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

try:  # Starlette renamed 422; keep compatibility across versions
    from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT as HTTP_422
except ImportError:  # pragma: no cover
    from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY as HTTP_422

from auth import get_current_user
from limiter import TIER_QUOTAS, get_now
from models import UsageRecord, User
from schemas import UserOut

router = APIRouter(prefix="/api/account", tags=["billing"])


# Server-side catalog of purchasable subscription tiers (§12: subscription checks).
# Deliberately excludes "anonymous" — that tier only exists for unauthenticated IPs.
SUBSCRIPTION_TIERS = {"free", "paid"}


class SubscriptionUpdate(BaseModel):
    plan_tier: str = Field(..., description="Target subscription tier (free or paid)")


class UsageOut(BaseModel):
    plan_tier: str
    tokens_used: int
    quota_limit: int
    window_seconds: int = 86_400


def _resolve_tier(tier: Optional[str]) -> str:
    resolved = tier or "free"
    return resolved if resolved in TIER_QUOTAS else "free"


@router.patch("/subscription", response_model=UserOut)
async def update_subscription(
    subscription: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
):
    """Server-authoritative subscription change.

    Rejects unknown tiers with 422; only the persisted plan_tier column ever
    decides quota enforcement.
    """
    if subscription.plan_tier not in SUBSCRIPTION_TIERS:
        raise HTTPException(
            status_code=HTTP_422,
            detail="سطح اشتراک نامعتبر است. سطوح مجاز: free، paid",
        )
    current_user.plan_tier = subscription.plan_tier
    await current_user.save()
    return UserOut.model_validate(current_user)


@router.get("/usage", response_model=UsageOut)
async def get_usage(current_user: User = Depends(get_current_user)):
    """Usage accounting for the current user from persisted UsageRecord rows."""
    tier = _resolve_tier(current_user.plan_tier)
    cutoff = datetime.fromtimestamp(get_now() - 86_400.0, tz=timezone.utc)
    records = await UsageRecord.filter(user=current_user, created_at__gte=cutoff)
    tokens_used = sum(r.tokens_count for r in records)
    return UsageOut(
        plan_tier=tier,
        tokens_used=tokens_used,
        quota_limit=TIER_QUOTAS[tier],
    )

