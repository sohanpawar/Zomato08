"""FastAPI Dependency Injection Providers.

Provides modular, override-friendly dependencies for application settings,
data repositories, filtering services, LLM clients, and the recommendation orchestrator.
"""

from functools import lru_cache
from fastapi import Depends

from app.config import Settings, get_settings
from app.data.repository import RestaurantRepository, SQLiteRestaurantRepository
from app.engine.cache import RecommendationCache
from app.engine.recommender import RecommendationEngine
from app.integration.filters import CandidateFilterService
from app.integration.prompt import PromptBuilder
from app.llm.client import LLMClient
from app.llm.factory import get_llm_client


def get_app_settings() -> Settings:
    """Dependency provider for application settings."""
    return get_settings()


@lru_cache
def get_recommendation_cache() -> RecommendationCache:
    """Singleton cache instance for recommendation responses."""
    return RecommendationCache(ttl_seconds=900.0)


def get_repository(
    settings: Settings = Depends(get_app_settings),
) -> RestaurantRepository:
    """Dependency provider for restaurant data repository."""
    return SQLiteRestaurantRepository(db_path=settings.sqlite_path)


def get_filter_service(
    repository: RestaurantRepository = Depends(get_repository),
) -> CandidateFilterService:
    """Dependency provider for candidate filtering and constraint relaxation service."""
    return CandidateFilterService(repository=repository)


def get_prompt_builder() -> PromptBuilder:
    """Dependency provider for prompt construction module."""
    return PromptBuilder()


def get_llm_service(
    settings: Settings = Depends(get_app_settings),
) -> LLMClient:
    """Dependency provider for configured LLM client."""
    return get_llm_client(settings)


def get_recommendation_engine(
    filter_service: CandidateFilterService = Depends(get_filter_service),
    prompt_builder: PromptBuilder = Depends(get_prompt_builder),
    llm_client: LLMClient = Depends(get_llm_service),
    cache: RecommendationCache = Depends(get_recommendation_cache),
    settings: Settings = Depends(get_app_settings),
) -> RecommendationEngine:
    """Dependency provider for the core recommendation engine orchestrator."""
    return RecommendationEngine(
        filter_service=filter_service,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        cache=cache,
        settings=settings,
    )
