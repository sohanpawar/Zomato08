"""Sliding-Window Rate Limiter and Token Quota Guard.

Enforces strict client-side limits for the LLM provider (openai/gpt-oss-120b on Groq):
    - Requests Per Minute (RPM): 30
    - Requests Per Day (RPD):    1,000 (1K)
    - Tokens Per Minute (TPM):   8,000 (8K)
    - Tokens Per Day (TPD):      200,000 (200K)

Prevents API 429 rate limit rejections and gracefully triggers heuristic fallback
when quota limits are reached.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from app.exceptions import LLMError
from app.logging import get_logger

logger = get_logger(__name__)


class TokenEntry(NamedTuple):
    timestamp: float
    tokens: int


class RateLimitExceededError(LLMError):
    """Raised when client-side rate limits (RPM, RPD, TPM, TPD) are reached."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:  # type: ignore[name-defined]
        super().__init__(
            message=f"Rate limit exceeded: {reason}. Switching to graceful fallback.",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details or {"reason": reason},
        )


@dataclass
class RateLimitStats:
    """Current consumption statistics across rate limit windows."""

    current_rpm: int = 0
    max_rpm: int = 30
    current_rpd: int = 0
    max_rpd: int = 1000
    current_tpm: int = 0
    max_tpm: int = 8000
    current_tpd: int = 0
    max_tpd: int = 200000


class LLMRateLimiter:
    """Thread-safe sliding-window rate limiter for LLM calls."""

    def __init__(
        self,
        max_rpm: int = 30,
        max_rpd: int = 1000,
        max_tpm: int = 8000,
        max_tpd: int = 200000,
    ) -> None:
        self.max_rpm = max_rpm
        self.max_rpd = max_rpd
        self.max_tpm = max_tpm
        self.max_tpd = max_tpd

        self._requests_minute: deque[float] = deque()
        self._requests_day: deque[float] = deque()
        self._tokens_minute: deque[TokenEntry] = deque()
        self._tokens_day: deque[TokenEntry] = deque()

        self._lock = asyncio.Lock()

    def _cleanup_expired(self, now: float) -> None:
        """Purge entries older than 60 seconds (minute windows) and 86400 seconds (day windows)."""
        minute_cutoff = now - 60.0
        day_cutoff = now - 86400.0

        while self._requests_minute and self._requests_minute[0] <= minute_cutoff:
            self._requests_minute.popleft()

        while self._requests_day and self._requests_day[0] <= day_cutoff:
            self._requests_day.popleft()

        while self._tokens_minute and self._tokens_minute[0].timestamp <= minute_cutoff:
            self._tokens_minute.popleft()

        while self._tokens_day and self._tokens_day[0].timestamp <= day_cutoff:
            self._tokens_day.popleft()

    async def check_and_acquire(self, estimated_tokens: int = 1000) -> bool:
        """Check if an upcoming LLM request fits within RPM, RPD, TPM, and TPD quotas.

        If within limits, registers the request and reserves estimated tokens.

        Args:
            estimated_tokens: Estimated prompt + completion tokens budget.

        Returns:
            bool: True if acquired; False if quota would be exceeded.
        """
        async with self._lock:
            now = time.time()
            self._cleanup_expired(now)

            # 1. Check Requests Per Minute (RPM)
            if len(self._requests_minute) >= self.max_rpm:
                logger.warning(
                    "Rate limit reached: %d/%d RPM limit active.",
                    len(self._requests_minute),
                    self.max_rpm,
                )
                return False

            # 2. Check Requests Per Day (RPD)
            if len(self._requests_day) >= self.max_rpd:
                logger.warning(
                    "Rate limit reached: %d/%d RPD limit active.",
                    len(self._requests_day),
                    self.max_rpd,
                )
                return False

            # 3. Check Tokens Per Minute (TPM)
            current_tpm = sum(entry.tokens for entry in self._tokens_minute)
            if current_tpm + estimated_tokens > self.max_tpm:
                logger.warning(
                    "Token limit reached: %d + %d > %d TPM limit active.",
                    current_tpm,
                    estimated_tokens,
                    self.max_tpm,
                )
                return False

            # 4. Check Tokens Per Day (TPD)
            current_tpd = sum(entry.tokens for entry in self._tokens_day)
            if current_tpd + estimated_tokens > self.max_tpd:
                logger.warning(
                    "Token limit reached: %d + %d > %d TPD limit active.",
                    current_tpd,
                    estimated_tokens,
                    self.max_tpd,
                )
                return False

            # Acquire quota
            self._requests_minute.append(now)
            self._requests_day.append(now)
            self._tokens_minute.append(TokenEntry(timestamp=now, tokens=estimated_tokens))
            self._tokens_day.append(TokenEntry(timestamp=now, tokens=estimated_tokens))

            return True

    async def record_actual_usage(
        self,
        actual_tokens: int,
        estimated_tokens_reserved: int = 1000,
    ) -> None:
        """Reconcile reserved estimated tokens with actual consumed tokens from API telemetry."""
        async with self._lock:
            now = time.time()
            self._cleanup_expired(now)

            diff = actual_tokens - estimated_tokens_reserved
            if diff != 0 and self._tokens_minute:
                # Adjust the most recent token entries by the difference
                last_min = self._tokens_minute.pop()
                self._tokens_minute.append(
                    TokenEntry(
                        timestamp=last_min.timestamp,
                        tokens=max(0, last_min.tokens + diff),
                    )
                )

            if diff != 0 and self._tokens_day:
                last_day = self._tokens_day.pop()
                self._tokens_day.append(
                    TokenEntry(
                        timestamp=last_day.timestamp,
                        tokens=max(0, last_day.tokens + diff),
                    )
                )

    async def get_stats(self) -> RateLimitStats:
        """Retrieve current usage statistics."""
        async with self._lock:
            now = time.time()
            self._cleanup_expired(now)
            return RateLimitStats(
                current_rpm=len(self._requests_minute),
                max_rpm=self.max_rpm,
                current_rpd=len(self._requests_day),
                max_rpd=self.max_rpd,
                current_tpm=sum(e.tokens for e in self._tokens_minute),
                max_tpm=self.max_tpm,
                current_tpd=sum(e.tokens for e in self._tokens_day),
                max_tpd=self.max_tpd,
            )

    async def reset(self) -> None:
        """Reset all rate limiter counters (useful for unit testing)."""
        async with self._lock:
            self._requests_minute.clear()
            self._requests_day.clear()
            self._tokens_minute.clear()
            self._tokens_day.clear()
