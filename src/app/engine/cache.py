"""In-Memory Recommendation Response Cache.

Caches recommendation outcomes by normalized query signature to conserve
LLM token quotas (TPM/TPD) and request limits (RPM/RPD) on repeated identical requests.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from app.logging import get_logger
from app.models.recommendation import RecommendationRequest, RecommendationResponse

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    response: RecommendationResponse
    expires_at: float


class RecommendationCache:
    """Thread-safe TTL in-memory cache for recommendation responses."""

    def __init__(self, ttl_seconds: float = 900.0, max_entries: int = 500) -> None:
        """Initialize recommendation cache.

        Args:
            ttl_seconds: Cache time-to-live in seconds (default: 15 minutes).
            max_entries: Maximum number of distinct query results to cache.
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}

    def _generate_key(self, request: RecommendationRequest) -> str:
        """Generate a deterministic cache key from normalized request attributes."""
        norm_cuisines = sorted([c.strip().lower() for c in request.cuisine]) if request.cuisine else []
        norm_prefs = sorted([p.strip().lower() for p in request.preferences]) if request.preferences else []

        payload = {
            "location": request.location.strip().lower(),
            "budget": request.budget.value,
            "cuisines": norm_cuisines,
            "min_rating": round(request.min_rating, 2),
            "preferences": norm_prefs,
            "top_n": request.top_n,
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def get(self, request: RecommendationRequest) -> RecommendationResponse | None:
        """Retrieve a cached response if present and not expired."""
        key = self._generate_key(request)
        entry = self._cache.get(key)
        if not entry:
            return None

        now = time.time()
        if entry.expires_at < now:
            del self._cache[key]
            return None

        logger.debug("Cache hit for query: %s (Key: %s)", request.location, key)
        return entry.response

    def set(self, request: RecommendationRequest, response: RecommendationResponse) -> None:
        """Store a recommendation response in cache."""
        if len(self._cache) >= self.max_entries:
            # Simple eviction of expired or oldest entry
            now = time.time()
            expired_keys = [k for k, v in self._cache.items() if v.expires_at < now]
            for k in expired_keys:
                del self._cache[k]

            if len(self._cache) >= self.max_entries:
                # Evict first key if still full
                first_key = next(iter(self._cache))
                del self._cache[first_key]

        key = self._generate_key(request)
        expires_at = time.time() + self.ttl_seconds
        self._cache[key] = CacheEntry(response=response, expires_at=expires_at)
        logger.debug("Cached recommendation response for: %s (Key: %s)", request.location, key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
