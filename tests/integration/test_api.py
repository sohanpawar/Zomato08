"""Integration Tests for FastAPI Endpoints, Middleware, and Dependency Injection."""

from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.data.repository import SQLiteRestaurantRepository
from app.data.storage import save_restaurants_to_sqlite
from app.dependencies import (
    get_app_settings,
    get_llm_service,
    get_repository,
)
from app.llm.providers.mock import MockLLMClient
from app.main import app
from app.models.restaurant import Restaurant


@pytest.fixture
def client_with_test_db(
    tmp_path: Path,
    sample_restaurant_models: list[Restaurant],
) -> Generator[TestClient, None, None]:
    """Test client fixture with pre-populated SQLite database and Mock LLM dependency overrides."""
    db_path = tmp_path / "test_api.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    test_settings = Settings(
        app_env="test",
        sqlite_path=db_path,
        llm_provider="mock",
        shortlist_size=10,
    )

    test_repo = SQLiteRestaurantRepository(db_path=db_path)
    test_llm = MockLLMClient()

    app.dependency_overrides[get_app_settings] = lambda: test_settings
    app.dependency_overrides[get_repository] = lambda: test_repo
    app.dependency_overrides[get_llm_service] = lambda: test_llm

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# ==============================================================================
# 1. System & Health Endpoint Tests
# ==============================================================================


def test_health_endpoint_healthy(client_with_test_db: TestClient) -> None:
    """Verify /health returns 200 and healthy status when database is populated."""
    response = client_with_test_db.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_available"] is True
    assert data["total_restaurants"] == 6
    assert "version" in data

    # Verify custom middleware headers
    assert "x-request-id" in response.headers
    assert "x-response-time-ms" in response.headers


def test_health_endpoint_degraded(tmp_path: Path) -> None:
    """Verify /health returns degraded when database file is missing."""
    empty_settings = Settings(sqlite_path=tmp_path / "missing.db")
    empty_repo = SQLiteRestaurantRepository(db_path=tmp_path / "missing.db")

    app.dependency_overrides[get_app_settings] = lambda: empty_settings
    app.dependency_overrides[get_repository] = lambda: empty_repo

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database_available"] is False
        assert data["total_restaurants"] == 0

    app.dependency_overrides.clear()


# ==============================================================================
# 2. Metadata Endpoint Tests
# ==============================================================================


def test_meta_endpoint_success(client_with_test_db: TestClient) -> None:
    """Verify /meta returns dynamic cities, cuisines, and catalog metrics."""
    response = client_with_test_db.get("/meta")
    assert response.status_code == 200

    data = response.json()
    assert "bangalore" in data["cities"]
    assert "delhi" in data["cities"]
    assert "Italian" in data["cuisines"]
    assert "North Indian" in data["cuisines"]
    assert data["budget_options"] == ["low", "medium", "high", "any"]
    assert data["total_restaurants"] == 6


# ==============================================================================
# 3. Recommendation Endpoint Tests (/recommend)
# ==============================================================================


def test_recommend_endpoint_strict_match(client_with_test_db: TestClient) -> None:
    """Verify /recommend returns AI-ranked recommendations for valid strict preferences."""
    payload = {
        "location": "Bangalore",
        "budget": "any",
        "cuisine": ["Italian"],
        "min_rating": 4.0,
        "preferences": ["romantic ambiance"],
        "top_n": 2,
    }
    response = client_with_test_db.post("/recommend", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] >= 1
    assert data["ai_generated"] is True
    assert data["fallback_notice"] is None
    assert len(data["recommendations"]) >= 1

    first_item = data["recommendations"][0]
    assert first_item["rank"] == 1
    assert first_item["name"] == "Toscano"
    assert first_item["rating"] == 4.6
    assert first_item["estimated_cost"] == 1600
    assert "Italian" in first_item["cuisine"]
    assert len(first_item["explanation"]) > 5


def test_recommend_endpoint_progressive_relaxation(client_with_test_db: TestClient) -> None:
    """Verify /recommend triggers progressive relaxation when strict filters yield no results."""
    payload = {
        "location": "Delhi",
        "budget": "low",
        "cuisine": ["Mughlai"],
        "min_rating": 4.5,
        "top_n": 2,
    }
    response = client_with_test_db.post("/recommend", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] >= 1
    assert data["relaxation"] is not None
    assert data["relaxation"]["is_relaxed"] is True
    assert len(data["relaxation"]["relaxation_applied"]) > 0


def test_recommend_endpoint_unknown_location(client_with_test_db: TestClient) -> None:
    """Verify /recommend for unknown location returns count=0 with supported cities."""
    payload = {
        "location": "Atlantis",
        "top_n": 3,
    }
    response = client_with_test_db.post("/recommend", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 0
    assert data["recommendations"] == []
    assert data["ai_generated"] is False
    assert "Atlantis" in data["summary"]


def test_recommend_endpoint_fallback_on_llm_failure(
    tmp_path: Path,
    sample_restaurant_models: list[Restaurant],
) -> None:
    """Verify /recommend produces deterministic fallback recommendations when LLM provider fails."""
    db_path = tmp_path / "test_fallback_api.db"
    save_restaurants_to_sqlite(sample_restaurant_models, db_path)

    test_settings = Settings(app_env="test", sqlite_path=db_path)
    test_repo = SQLiteRestaurantRepository(db_path=db_path)
    failing_llm = MockLLMClient(simulate_timeout=True)

    app.dependency_overrides[get_app_settings] = lambda: test_settings
    app.dependency_overrides[get_repository] = lambda: test_repo
    app.dependency_overrides[get_llm_service] = lambda: failing_llm

    with TestClient(app) as client:
        payload = {"location": "Bangalore", "top_n": 2}
        response = client.post("/recommend", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 2
        assert data["ai_generated"] is False
        assert data["fallback_notice"] is not None
        assert len(data["recommendations"]) == 2

    app.dependency_overrides.clear()


# ==============================================================================
# 4. Input Validation & Error Handling Tests
# ==============================================================================


def test_recommend_validation_error_invalid_rating(client_with_test_db: TestClient) -> None:
    """Verify 422 error when rating exceeds boundary."""
    payload = {
        "location": "Bangalore",
        "min_rating": 7.5,  # Invalid (> 5.0)
    }
    response = client_with_test_db.post("/recommend", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert data["error_code"] == "REQUEST_VALIDATION_ERROR"
    assert "details" in data
    assert "validation_errors" in data["details"]


def test_recommend_validation_error_short_location(client_with_test_db: TestClient) -> None:
    """Verify 422 error when location is shorter than 2 chars."""
    payload = {"location": "A"}
    response = client_with_test_db.post("/recommend", json=payload)
    assert response.status_code == 422


def test_recommend_validation_error_top_n_bounds(client_with_test_db: TestClient) -> None:
    """Verify 422 error when top_n is out of allowed bounds."""
    response_zero = client_with_test_db.post("/recommend", json={"location": "Delhi", "top_n": 0})
    assert response_zero.status_code == 422

    response_large = client_with_test_db.post("/recommend", json={"location": "Delhi", "top_n": 50})
    assert response_large.status_code == 422


def test_openapi_documentation_accessible(client_with_test_db: TestClient) -> None:
    """Verify OpenAPI JSON schema endpoint is accessible and valid."""
    response = client_with_test_db.get("/openapi.json")
    assert response.status_code == 200

    data = response.json()
    assert data["info"]["title"] == "AI-Powered Restaurant Recommendation API"
    assert "/health" in data["paths"]
    assert "/meta" in data["paths"]
    assert "/recommend" in data["paths"]
