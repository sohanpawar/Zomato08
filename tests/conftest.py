"""Pytest Configuration and Shared Test Fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.models.restaurant import BudgetBucket, Restaurant


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Provides isolated settings with temporary data directories."""
    return Settings(
        app_env="test",
        debug=True,
        log_level="DEBUG",
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        sqlite_path=tmp_path / "processed" / "test_restaurants.db",
        parquet_path=tmp_path / "processed" / "test_restaurants.parquet",
        llm_provider="mock",
        llm_model="mock-recommender",
    )


@pytest.fixture
def sample_restaurants_data() -> list[dict[str, Any]]:
    """Loads sample raw JSON restaurant fixtures."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_restaurants.json"
    with open(fixture_path, encoding="utf-8") as f:
        data: list[dict[str, Any]] = json.load(f)
        return data


@pytest.fixture
def sample_restaurant_models(sample_restaurants_data: list[dict[str, Any]]) -> list[Restaurant]:
    """Provides validated Restaurant domain model fixtures."""
    return [
        Restaurant(
            id=item["id"],
            name=item["name"],
            city=item["city"],
            area=item.get("area"),
            cuisines=item["cuisines"],
            cost_for_two=item["cost_for_two"],
            budget_bucket=BudgetBucket(item["budget_bucket"]),
            rating=item["rating"],
            votes=item.get("votes", 0),
            features=item.get("features", []),
            address=item.get("address"),
        )
        for item in sample_restaurants_data
    ]
