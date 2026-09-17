"""Commercialization, Quotas, and Abuse Protection.

Implements:
- Server-side plan tier quotas (free vs paid vs anonymous)
- Sliding-window rate limiting
- Usage accounting (persisted to UsageRecord)
- Injectable clock for deterministic, sleep-free testing
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from models import UsageRecord, User

# Tier Quotas (Tokens per 24-hour window) per §12
TIER_QUOTAS: Dict[str, int] = {
    "anonymous": 500,      # Bounded anonymous allowance
    "free": 2_000,         # Registered free tier
    "paid": 50_000,        # Premium subscription tier
}

# Rate Limits: tier -> (max_requests, window_seconds)
TIER_RATE_LIMITS: Dict[str, Tuple[int, float]] = {
    "anonymous": (10, 60.0),    # 10 req / min
    "free": (30, 60.0),         # 30 req / min
    "paid": (120, 60.0),        # 120 req / min
}

# Injectable clock provider for deterministic testing
_time_provider: Optional[Callable[[], float]] = None


def get_now() -> float:
    """Returns current timestamp, respecting injected time provider if configured."""
    return _time_provider() if _time_provider is not None else time.time()


def set_time_provider(provider: Optional[Callable[[], float]]) -> None:
    """Sets or clears the mock time provider for testing."""
    global _time_provider
    _time_provider = provider


class RateLimiter:
    """In-memory sliding-window rate limiter per client identifier."""

    def __init__(self):
        self._history: Dict[str, List[float]] = {}

    def check(self, key: str, tier: str = "free") -> float:
        """Checks rate limit for the given key and tier. Raises 429 if exceeded.

        Records the request BEFORE evaluating remaining capacity (pre-consumption):
        a rejected request consumes its slot, so hammering a limited endpoint
        cannot keep the window permanently full (§12 abuse protection).

        Returns seconds elapsed since the start of the current window.
        """
        max_requests, window_seconds = TIER_RATE_LIMITS.get(tier, TIER_RATE_LIMITS["free"])
        now = get_now()
        cutoff = now - window_seconds

        history = [ts for ts in self._history.get(key, []) if ts >= cutoff]
        if len(history) >= max_requests:
            window_start = history[0]
            retry_after = max(1, int(round(window_start + window_seconds - now)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="تعداد درخواست‌های شما بیش از حد مجاز است. لطفاً کمی صبر کرده و مجدداً تلاش کنید.",
                headers={"Retry-After": str(retry_after)},
            )

        history.append(now)
        self._history[key] = history
        return now - history[0]

    def reset(self) -> None:
        """Clears in-memory rate limiting state."""
        self._history.clear()


class QuotaManager:
    """Manages token quotas and persists usage accounting records."""

    def __init__(self):
        # In-memory single-instance token tracking for anonymous IPs per §12
        self._anon_usage: Dict[str, List[Tuple[float, int]]] = {}
        # Per-identifier locks: quota check + usage record must be atomic per client,
        # otherwise concurrent requests can interleave between the usage read and the
        # record write and all pass the quota boundary (double-spend).
        self._locks: Dict[str, asyncio.Lock] = {}

    async def check_and_consume(
        self,
        user: Optional[User],
        identifier: str,
        tokens_count: int,
    ) -> int:
        """Enforces tier quota and records usage. Raises 429 if quota is exceeded.

        Returns total tokens consumed in the current 24-hour window.
        """
        now = get_now()
        window_start = now - 86400.0  # 24-hour sliding window

        # Serialize check+record per client identifier (see __init__ note).
        # Single-instance guarantee only; horizontal scaling needs a DB-level
        # atomic counter (scheduled Phase 10 per plan §13).
        lock = self._locks.setdefault(identifier, asyncio.Lock())
        async with lock:
            return await self._check_and_consume_locked(
                user, identifier, tokens_count, now, window_start
            )

    async def _check_and_consume_locked(
        self,
        user: Optional[User],
        identifier: str,
        tokens_count: int,
        now: float,
        window_start: float,
    ) -> int:
        if user:
            tier = getattr(user, "plan_tier", "free") or "free"
            if tier not in TIER_QUOTAS:
                tier = "free"
        else:
            tier = "anonymous"

        max_quota = TIER_QUOTAS[tier]

        # Calculate current usage in sliding window
        if user:
            cutoff_dt = datetime.fromtimestamp(window_start, tz=timezone.utc)
            records = await UsageRecord.filter(user=user, created_at__gte=cutoff_dt)
            used_tokens = sum(r.tokens_count for r in records)
        else:
            cleaned = [
                (ts, c) for ts, c in self._anon_usage.get(identifier, []) if ts >= window_start
            ]
            self._anon_usage[identifier] = cleaned
            used_tokens = sum(c for _, c in cleaned)

        if used_tokens + tokens_count > max_quota:
            if tier == "anonymous":
                detail = (
                    f"سقف مطالعه رایگان بدون ثبت‌نام ({max_quota} توکن) به پایان رسیده است. "
                    "لطفاً برای ادامه وارد حساب خود شوید."
                )
            else:
                detail = (
                    f"سقف مصرف مجاز شما در این دوره ({max_quota} توکن) به پایان رسیده است. "
                    "لطفاً اشتراک خود را ارتقا دهید یا در دوره بعدی تلاش کنید."
                )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            )

        # Record usage in database
        created_at_dt = datetime.fromtimestamp(now, tz=timezone.utc)
        await UsageRecord.create(
            user=user,
            identifier=identifier,
            tokens_count=tokens_count,
            endpoint="/api/rsvp/plan",
            created_at=created_at_dt,
        )

        if not user:
            self._anon_usage.setdefault(identifier, []).append((now, tokens_count))

        return used_tokens + tokens_count

    def reset(self) -> None:
        """Clears in-memory anonymous tracking state."""
        self._anon_usage.clear()
        self._locks.clear()


# Global singleton instances
rate_limiter = RateLimiter()
quota_manager = QuotaManager()
