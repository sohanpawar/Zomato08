"""Unit and Integration Tests for Data Ingestion, Cleaning, and Storage."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.data.storage import (
    init_sqlite_database,
    load_restaurants_from_sqlite,
    save_restaurants_to_parquet,
    save_restaurants_to_sqlite,
)
from app.ingestion.cleaner import (
    deduplicate_restaurants,
    derive_budget_bucket,
    extract_features,
    generate_restaurant_id,
    normalize_raw_record,
    parse_cost,
    parse_cuisines,
    parse_rating,
)
from app.ingestion.pipeline import IngestionPipeline
from app.models.restaurant import BudgetBucket, Restaurant


# ==============================================================================
# 1. Cleaner & Normalizer Unit Tests
# ==============================================================================


def test_parse_rating_valid_cases() -> None:
    """Verify rating parser handles standard scales, slash-fives, and comma decimals."""
    assert parse_rating("4.1/5") == 4.1
    assert parse_rating("4.5 / 5") == 4.5
    assert parse_rating("4.0") == 4.0
    assert parse_rating("3,8 /5") == 3.8
    assert parse_rating(4.2) == 4.2
    assert parse_rating("5.0/5") == 5.0
    assert parse_rating("0.0/5") == 0.0


def test_parse_rating_invalid_and_edge_cases() -> None:
    """Verify unrated tags, missing values, and out-of-bounds ratings return None."""
    assert parse_rating("NEW") is None
    assert parse_rating("new") is None
    assert parse_rating("-") is None
    assert parse_rating("") is None
    assert parse_rating(None) is None
    assert parse_rating("NAN") is None
    assert parse_rating("6.5/5") is None  # Out of bounds
    assert parse_rating("-1.0/5") is None  # Negative


def test_parse_cost_valid_cases() -> None:
    """Verify cost parser cleans commas, spaces, currency symbols, and numeric floats."""
    assert parse_cost("1,200") == 1200
    assert parse_cost("1 500") == 1500
    assert parse_cost("₹800") == 800
    assert parse_cost("Rs. 450") == 450
    assert parse_cost("INR 3000") == 3000
    assert parse_cost(600) == 600
    assert parse_cost(750.0) == 750


def test_parse_cost_invalid_and_edge_cases() -> None:
    """Verify zero, negative, missing, and non-numeric costs return None."""
    assert parse_cost("0") is None
    assert parse_cost(0) is None
    assert parse_cost("") is None
    assert parse_cost(None) is None
    assert parse_cost("-") is None
    assert parse_cost("N/A") is None


def test_parse_cuisines_delimiters_and_casing() -> None:
    """Verify cuisine parser splits on commas, semicolons, slashes, and title-cases."""
    result = parse_cuisines("north indian, chinese; continental / desserts")
    assert result == ["North Indian", "Chinese", "Continental", "Desserts"]

    single = parse_cuisines("italian")
    assert single == ["Italian"]

    empty = parse_cuisines("")
    assert empty == []

    none_val = parse_cuisines(None)
    assert none_val == []


def test_derive_budget_bucket_thresholds() -> None:
    """Verify budget tier boundaries for INR pricing."""
    # Low: <= 500
    assert derive_budget_bucket(200) == BudgetBucket.LOW
    assert derive_budget_bucket(500) == BudgetBucket.LOW

    # Medium: 501 - 1200
    assert derive_budget_bucket(501) == BudgetBucket.MEDIUM
    assert derive_budget_bucket(800) == BudgetBucket.MEDIUM
    assert derive_budget_bucket(1200) == BudgetBucket.MEDIUM

    # High: > 1200
    assert derive_budget_bucket(1201) == BudgetBucket.HIGH
    assert derive_budget_bucket(2500) == BudgetBucket.HIGH


def test_extract_features_from_raw() -> None:
    """Verify feature tags extraction from online_order, book_table, and rest_type."""
    raw_row = {
        "online_order": "Yes",
        "book_table": "Yes",
        "rest_type": "Casual Dining, Wine Bar",
        "listed_in(type)": "Dine-out",
    }
    features = extract_features(raw_row)
    assert "online_delivery" in features
    assert "table_booking" in features
    assert "casual_dining" in features
    assert "wine_bar" in features
    assert "dine_out" in features


def test_generate_restaurant_id_stability() -> None:
    """Verify deterministic ID generation produces consistent IDs."""
    id1 = generate_restaurant_id("Toscano", "bangalore", "Koramangala", "Forum Mall")
    id2 = generate_restaurant_id("toscano", "Bangalore", "koramangala", "Forum Mall")
    id3 = generate_restaurant_id("Different", "bangalore", "Koramangala", "Forum Mall")

    assert id1 == id2
    assert id1.startswith("rest_")
    assert id1 != id3


def test_normalize_raw_record_success() -> None:
    """Verify end-to-end normalization of a valid raw dictionary record."""
    raw = {
        "name": "Taaza Thindi",
        "rate": "4.7 /5",
        "approx_cost(for two people)": "200",
        "cuisines": "South Indian, Fast Food",
        "location": "Jayanagar",
        "votes": "5400",
        "online_order": "Yes",
        "address": "4th Block, Jayanagar",
    }
    rest, drop_reason = normalize_raw_record(raw)
    assert drop_reason is None
    assert rest is not None
    assert rest.name == "Taaza Thindi"
    assert rest.rating == 4.7
    assert rest.cost_for_two == 200
    assert rest.budget_bucket == BudgetBucket.LOW
    assert rest.cuisines == ["South Indian", "Fast Food"]
    assert rest.votes == 5400
    assert "online_delivery" in rest.features


def test_normalize_raw_record_drop_reasons() -> None:
    """Verify dropped records produce specific, measurable drop reasons."""
    # Missing name
    r1, reason1 = normalize_raw_record({"rate": "4.0/5", "approx_cost(for two people)": "500", "cuisines": "Italian"})
    assert r1 is None
    assert reason1 == "missing_name"

    # Unrated / NEW
    r2, reason2 = normalize_raw_record({"name": "Spot", "rate": "NEW", "approx_cost(for two people)": "500", "cuisines": "Italian"})
    assert r2 is None
    assert reason2 == "invalid_or_missing_rating"

    # Missing cost
    r3, reason3 = normalize_raw_record({"name": "Spot", "rate": "4.2/5", "approx_cost(for two people)": None, "cuisines": "Italian"})
    assert r3 is None
    assert reason3 == "invalid_or_missing_cost"


def test_deduplicate_restaurants_preserves_highest_votes() -> None:
    """Verify deduplication keeps the listing with the most votes."""
    r1 = Restaurant(
        id="rest_1",
        name="Toscano",
        city="bangalore",
        area="Koramangala",
        cuisines=["Italian"],
        cost_for_two=1600,
        budget_bucket=BudgetBucket.HIGH,
        rating=4.5,
        votes=1000,
        address="Forum Mall",
    )
    r2 = Restaurant(
        id="rest_1",
        name="Toscano",
        city="bangalore",
        area="Koramangala",
        cuisines=["Italian"],
        cost_for_two=1600,
        budget_bucket=BudgetBucket.HIGH,
        rating=4.5,
        votes=2500,  # Higher votes
        address="Forum Mall",
    )
    deduped, removed_count = deduplicate_restaurants([r1, r2])
    assert removed_count == 1
    assert len(deduped) == 1
    assert deduped[0].votes == 2500


# ==============================================================================
# 2. SQLite & Parquet Storage Tests
# ==============================================================================


def test_sqlite_storage_lifecycle(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify SQLite database initialization, table indexes, insertion, and query loading."""
    db_path = tmp_path / "test_lifecycle.db"

    # 1. Initialize schema
    conn = init_sqlite_database(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "restaurants" in tables
    assert "restaurant_cuisines" in tables
    conn.close()

    # 2. Save restaurants
    count = save_restaurants_to_sqlite(sample_restaurant_models, db_path)
    assert count == len(sample_restaurant_models)

    # 3. Read back from SQLite
    loaded = load_restaurants_from_sqlite(db_path)
    assert len(loaded) == len(sample_restaurant_models)
    assert loaded[0].name == sample_restaurant_models[0].name


def test_parquet_storage_lifecycle(tmp_path: Path, sample_restaurant_models: list[Restaurant]) -> None:
    """Verify Parquet file writing and reading."""
    import pandas as pd

    parquet_path = tmp_path / "test_restaurants.parquet"
    save_restaurants_to_parquet(sample_restaurant_models, parquet_path)

    assert parquet_path.is_file()
    df = pd.read_parquet(parquet_path)
    assert len(df) == len(sample_restaurant_models)
    assert "cost_for_two" in df.columns
    assert "budget_bucket" in df.columns


# ==============================================================================
# 3. End-to-End Ingestion Pipeline Integration Test
# ==============================================================================


def test_ingestion_pipeline_run_with_fixture(tmp_path: Path) -> None:
    """Verify full IngestionPipeline execution using the raw HF sample fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_raw_hf_zomato.json"

    settings = Settings(
        app_env="test",
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        sqlite_path=tmp_path / "processed" / "restaurants.db",
        parquet_path=tmp_path / "processed" / "restaurants.parquet",
    )

    pipeline = IngestionPipeline(settings=settings)
    report = pipeline.run(local_file=fixture_path, force_reload=True)

    # Assert report statistics
    assert report.total_raw_rows == 9
    # In fixture: 9 rows total
    # - 1 duplicate (Toscano delivery listing)
    # - 4 invalid (NEW, -, missing cost, missing name)
    # Valid clean rows = 4 (Jigger Thindi, Toscano, Punjabi Rasoi, Veena Stores)
    assert report.clean_deduped_rows == 4
    assert report.duplicates_removed == 1
    assert report.dropped_rows == 4
    assert "invalid_or_missing_rating" in report.drop_reasons
    assert "invalid_or_missing_cost" in report.drop_reasons
    assert "missing_name" in report.drop_reasons

    # Assert artifacts created
    assert settings.sqlite_path.is_file()
    assert settings.parquet_path.is_file()

    # Verify SQLite content
    loaded = load_restaurants_from_sqlite(settings.sqlite_path)
    assert len(loaded) == 4
    names = {r.name for r in loaded}
    assert "Toscano" in names
    assert "Jigger Thindi" in names
    assert "Punjabi Rasoi" in names
    assert "Veena Stores" in names

    # Verify metadata JSON report written
    report_json = settings.processed_data_dir / "ingestion_report.json"
    assert report_json.is_file()
    with open(report_json, encoding="utf-8") as f:
        data = json.load(f)
        assert data["clean_deduped_rows"] == 4
