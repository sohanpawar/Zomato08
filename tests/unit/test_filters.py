"""Unit Tests for CandidateFilterService, Pre-Ranking Scoring, and Constraint Relaxation."""

from pathlib import Path
import pytest

from app.data.repository import SQLiteRestaurantRepository
from app.data.storage import save_restaurants_to_sqlite
from app.integration.filters import CandidateFilterService
from app.models.recommendation import RecommendationRequest
from app.models.restaurant import BudgetBucket, Restaurant


@pytest.fixture
def filter_service(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> CandidateFilterService:
    """Provides CandidateFilterService connected to a populated SQLite repository."""
    db_path = tmp_path / "test_filter_service.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)
    repo = SQLiteRestaurantRepository(db_path)
    return CandidateFilterService(repository=repo)


# ==============================================================================
# 1. Pre-Ranking Scoring Tests
# ==============================================================================


def test_calculate_pre_ranking_score_boosts(filter_service: CandidateFilterService) -> None:
    """Verify pre-ranking scoring formula boosts ratings, cuisines, and features."""
    rest = Restaurant(
        id="rest_test_01",
        name="Pasta Palace",
        city="bangalore",
        area="Indiranagar",
        cuisines=["Italian", "Continental"],
        cost_for_two=1000,
        budget_bucket=BudgetBucket.MEDIUM,
        rating=4.5,
        votes=300,
        features=["family_friendly", "online_delivery"],
    )

    # Base request
    base_req = RecommendationRequest(location="bangalore")
    base_score = filter_service.calculate_pre_ranking_score(rest, base_req)
    # Expected: (4.5 * 1000) + 300 + (1000 / 1001) = 4500 + 300 + 0.999 = 4800.999
    assert base_score > 4800.0

    # Request matching cuisine
    cuisine_req = RecommendationRequest(location="bangalore", cuisine=["Italian"])
    cuisine_score = filter_service.calculate_pre_ranking_score(rest, cuisine_req)
    assert cuisine_score == round(base_score + 200.0, 4)

    # Request matching preferences
    pref_req = RecommendationRequest(location="bangalore", preferences=["family-friendly"])
    pref_score = filter_service.calculate_pre_ranking_score(rest, pref_req)
    assert pref_score == round(base_score + 150.0, 4)

    # Request matching area specifically
    area_req = RecommendationRequest(location="Indiranagar")
    area_score = filter_service.calculate_pre_ranking_score(rest, area_req)
    assert area_score == round(base_score + 250.0, 4)


def test_sort_and_rank_candidates_deterministic(
    filter_service: CandidateFilterService,
    sample_restaurant_models: list[Restaurant],
) -> None:
    """Verify ranking produces identical output across multiple runs for deterministic stability."""
    req = RecommendationRequest(location="bangalore", budget=BudgetBucket.ANY, top_n=3)

    run_1 = filter_service.sort_and_rank_candidates(sample_restaurant_models, req)
    run_2 = filter_service.sort_and_rank_candidates(sample_restaurant_models, req)

    assert [r.id for r in run_1] == [r.id for r in run_2]


# ==============================================================================
# 2. Strict Filtering & Shortlisting Tests
# ==============================================================================


def test_filter_and_shortlist_strict_success(filter_service: CandidateFilterService) -> None:
    """Verify strict filtering when sufficient matches exist."""
    req = RecommendationRequest(
        location="bangalore",
        budget=BudgetBucket.ANY,
        min_rating=4.0,
        top_n=2,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=10)

    assert result.is_relaxed is False
    assert result.relaxation is None
    assert len(result.candidates) >= 2
    assert all(r.rating >= 4.0 for r in result.candidates)
    assert len(result.raw_restaurants) == len(result.candidates)


# ==============================================================================
# 3. Progressive Constraint Relaxation Tests
# ==============================================================================


def test_filter_and_shortlist_relaxes_high_rating(filter_service: CandidateFilterService) -> None:
    """Verify system lowers minimum rating if strict criteria yields zero matches."""
    # Delhi has Moti Mahal (3.9), Karim's (4.5), Bukhara (4.8)
    # User asks for min_rating 4.9 in Delhi (0 match strictly)
    req = RecommendationRequest(
        location="delhi",
        budget=BudgetBucket.ANY,
        min_rating=4.9,
        top_n=3,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=5)

    assert result.is_relaxed is True
    assert result.relaxation is not None
    assert len(result.candidates) == 3
    rating_steps = [
        step for step in result.relaxation.relaxation_applied if "minimum rating" in step
    ]
    assert len(rating_steps) == 1
    assert "from 4.9★ to" in rating_steps[0]


def test_filter_and_shortlist_consolidates_rating_relaxation_steps(
    filter_service: CandidateFilterService,
) -> None:
    """Verify multiple rating decrements produce one consolidated audit message."""
    req = RecommendationRequest(
        location="delhi",
        budget=BudgetBucket.LOW,
        min_rating=4.8,
        top_n=5,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=5)

    assert result.relaxation is not None
    rating_steps = [
        step for step in result.relaxation.relaxation_applied if "minimum rating" in step
    ]
    assert len(rating_steps) == 1
    assert rating_steps[0].startswith("Lowered minimum rating threshold from 4.8★ to")


def test_filter_and_shortlist_widens_budget(filter_service: CandidateFilterService) -> None:
    """Verify system widens budget tier when no restaurants match in requested budget."""
    # In Delhi, there are no French/Italian restaurants in low budget
    req = RecommendationRequest(
        location="delhi",
        budget=BudgetBucket.LOW,
        cuisine=["Mughlai"],
        min_rating=4.5,  # Karim's is medium budget (900), not low
        top_n=1,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=5)

    assert result.is_relaxed is True
    assert result.relaxation is not None
    assert len(result.candidates) >= 1
    assert result.candidates[0].name == "Karim's"
    assert any("Expanded budget tier" in step for step in result.relaxation.relaxation_applied)


def test_filter_and_shortlist_relaxes_cuisine(filter_service: CandidateFilterService) -> None:
    """Verify system relaxes cuisine when non-existent cuisine is requested."""
    req = RecommendationRequest(
        location="bangalore",
        cuisine=["French"],  # No French restaurant in test fixture
        min_rating=4.0,
        top_n=3,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=5)

    assert result.is_relaxed is True
    assert result.relaxation is not None
    assert len(result.candidates) == 3
    assert any("Broadened cuisine criteria" in step for step in result.relaxation.relaxation_applied)


def test_filter_and_shortlist_unknown_location(filter_service: CandidateFilterService) -> None:
    """Verify unknown location gracefully returns 0 candidates and lists supported cities."""
    req = RecommendationRequest(
        location="Atlantis",
        min_rating=4.0,
        top_n=5,
    )
    result = filter_service.filter_and_shortlist(req, shortlist_size=5)

    assert result.is_relaxed is True
    assert len(result.candidates) == 0
    assert result.total_matches_found == 0
    assert result.relaxation is not None
    assert "supported_cities" in result.relaxation.effective_query
    assert "bangalore" in result.relaxation.effective_query["supported_cities"]
