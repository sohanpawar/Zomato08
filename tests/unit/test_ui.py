"""Unit tests for the Streamlit UI API client and state handling."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.models.recommendation import (
    MetadataResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from app.models.restaurant import BudgetBucket
from ui.api_client import BackendAPIClient


@pytest.fixture
def api_client() -> BackendAPIClient:
    return BackendAPIClient(base_url="http://testserver:8000", timeout_seconds=5.0)


def test_api_client_health_success(api_client: BackendAPIClient) -> None:
    """Test health check returns success dictionary on 200."""
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "healthy",
            "version": "0.1.0",
            "database_available": True,
            "total_restaurants": 9500,
            "llm_provider": "groq",
            "llm_model": "openai/gpt-oss-120b",
        }
        mock_get.return_value = mock_resp

        health = api_client.check_health()
        assert health["status"] == "healthy"
        assert health["total_restaurants"] == 9500


def test_api_client_health_failure(api_client: BackendAPIClient) -> None:
    """Test health check returns unreachable status when connection fails."""
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
        health = api_client.check_health()
        assert health["status"] == "unreachable"
        assert health["database_available"] is False
        assert "Connection refused" in health["error"]


def test_api_client_get_metadata_success(api_client: BackendAPIClient) -> None:
    """Test metadata retrieval on 200 OK."""
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "cities": ["bangalore", "delhi"],
            "cuisines": ["Italian", "North Indian"],
            "budget_options": ["low", "medium", "high", "any"],
            "min_rating_range": [0.0, 5.0],
            "max_top_n": 20,
            "total_restaurants": 100,
        }
        mock_get.return_value = mock_resp

        meta = api_client.get_metadata()
        assert isinstance(meta, MetadataResponse)
        assert meta.cities == ["bangalore", "delhi"]
        assert "Italian" in meta.cuisines


def test_api_client_get_metadata_fallback_on_error(api_client: BackendAPIClient) -> None:
    """Test fallback metadata is returned when server is unreachable."""
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Server down")):
        meta = api_client.get_metadata()
        assert isinstance(meta, MetadataResponse)
        assert "bangalore" in meta.cities
        assert "North Indian" in meta.cuisines
        assert meta.total_restaurants == 0


def test_api_client_get_recommendations_success(
    api_client: BackendAPIClient,
    sample_recommendation_request: RecommendationRequest,
) -> None:
    """Test recommendation submission on successful response."""
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "recommendations": [
                {
                    "rank": 1,
                    "name": "Toscano",
                    "city": "Bangalore",
                    "area": "UB City",
                    "cuisine": ["Italian", "Continental"],
                    "rating": 4.6,
                    "votes": 1200,
                    "estimated_cost": 1800,
                    "budget_tier": "high",
                    "features": ["table_booking", "online_delivery"],
                    "highlights": ["romantic ambiance", "authentic pasta"],
                    "explanation": "Top-tier authentic Italian dining with romantic atmosphere.",
                }
            ],
            "summary": "Found 1 great dining option in Bangalore.",
            "count": 1,
            "relaxation": {
                "is_relaxed": False,
                "original_count": 1,
                "relaxed_count": 1,
                "relaxation_applied": [],
            },
            "ai_generated": True,
            "fallback_notice": None,
        }
        mock_post.return_value = mock_resp

        result, error = api_client.get_recommendations(sample_recommendation_request)
        assert error is None
        assert isinstance(result, RecommendationResponse)
        assert result.count == 1
        assert result.recommendations[0].name == "Toscano"
        assert result.ai_generated is True


def test_api_client_get_recommendations_validation_error(
    api_client: BackendAPIClient,
    sample_recommendation_request: RecommendationRequest,
) -> None:
    """Test recommendation submission on 422 Unprocessable Entity."""
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {
            "error_type": "ValidationError",
            "message": "Request validation failed",
            "details": {
                "validation_errors": [
                    {"field": "location", "message": "Location cannot be empty."},
                ]
            },
        }
        mock_post.return_value = mock_resp

        result, error = api_client.get_recommendations(sample_recommendation_request)
        assert result is None
        assert error is not None
        assert "Validation Error" in error
        assert "Location cannot be empty" in error


def test_api_client_get_recommendations_connect_error(
    api_client: BackendAPIClient,
    sample_recommendation_request: RecommendationRequest,
) -> None:
    """Test recommendation submission when connection fails."""
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        result, error = api_client.get_recommendations(sample_recommendation_request)
        assert result is None
        assert error is not None
        assert "Could not connect to backend server" in error


def test_api_client_get_recommendations_timeout(
    api_client: BackendAPIClient,
    sample_recommendation_request: RecommendationRequest,
) -> None:
    """Test recommendation submission timeout."""
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Timed out")):
        result, error = api_client.get_recommendations(sample_recommendation_request)
        assert result is None
        assert error is not None
        assert "timed out after" in error


def test_recommendation_request_construction() -> None:
    """Test constructing RecommendationRequest model with various UI combinations."""
    req = RecommendationRequest(
        location="Indiranagar, Bangalore",
        budget=BudgetBucket.MEDIUM,
        cuisine=["Italian", "Cafe"],
        min_rating=4.2,
        preferences=["romantic ambiance", "great coffee"],
        top_n=3,
    )
    assert req.location == "Indiranagar, Bangalore"
    assert req.budget == BudgetBucket.MEDIUM
    assert req.cuisine == ["Italian", "Cafe"]
    assert req.min_rating == 4.2
    assert req.top_n == 3


def test_restaurant_card_rendering() -> None:
    """Test rendering HTML for an individual restaurant recommendation card."""
    from app.models.recommendation import RecommendationItem
    from ui.components.card import build_restaurant_card_html

    item = RecommendationItem(
        rank=1,
        id="r1",
        name="Toscano",
        city="Bangalore",
        area="UB City",
        cuisine=["Italian", "Continental"],
        rating=4.6,
        estimated_cost=1800,
        features=["table_booking", "online_delivery"],
        highlights=["romantic ambiance", "authentic pasta"],
        explanation="Top-tier authentic Italian dining with romantic atmosphere.",
    )

    card_html = build_restaurant_card_html(item)
    assert "restaurant-card" in card_html
    assert "Toscano" in card_html
    assert "UB City, Bangalore" in card_html
    assert "★ 4.6" in card_html
    assert "₹1,800 for two" in card_html
    assert "Italian" in card_html
    assert "Taste Match" in card_html
    assert "Neural Reasoning" in card_html
    assert "Top-tier authentic Italian" in card_html


def test_restaurant_card_escapes_html_in_explanation() -> None:
    """Test that dynamic LLM text is HTML-escaped to prevent broken markup."""
    from app.models.recommendation import RecommendationItem
    from ui.components.card import build_restaurant_card_html

    item = RecommendationItem(
        rank=1,
        id="r2",
        name="Test <script>",
        city="Bangalore",
        area=None,
        cuisine=["Cafe"],
        rating=4.0,
        estimated_cost=400,
        features=[],
        highlights=[],
        explanation='Uses <strong> tags & "quotes" safely.',
    )

    card_html = build_restaurant_card_html(item)
    assert "<script>" not in card_html
    assert "&lt;strong&gt;" in card_html
    assert "Test &lt;script&gt;" in card_html

