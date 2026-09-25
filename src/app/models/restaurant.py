"""Restaurant Data Models.

Defines the canonical restaurant entity, budget categorization, and candidate
representations used across ingestion, repository storage, and LLM shortlisting.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BudgetBucket(str, Enum):
    """Categorical budget classification derived from cost for two."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ANY = "any"


class Restaurant(BaseModel):
    """Canonical normalized restaurant entity stored in Parquet/SQLite."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str = Field(..., description="Stable deterministic unique identifier.")
    name: str = Field(..., min_length=1, description="Restaurant name.")
    city: str = Field(..., min_length=1, description="Normalized city name (e.g. bangalore).")
    area: str | None = Field(default=None, description="Sub-locality or neighborhood.")
    cuisines: list[str] = Field(
        default_factory=list,
        min_length=1,
        description="List of cuisines offered.",
    )
    cost_for_two: int = Field(
        ...,
        ge=0,
        description="Estimated dining cost for two people in local currency (INR).",
    )
    budget_bucket: BudgetBucket = Field(
        ...,
        description="Classified budget tier (low, medium, high).",
    )
    rating: float = Field(
        ...,
        ge=0.0,
        le=5.0,
        description="Normalized aggregate dining rating on a 0.0 to 5.0 scale.",
    )
    votes: int = Field(
        default=0,
        ge=0,
        description="Total number of customer ratings/reviews recorded.",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Notable features (e.g. online_delivery, table_booking).",
    )
    address: str | None = Field(
        default=None,
        description="Full physical address or street details if available.",
    )

    @field_validator("name", "city")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class RestaurantCandidate(BaseModel):
    """Grounded candidate representation serialized into LLM prompts."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique restaurant ID.")
    name: str = Field(..., description="Restaurant name.")
    area: str | None = Field(default=None, description="Neighborhood location.")
    cuisines: list[str] = Field(default_factory=list, description="Cuisines offered.")
    cost_for_two: int = Field(..., description="Approximate cost for two.")
    rating: float = Field(..., description="Rating (0.0 - 5.0).")
    votes: int = Field(default=0, description="Customer votes.")
    features: list[str] = Field(default_factory=list, description="Available features.")

    @classmethod
    def from_restaurant(cls, restaurant: Restaurant) -> "RestaurantCandidate":
        """Convert a canonical Restaurant into a candidate for LLM context."""
        return cls(
            id=restaurant.id,
            name=restaurant.name,
            area=restaurant.area,
            cuisines=restaurant.cuisines,
            cost_for_two=restaurant.cost_for_two,
            rating=restaurant.rating,
            votes=restaurant.votes,
            features=restaurant.features,
        )

    def to_llm_dict(self) -> dict[str, Any]:
        """Compact dictionary format for prompt serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "area": self.area or "N/A",
            "cuisines": self.cuisines,
            "cost_for_two": self.cost_for_two,
            "rating": self.rating,
            "votes": self.votes,
            "features": self.features,
        }
