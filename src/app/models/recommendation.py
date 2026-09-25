"""Recommendation Request and Response Schemas.

Defines Pydantic models for user preference validation, LLM structured outputs,
metadata introspection, and finalized API responses.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.restaurant import BudgetBucket


class RecommendationRequest(BaseModel):
    """User input criteria for restaurant recommendation."""

    model_config = ConfigDict(extra="forbid")

    location: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Target city or area name (e.g., Bangalore, Koramangala).",
    )
    budget: BudgetBucket = Field(
        default=BudgetBucket.ANY,
        description="Budget tier preference: low, medium, high, or any.",
    )
    cuisine: list[str] | None = Field(
        default=None,
        max_length=10,
        description="List of preferred cuisines (e.g., ['Italian', 'Chinese']).",
    )
    min_rating: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        description="Minimum restaurant rating threshold (0.0 to 5.0).",
    )
    preferences: list[str] | None = Field(
        default=None,
        max_length=5,
        description="Additional preferences (e.g. ['family-friendly', 'quick service']).",
    )
    top_n: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of recommendations requested (1 to 20).",
    )

    @field_validator("location")
    @classmethod
    def sanitize_location(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Location must be at least 2 characters long.")
        return cleaned

    @field_validator("cuisine", "preferences")
    @classmethod
    def sanitize_string_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [item.strip() for item in v if item.strip()]
        return cleaned if cleaned else None


# ==============================================================================
# LLM Structured Output Models (Enforced in Prompt)
# ==============================================================================


class LLMSelectedRecommendation(BaseModel):
    """Single restaurant selection returned directly by the LLM."""

    id: str = Field(..., description="The exact ID of the candidate chosen from shortlist.")
    rank: int = Field(..., ge=1, description="Ranking position (1-based index).")
    explanation: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="1-2 sentence grounded justification matching user preferences.",
    )
    highlights: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Short bullet highlights (e.g. ['Budget-Friendly', 'Authentic Pasta']).",
    )


class LLMStructuredOutput(BaseModel):
    """Complete structured JSON schema expected from LLM completion."""

    recommendations: list[LLMSelectedRecommendation] = Field(
        default_factory=list,
        description="Ranked list of recommendations chosen strictly from candidate shortlist.",
    )
    summary: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Overall summary of the recommendation set.",
    )


# ==============================================================================
# Final Client-Facing API Response Models
# ==============================================================================


class RecommendationItem(BaseModel):
    """Fully hydrated recommendation card returned to client."""

    rank: int = Field(..., description="Rank position (1 to N).")
    id: str = Field(..., description="Restaurant identifier.")
    name: str = Field(..., description="Restaurant name.")
    city: str = Field(..., description="City location.")
    area: str | None = Field(default=None, description="Locality or neighborhood.")
    cuisine: list[str] = Field(default_factory=list, description="Cuisines offered.")
    rating: float = Field(..., description="Aggregate rating (0.0 to 5.0).")
    estimated_cost: int = Field(..., description="Estimated cost for two in local currency.")
    features: list[str] = Field(default_factory=list, description="Special features or tags.")
    explanation: str = Field(..., description="AI or heuristic explanation.")
    highlights: list[str] = Field(default_factory=list, description="Key recommendation tags.")


class RelaxationDetails(BaseModel):
    """Audit details when query constraints were relaxed to find candidates."""

    is_relaxed: bool = Field(default=False, description="Whether constraint relaxation occurred.")
    relaxation_applied: list[str] = Field(
        default_factory=list,
        description="Step-by-step descriptions of constraints relaxed.",
    )
    effective_query: dict[str, Any] = Field(
        default_factory=dict,
        description="The actual query criteria used after relaxation.",
    )


class RecommendationResponse(BaseModel):
    """Full payload returned by POST /recommend."""

    query_echo: dict[str, Any] = Field(..., description="Original user query parameters.")
    count: int = Field(..., description="Number of recommendations returned.")
    recommendations: list[RecommendationItem] = Field(
        default_factory=list,
        description="Ranked recommendation items.",
    )
    summary: str = Field(..., description="Overall summary of recommendations.")
    relaxation: RelaxationDetails | None = Field(
        default=None,
        description="Constraint relaxation audit if applicable.",
    )
    ai_generated: bool = Field(
        default=True,
        description="True if ranked/explained by LLM; False if using heuristic fallback.",
    )
    fallback_notice: str | None = Field(
        default=None,
        description="User-facing notice if heuristic fallback was used.",
    )


class MetadataResponse(BaseModel):
    """Payload returned by GET /meta for UI dropdown hydration."""

    cities: list[str] = Field(default_factory=list, description="Supported normalized cities.")
    cuisines: list[str] = Field(default_factory=list, description="Available cuisine options.")
    budget_options: list[str] = Field(
        default=["low", "medium", "high", "any"],
        description="Supported budget tiers.",
    )
    min_rating_range: tuple[float, float] = Field(
        default=(0.0, 5.0),
        description="Allowed rating bounds.",
    )
    max_top_n: int = Field(default=20, description="Max allowed recommendations per request.")
    total_restaurants: int = Field(default=0, description="Total restaurants in catalog.")


class HealthResponse(BaseModel):
    """Payload returned by GET /health."""

    status: str = Field(default="healthy", description="Application status.")
    database_available: bool = Field(..., description="Whether restaurant database is accessible.")
    total_restaurants: int = Field(default=0, description="Count of stored restaurants.")
    version: str = Field(default="0.1.0", description="Application version.")
