"""Database Schema, SQLite Storage, and Parquet Serialization.

Provides robust database initialization, indexed relational schema creation,
batch insertions, and Parquet persistence for the restaurant recommendation catalog.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from app.logging import get_logger
from app.models.restaurant import BudgetBucket, Restaurant

logger = get_logger(__name__)


SCHEMA_SQL = """
-- Core restaurants table
CREATE TABLE IF NOT EXISTS restaurants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    area TEXT,
    cuisines TEXT NOT NULL,          -- Stored as JSON array string
    cost_for_two INTEGER NOT NULL,
    budget_bucket TEXT NOT NULL,
    rating REAL NOT NULL,
    votes INTEGER NOT NULL DEFAULT 0,
    features TEXT NOT NULL,          -- Stored as JSON array string
    address TEXT
);

-- Normalized cuisine lookup table for fast indexed searches
CREATE TABLE IF NOT EXISTS restaurant_cuisines (
    restaurant_id TEXT NOT NULL,
    cuisine TEXT NOT NULL,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE,
    PRIMARY KEY (restaurant_id, cuisine)
);

-- Indexes for fast query filtering and sorting
CREATE INDEX IF NOT EXISTS idx_restaurants_city ON restaurants(city);
CREATE INDEX IF NOT EXISTS idx_restaurants_area ON restaurants(area);
CREATE INDEX IF NOT EXISTS idx_restaurants_budget ON restaurants(budget_bucket);
CREATE INDEX IF NOT EXISTS idx_restaurants_rating ON restaurants(rating DESC);
CREATE INDEX IF NOT EXISTS idx_restaurants_city_budget ON restaurants(city, budget_bucket);
CREATE INDEX IF NOT EXISTS idx_restaurant_cuisines_cuisine ON restaurant_cuisines(cuisine);
CREATE INDEX IF NOT EXISTS idx_restaurant_cuisines_rest_id ON restaurant_cuisines(restaurant_id);
"""


def init_sqlite_database(db_path: Path | str) -> sqlite3.Connection:
    """Initialize SQLite database with schema and WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        sqlite3.Connection: Active connection to the initialized database.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for high concurrency read performance
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    # Execute schema creation
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    logger.debug("Initialized SQLite database schema at: %s", path)
    return conn


def save_restaurants_to_sqlite(
    restaurants: list[Restaurant],
    db_path: Path | str,
    batch_size: int = 1000,
) -> int:
    """Save a list of canonical Restaurant entities into SQLite.

    Replaces existing data with an atomic transaction.

    Args:
        restaurants: List of Restaurant models to insert.
        db_path: Path to target SQLite database.
        batch_size: Batch size for execute_many inserts.

    Returns:
        int: Count of restaurants inserted.
    """
    conn = init_sqlite_database(db_path)

    try:
        with conn:
            # Clear existing data atomically
            conn.execute("DELETE FROM restaurant_cuisines;")
            conn.execute("DELETE FROM restaurants;")

            restaurant_rows: list[tuple[Any, ...]] = []
            cuisine_rows: list[tuple[str, str]] = []

            for r in restaurants:
                restaurant_rows.append((
                    r.id,
                    r.name,
                    r.city,
                    r.area,
                    json.dumps(r.cuisines),
                    r.cost_for_two,
                    r.budget_bucket.value,
                    r.rating,
                    r.votes,
                    json.dumps(r.features),
                    r.address,
                ))

                for cuisine in r.cuisines:
                    cuisine_rows.append((r.id, cuisine.strip().lower()))

            # Insert restaurants in batches
            insert_restaurant_sql = """
            INSERT INTO restaurants (
                id, name, city, area, cuisines, cost_for_two,
                budget_bucket, rating, votes, features, address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """

            for i in range(0, len(restaurant_rows), batch_size):
                batch = restaurant_rows[i : i + batch_size]
                conn.executemany(insert_restaurant_sql, batch)

            # Insert cuisines lookup
            insert_cuisine_sql = """
            INSERT OR IGNORE INTO restaurant_cuisines (restaurant_id, cuisine)
            VALUES (?, ?);
            """

            for i in range(0, len(cuisine_rows), batch_size):
                c_batch = cuisine_rows[i : i + batch_size]
                conn.executemany(insert_cuisine_sql, c_batch)

        logger.info(
            "Successfully inserted %d restaurants into SQLite at: %s",
            len(restaurants),
            db_path,
        )
        return len(restaurants)
    finally:
        conn.close()


def save_restaurants_to_parquet(
    restaurants: list[Restaurant],
    parquet_path: Path | str,
) -> None:
    """Serialize a list of Restaurant domain models to an Apache Parquet file.

    Args:
        restaurants: List of Restaurant models.
        parquet_path: Target Parquet file destination.
    """
    path = Path(parquet_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = [
        {
            "id": r.id,
            "name": r.name,
            "city": r.city,
            "area": r.area,
            "cuisines": r.cuisines,
            "cost_for_two": r.cost_for_two,
            "budget_bucket": r.budget_bucket.value,
            "rating": r.rating,
            "votes": r.votes,
            "features": r.features,
            "address": r.address,
        }
        for r in restaurants
    ]

    df = pd.DataFrame(records)
    df.to_parquet(path, engine="pyarrow", index=False)
    logger.info("Saved %d records to Parquet at: %s", len(restaurants), path)


def load_restaurants_from_sqlite(db_path: Path | str) -> list[Restaurant]:
    """Load all restaurants from SQLite database into domain models."""
    path = Path(db_path)
    if not path.is_file():
        return []

    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM restaurants ORDER BY rating DESC, votes DESC;")
        rows = cursor.fetchall()

        restaurants: list[Restaurant] = []
        for row in rows:
            cuisines_list = json.loads(row["cuisines"])
            features_list = json.loads(row["features"])

            rest = Restaurant(
                id=row["id"],
                name=row["name"],
                city=row["city"],
                area=row["area"],
                cuisines=cuisines_list,
                cost_for_two=row["cost_for_two"],
                budget_bucket=BudgetBucket(row["budget_bucket"]),
                rating=row["rating"],
                votes=row["votes"],
                features=features_list,
                address=row["address"],
            )
            restaurants.append(rest)

        return restaurants
    finally:
        conn.close()
