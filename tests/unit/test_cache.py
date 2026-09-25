"""Unit Tests for RecommendationCache."""

import time

from app.engine.cache import RecommendationCache
from app.models.recommendation import (
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
)
from app.models.restaurant import BudgetBucket


def test_recommendation_cache_set_and_get() -> None:
    """Verify caching responses and retrieving exact query matches."""
    cache = RecommendationCache(ttl_seconds=60.0)

    req = RecommendationRequest(
        location="bangalore",
        budget=BudgetBucket.MEDIUM,
        cuisine=["Italian"],
        min_rating=4.0,
        top_n=2,
    )

    response = RecommendationResponse(
        query_echo=req.model_dump(),
        count=1,
        recommendations=[
            RecommendationItem(
                rank=1,
                id="rest_blr_001",
                name="Toscano",
                city="Bangalore",
                cuisine=["Italian"],
                rating=4.6,
                estimated_cost=1600,
                explanation="Authentic Italian pasta.",
                highlights=["Italian"],
            )
        ],
        summary="Top pick in Bangalore",
        ai_generated=True,
    )

    assert cache.get(req) is None

    cache.set(req, response)
    cached = cache.get(req)

    assert cached is not None
    assert cached.count == 1
    assert cached.recommendations[0].name == "Toscano"


def test_recommendation_cache_expiration() -> None:
    """Verify cache entries expire after TTL."""
    short_cache = RecommendationCache(ttl_seconds=0.01)

    req = RecommendationRequest(location="delhi", top_n=1)
    response = RecommendationResponse(
        query_echo=req.model_dump(),
        count=0,
        recommendations=[],
        summary="Empty",
        ai_generated=False,
    )

    short_cache.set(req, response)
    time.sleep(0.02)

    assert short_cache.get(req) is None
