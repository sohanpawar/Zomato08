"""Unit Tests for LLMRateLimiter (RPM, RPD, TPM, TPD Sliding Windows)."""

import pytest

from app.llm.rate_limiter import LLMRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_rpm_limit() -> None:
    """Verify rate limiter blocks when RPM limit is reached."""
    limiter = LLMRateLimiter(max_rpm=3, max_rpd=100, max_tpm=10000, max_tpd=100000)

    # 3 requests allowed within 1 minute
    assert await limiter.check_and_acquire(estimated_tokens=100) is True
    assert await limiter.check_and_acquire(estimated_tokens=100) is True
    assert await limiter.check_and_acquire(estimated_tokens=100) is True

    # 4th request blocked
    assert await limiter.check_and_acquire(estimated_tokens=100) is False

    stats = await limiter.get_stats()
    assert stats.current_rpm == 3
    assert stats.max_rpm == 3


@pytest.mark.asyncio
async def test_rate_limiter_tpm_limit() -> None:
    """Verify rate limiter blocks when TPM limit is reached."""
    limiter = LLMRateLimiter(max_rpm=50, max_rpd=1000, max_tpm=2000, max_tpd=100000)

    # Acquire 1500 tokens (allowed)
    assert await limiter.check_and_acquire(estimated_tokens=1500) is True

    # Try acquiring another 1000 tokens (1500 + 1000 = 2500 > 2000 TPM limit) -> blocked
    assert await limiter.check_and_acquire(estimated_tokens=1000) is False


@pytest.mark.asyncio
async def test_rate_limiter_record_actual_usage_reconciliation() -> None:
    """Verify actual usage adjustment updates tracked tokens."""
    limiter = LLMRateLimiter(max_rpm=10, max_tpm=5000)

    # Reserve 1000 tokens
    await limiter.check_and_acquire(estimated_tokens=1000)
    stats_before = await limiter.get_stats()
    assert stats_before.current_tpm == 1000

    # Reconcile with actual 600 tokens consumed (diff: -400)
    await limiter.record_actual_usage(actual_tokens=600, estimated_tokens_reserved=1000)
    stats_after = await limiter.get_stats()
    assert stats_after.current_tpm == 600


@pytest.mark.asyncio
async def test_rate_limiter_reset() -> None:
    """Verify reset clears all sliding window tracking."""
    limiter = LLMRateLimiter(max_rpm=2, max_tpm=1000)
    await limiter.check_and_acquire(estimated_tokens=500)
    await limiter.check_and_acquire(estimated_tokens=500)
    assert await limiter.check_and_acquire(estimated_tokens=100) is False

    await limiter.reset()
    assert await limiter.check_and_acquire(estimated_tokens=100) is True
