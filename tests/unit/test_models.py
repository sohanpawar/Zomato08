"""Unit tests for domain models, validation rules, and schema mappings."""

import pytest
from pydantic import ValidationError

from app.models.restaurant import BudgetBucket, Restaurant, RestaurantCandidate
from app.models.recommendation import (
    HealthResponse,
    LLMSelectedRecommendation,
    LLMStructuredOutput,
    MetadataResponse,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
    RelaxationDetails,
)


def test_restaurant_model_valid() -> None:
    """Verify Restaurant domain model validation."""
    rest = Restaurant(
        id="rest_123",
        name="Toscano",
        city="bangalore",
        area="Koramangala",
        cuisines=["Italian", "Continental"],
        cost_for_two=1500,
        budget_bucket=BudgetBucket.HIGH,
        rating=4.5,
        votes=120,
        features=["online_delivery"],
    )
    assert rest.id == "rest_123"
    assert rest.name == "Toscano"
    assert rest.cost_for_two == 1500
    assert rest.budget_bucket == BudgetBucket.HIGH
    assert rest.rating == 4.5


def test_restaurant_model_invalid_rating() -> None:
    """Verify rating boundary rejection (< 0 or > 5)."""
    with pytest.raises(ValidationError):
        Restaurant(
            id="rest_1",
            name="Test",
            city="bangalore",
            cuisines=["Italian"],
            cost_for_two=500,
            budget_bucket=BudgetBucket.LOW,
            rating=5.5,  # Out of bounds
        )


def test_restaurant_candidate_from_restaurant() -> None:
    """Verify RestaurantCandidate conversion and dictionary formatting."""
    rest = Restaurant(
        id="rest_blr_001",
        name="Taaza Thindi",
        city="bangalore",
        area="Jayanagar",
        cuisines=["South Indian"],
        cost_for_two=200,
        budget_bucket=BudgetBucket.LOW,
        rating=4.7,
        votes=5000,
        features=["quick_service"],
    )
    candidate = RestaurantCandidate.from_restaurant(rest)
    assert candidate.id == rest.id
    assert candidate.name == rest.name
    llm_dict = candidate.to_llm_dict()
    assert llm_dict["id"] == "rest_blr_001"
    assert llm_dict["area"] == "Jayanagar"
    assert llm_dict["cost_for_two"] == 200


def test_recommendation_request_valid() -> None:
    """Verify RecommendationRequest schema validation and whitespace trimming."""
    req = RecommendationRequest(
        location="  Bangalore  ",
        budget=BudgetBucket.MEDIUM,
        cuisine=["  Italian  ", "Chinese"],
        min_rating=4.0,
        preferences=["  family-friendly "],
        top_n=5,
    )
    assert req.location == "Bangalore"
    assert req.budget == BudgetBucket.MEDIUM
    assert req.cuisine == ["Italian", "Chinese"]
    assert req.min_rating == 4.0
    assert req.preferences == ["family-friendly"]
    assert req.top_n == 5


def test_recommendation_request_invalid_location_length() -> None:
    """Verify short location (< 2 chars) raises validation error."""
    with pytest.raises(ValidationError):
        RecommendationRequest(location="X")


def test_recommendation_request_invalid_top_n() -> None:
    """Verify top_n out of bounds is rejected."""
    with pytest.raises(ValidationError):
        RecommendationRequest(location="Delhi", top_n=0)
    with pytest.raises(ValidationError):
        RecommendationRequest(location="Delhi", top_n=25)


def test_llm_structured_output_schema() -> None:
    """Verify LLMStructuredOutput validation."""
    output = LLMStructuredOutput(
        recommendations=[
            LLMSelectedRecommendation(
                id="rest_blr_001",
                rank=1,
                explanation="Exemplary authentic pasta and romantic ambiance.",
                highlights=["Authentic Pasta", "Romantic"],
            )
        ],
        summary="Top Italian recommendations in Bangalore matching mid budget.",
    )
    assert len(output.recommendations) == 1
    assert output.recommendations[0].id == "rest_blr_001"
    assert output.recommendations[0].rank == 1


def test_recommendation_response_structure() -> None:
    """Verify final client RecommendationResponse assembly."""
    response = RecommendationResponse(
        query_echo={"location": "Bangalore", "budget": "medium"},
        count=1,
        recommendations=[
            RecommendationItem(
                rank=1,
                id="rest_blr_001",
                name="Toscano",
                city="Bangalore",
                area="Koramangala",
                cuisine=["Italian"],
                rating=4.6,
                estimated_cost=1600,
                features=["online_delivery"],
                explanation="Great atmosphere and high rating.",
                highlights=["Italian"],
            )
        ],
        summary="Here is your top recommendation.",
        relaxation=RelaxationDetails(is_relaxed=False),
        ai_generated=True,
    )
    assert response.count == 1
    assert response.ai_generated is True
    assert response.recommendations[0].name == "Toscano"


def test_health_response_schema() -> None:
    """Verify HealthResponse structure."""
    health = HealthResponse(
        status="healthy",
        database_available=True,
        total_restaurants=5000,
        version="0.1.0",
    )
    assert health.status == "healthy"
    assert health.database_available is True
    assert health.total_restaurants == 5000
