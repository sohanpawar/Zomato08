"""Unit and Query Tests for SQLiteRestaurantRepository."""

from pathlib import Path
import pytest

from app.data.repository import SQLiteRestaurantRepository
from app.data.storage import save_restaurants_to_sqlite
from app.exceptions import RepositoryError
from app.models.restaurant import BudgetBucket, Restaurant


@pytest.fixture
def test_repo(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> SQLiteRestaurantRepository:
    """Provides a SQLite repository initialized with sample fixture records."""
    db_path = tmp_path / "test_repo.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)
    return SQLiteRestaurantRepository(db_path)


def test_repository_availability(test_repo: SQLiteRestaurantRepository, tmp_path: Path) -> None:
    """Verify repository availability check."""
    assert test_repo.is_available() is True

    missing_repo = SQLiteRestaurantRepository(tmp_path / "non_existent.db")
    assert missing_repo.is_available() is False


def test_get_by_id_found_and_missing(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify get_by_id returns the restaurant or None if not found."""
    found = test_repo.get_by_id("rest_blr_001")
    assert found is not None
    assert found.name == "Toscano"
    assert found.city == "bangalore"
    assert found.rating == 4.6
    assert found.cost_for_two == 1600
    assert found.budget_bucket == BudgetBucket.HIGH

    missing = test_repo.get_by_id("non_existent_id")
    assert missing is None


def test_get_by_ids_preserves_order(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify get_by_ids returns records in the exact requested order."""
    requested_ids = ["rest_del_001", "rest_blr_001", "rest_blr_003"]
    results = test_repo.get_by_ids(requested_ids)

    assert len(results) == 3
    assert [r.id for r in results] == requested_ids
    assert results[0].name == "Karim's"
    assert results[1].name == "Toscano"
    assert results[2].name == "Taaza Thindi"


def test_get_by_ids_handles_missing_elements(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify get_by_ids gracefully ignores missing IDs."""
    requested_ids = ["rest_blr_001", "ghost_id_123", "rest_del_002"]
    results = test_repo.get_by_ids(requested_ids)

    assert len(results) == 2
    assert [r.id for r in results] == ["rest_blr_001", "rest_del_002"]


def test_find_candidates_city_matching(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify city matching works case-insensitively."""
    blr_matches = test_repo.find_candidates(location="Bangalore")
    assert len(blr_matches) == 3
    assert all(r.city == "bangalore" for r in blr_matches)

    # Lowercase match
    del_matches = test_repo.find_candidates(location="delhi")
    assert len(del_matches) == 3
    assert all(r.city == "delhi" for r in del_matches)


def test_find_candidates_area_substring_matching(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify area matching works when searching for sub-localities."""
    koramangala = test_repo.find_candidates(location="Koramangala")
    assert len(koramangala) == 1
    assert koramangala[0].name == "Toscano"

    jayanagar = test_repo.find_candidates(location="Jayanagar")
    assert len(jayanagar) == 1
    assert jayanagar[0].name == "Taaza Thindi"


def test_find_candidates_budget_filter(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify budget tier filtering in Bangalore and Delhi."""
    # Low budget in Bangalore (Taaza Thindi: 200)
    low_blr = test_repo.find_candidates(location="bangalore", budget=BudgetBucket.LOW)
    assert len(low_blr) == 1
    assert low_blr[0].name == "Taaza Thindi"

    # High budget in Bangalore (Toscano: 1600)
    high_blr = test_repo.find_candidates(location="bangalore", budget=BudgetBucket.HIGH)
    assert len(high_blr) == 1
    assert high_blr[0].name == "Toscano"

    # Any budget
    any_blr = test_repo.find_candidates(location="bangalore", budget=BudgetBucket.ANY)
    assert len(any_blr) == 3


def test_find_candidates_min_rating(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify rating threshold filtering."""
    high_rated = test_repo.find_candidates(location="delhi", min_rating=4.5)
    assert len(high_rated) == 2  # Bukhara (4.8), Karim's (4.5)
    assert all(r.rating >= 4.5 for r in high_rated)

    strict_rated = test_repo.find_candidates(location="delhi", min_rating=4.7)
    assert len(strict_rated) == 1
    assert strict_rated[0].name == "Bukhara - ITC Maurya"


def test_find_candidates_cuisine_filtering(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify single and multi-cuisine filtering logic."""
    italian = test_repo.find_candidates(location="bangalore", cuisines=["Italian"])
    assert len(italian) == 1
    assert italian[0].name == "Toscano"

    # Multi-cuisine OR search: Italian OR South Indian
    multi = test_repo.find_candidates(location="bangalore", cuisines=["Italian", "South Indian"])
    assert len(multi) == 3  # Toscano (Italian), Nagarjuna (South Indian), Taaza Thindi (South Indian)

    # Non-existent cuisine in Bangalore
    none_match = test_repo.find_candidates(location="bangalore", cuisines=["Mexican"])
    assert len(none_match) == 0


def test_find_candidates_sql_injection_resistance(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify malicious SQL injection payloads are safely sanitized by parameterization."""
    malicious_loc = "bangalore' OR '1'='1"
    res = test_repo.find_candidates(location=malicious_loc)
    # Parameterized query should treat the entire string as a literal location value (matching 0)
    assert len(res) == 0

    malicious_cuisine = ["Italian'); DROP TABLE restaurants; --"]
    res_cuisine = test_repo.find_candidates(location="bangalore", cuisines=malicious_cuisine)
    assert len(res_cuisine) == 0

    # Ensure database table is intact
    assert test_repo.count_total() == 6


def test_list_cities_and_cuisines(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify catalog metadata listings."""
    cities = test_repo.list_cities()
    assert cities == ["bangalore", "delhi"]

    global_cuisines = test_repo.list_cuisines()
    assert "Italian" in global_cuisines
    assert "South Indian" in global_cuisines
    assert "Mughlai" in global_cuisines

    delhi_cuisines = test_repo.list_cuisines(city="delhi")
    assert "Mughlai" in delhi_cuisines
    assert "Italian" not in delhi_cuisines


def test_catalog_stats(test_repo: SQLiteRestaurantRepository) -> None:
    """Verify catalog aggregate statistics."""
    stats = test_repo.get_catalog_stats()
    assert stats["total_count"] == 6
    assert stats["min_rating"] == 3.9
    assert stats["max_rating"] == 4.8
    assert stats["min_cost"] == 200
    assert stats["max_cost"] == 6500
    assert stats["avg_rating"] > 4.0
