"""Unit and Integration Tests for RecommendationEngine Orchestrator."""

from pathlib import Path
import pytest

from app.config import Settings
from app.data.repository import SQLiteRestaurantRepository
from app.data.storage import save_restaurants_to_sqlite
from app.engine.recommender import RecommendationEngine
from app.integration.filters import CandidateFilterService
from app.integration.prompt import PromptBuilder
from app.llm.providers.mock import MockLLMClient
from app.models.recommendation import (
    LLMSelectedRecommendation,
    LLMStructuredOutput,
    RecommendationRequest,
)
from app.models.restaurant import BudgetBucket, Restaurant


@pytest.fixture
def recommender_setup(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> tuple[RecommendationEngine, MockLLMClient]:
    """Provides a configured RecommendationEngine with a connected SQLite repository and Mock LLM."""
    db_path = tmp_path / "test_engine.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    repo = SQLiteRestaurantRepository(db_path)
    filter_service = CandidateFilterService(repository=repo)
    mock_llm = MockLLMClient()
    settings = Settings(llm_provider="mock", shortlist_size=10)

    engine = RecommendationEngine(
        filter_service=filter_service,
        prompt_builder=PromptBuilder(),
        llm_client=mock_llm,
        settings=settings,
    )
    return engine, mock_llm


@pytest.mark.asyncio
async def test_recommendation_engine_success(recommender_setup: tuple[RecommendationEngine, MockLLMClient]) -> None:
    """Verify standard recommendation flow with AI ranking and metadata hydration."""
    engine, mock_llm = recommender_setup

    req = RecommendationRequest(
        location="bangalore",
        budget=BudgetBucket.ANY,
        min_rating=4.0,
        top_n=2,
    )

    response = await engine.recommend(req)

    assert response.count == 2
    assert len(response.recommendations) == 2
    assert response.ai_generated is True
    assert response.fallback_notice is None
    assert response.recommendations[0].rank == 1
    assert response.recommendations[1].rank == 2

    # Verify metadata hydrated from database
    rec1 = response.recommendations[0]
    assert rec1.name in {"Toscano", "Taaza Thindi", "Nagarjuna"}
    assert rec1.rating >= 4.0
    assert rec1.estimated_cost > 0


@pytest.mark.asyncio
async def test_recommendation_engine_anti_hallucination_guard(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify hallucinated IDs are purged and valid candidate IDs are backfilled."""
    db_path = tmp_path / "test_anti_hallucination.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    repo = SQLiteRestaurantRepository(db_path)
    filter_service = CandidateFilterService(repository=repo)

    # Mock client returns a hallucinated ghost ID along with 1 valid ID
    hallucinated_output = LLMStructuredOutput(
        recommendations=[
            LLMSelectedRecommendation(
                id="fake_hallucinated_ghost_id_999",
                rank=1,
                explanation="Fake restaurant that does not exist.",
            ),
            LLMSelectedRecommendation(
                id="rest_blr_001",  # Valid (Toscano)
                rank=2,
                explanation="Authentic Italian pasta.",
            ),
        ],
        summary="Here are your picks.",
    )

    mock_llm = MockLLMClient(preset_response=hallucinated_output)
    engine = RecommendationEngine(
        filter_service=filter_service,
        llm_client=mock_llm,
        settings=Settings(llm_provider="mock"),
    )

    req = RecommendationRequest(location="bangalore", top_n=2)
    response = await engine.recommend(req)

    # Assert hallucinated ID was purged and backfilled up to top_n=2
    assert response.count == 2
    ids_returned = [r.id for r in response.recommendations]
    assert "fake_hallucinated_ghost_id_999" not in ids_returned
    assert "rest_blr_001" in ids_returned
    # All returned IDs must be valid candidates in the database
    assert all(r.name in {"Toscano", "Nagarjuna", "Taaza Thindi"} for r in response.recommendations)


@pytest.mark.asyncio
async def test_recommendation_engine_factual_attribute_integrity(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify factual attributes (cost, rating, cuisines) always match the SQLite database."""
    db_path = tmp_path / "test_facts.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    repo = SQLiteRestaurantRepository(db_path)
    filter_service = CandidateFilterService(repository=repo)
    mock_llm = MockLLMClient()
    engine = RecommendationEngine(
        filter_service=filter_service,
        llm_client=mock_llm,
        settings=Settings(llm_provider="mock"),
    )

    req = RecommendationRequest(location="bangalore", top_n=3)
    response = await engine.recommend(req)

    for item in response.recommendations:
        db_entity = repo.get_by_id(item.id)
        assert db_entity is not None
        assert item.name == db_entity.name
        assert item.rating == db_entity.rating
        assert item.estimated_cost == db_entity.cost_for_two
        assert item.cuisine == db_entity.cuisines


@pytest.mark.asyncio
async def test_recommendation_engine_fallback_on_llm_timeout(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify engine activates deterministic heuristic fallback when LLM times out."""
    db_path = tmp_path / "test_timeout.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    repo = SQLiteRestaurantRepository(db_path)
    filter_service = CandidateFilterService(repository=repo)
    mock_llm = MockLLMClient(simulate_timeout=True)

    engine = RecommendationEngine(
        filter_service=filter_service,
        llm_client=mock_llm,
        settings=Settings(llm_provider="mock"),
    )

    req = RecommendationRequest(location="delhi", top_n=2)
    response = await engine.recommend(req)

    assert response.count == 2
    assert response.ai_generated is False
    assert response.fallback_notice is not None
    assert "LLMTimeoutError" in response.fallback_notice
    # Explanations still present and grounded
    assert len(response.recommendations[0].explanation) > 10


@pytest.mark.asyncio
async def test_recommendation_engine_fallback_on_malformed_llm_output(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify engine activates heuristic fallback when LLM output is malformed."""
    db_path = tmp_path / "test_malformed.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    repo = SQLiteRestaurantRepository(db_path)
    filter_service = CandidateFilterService(repository=repo)
    mock_llm = MockLLMClient(simulate_malformed=True)

    engine = RecommendationEngine(
        filter_service=filter_service,
        llm_client=mock_llm,
        settings=Settings(llm_provider="mock"),
    )

    req = RecommendationRequest(location="delhi", top_n=3)
    response = await engine.recommend(req)

    assert response.count == 3
    assert response.ai_generated is False
    assert response.fallback_notice is not None


@pytest.mark.asyncio
async def test_recommendation_engine_unknown_location_empty_response(recommender_setup: tuple[RecommendationEngine, MockLLMClient]) -> None:
    """Verify unknown location gracefully returns count=0 without calling LLM."""
    engine, mock_llm = recommender_setup

    req = RecommendationRequest(location="Atlantis", top_n=5)
    response = await engine.recommend(req)

    assert response.count == 0
    assert len(response.recommendations) == 0
    assert response.ai_generated is False
    assert "Atlantis" in response.summary
    assert len(mock_llm.call_history) == 0  # LLM was never called
