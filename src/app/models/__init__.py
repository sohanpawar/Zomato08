"""Domain Models Package."""

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
from app.models.restaurant import (
    BudgetBucket,
    Restaurant,
    RestaurantCandidate,
)

__all__ = [
    "BudgetBucket",
    "HealthResponse",
    "LLMSelectedRecommendation",
    "LLMStructuredOutput",
    "MetadataResponse",
    "RecommendationItem",
    "RecommendationRequest",
    "RecommendationResponse",
    "RelaxationDetails",
    "Restaurant",
    "RestaurantCandidate",
]
