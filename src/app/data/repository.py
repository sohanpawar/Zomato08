"""Restaurant Data Repository Protocol and SQLite Implementation.

Provides high-performance, indexed candidate querying, parameterized filtering,
entity rehydration, and catalog metadata introspection.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from app.exceptions import RepositoryError
from app.logging import get_logger
from app.models.restaurant import BudgetBucket, Restaurant

logger = get_logger(__name__)


class RestaurantRepository(Protocol):
    """Abstract protocol for restaurant data retrieval."""

    def is_available(self) -> bool:
        """Check if the repository storage is accessible."""
        ...

    def get_by_id(self, restaurant_id: str) -> Restaurant | None:
        """Fetch a single restaurant by its unique ID."""
        ...

    def get_by_ids(self, restaurant_ids: list[str]) -> list[Restaurant]:
        """Fetch multiple restaurants preserving the requested order."""
        ...

    def find_candidates(
        self,
        location: str,
        budget: BudgetBucket = BudgetBucket.ANY,
        cuisines: list[str] | None = None,
        min_rating: float = 0.0,
        limit: int = 50,
    ) -> list[Restaurant]:
        """Query restaurants matching filter criteria."""
        ...

    def list_cities(self) -> list[str]:
        """List all distinct supported cities in alphabetical order."""
        ...

    def list_cuisines(self, city: str | None = None) -> list[str]:
        """List distinct cuisines available globally or in a specified city."""
        ...

    def count_total(self) -> int:
        """Return total count of restaurants in the catalog."""
        ...

    def get_catalog_stats(self) -> dict[str, Any]:
        """Return aggregated summary metrics of the dataset."""
        ...


class SQLiteRestaurantRepository:
    """SQLite implementation of RestaurantRepository with parameterized indexed queries."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Open a read-only or read-write connection to SQLite with WAL mode."""
        if not self.db_path.is_file():
            raise RepositoryError(
                f"SQLite database file not found at: {self.db_path}",
                error_code="DATABASE_NOT_FOUND",
                status_code=503,
                details={"db_path": str(self.db_path)},
            )

        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            return conn
        except sqlite3.Error as e:
            logger.error("Failed to connect to SQLite at %s: %s", self.db_path, str(e))
            raise RepositoryError(
                f"Database connection error: {e}",
                error_code="DATABASE_CONNECTION_ERROR",
                status_code=500,
                details={"db_path": str(self.db_path), "error": str(e)},
            ) from e

    def is_available(self) -> bool:
        """Check if the SQLite database exists and is queryable."""
        if not self.db_path.is_file():
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM restaurants LIMIT 1;")
                return True
        except Exception:
            return False

    def _row_to_entity(self, row: sqlite3.Row) -> Restaurant:
        """Convert a SQLite row into a canonical Restaurant domain entity."""
        cuisines = json.loads(row["cuisines"]) if row["cuisines"] else []
        features = json.loads(row["features"]) if row["features"] else []

        return Restaurant(
            id=row["id"],
            name=row["name"],
            city=row["city"],
            area=row["area"],
            cuisines=cuisines,
            cost_for_two=row["cost_for_two"],
            budget_bucket=BudgetBucket(row["budget_bucket"]),
            rating=float(row["rating"]),
            votes=int(row["votes"]),
            features=features,
            address=row["address"],
        )

    def get_by_id(self, restaurant_id: str) -> Restaurant | None:
        """Fetch a single restaurant by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM restaurants WHERE id = ? LIMIT 1;",
                (restaurant_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def get_by_ids(self, restaurant_ids: list[str]) -> list[Restaurant]:
        """Fetch multiple restaurants preserving the exact requested ID ordering."""
        if not restaurant_ids:
            return []

        placeholders = ",".join(["?"] * len(restaurant_ids))
        query = f"SELECT * FROM restaurants WHERE id IN ({placeholders});"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, restaurant_ids)
            rows = cursor.fetchall()

        entity_map = {row["id"]: self._row_to_entity(row) for row in rows}

        # Preserve the exact ordering from restaurant_ids parameter
        ordered: list[Restaurant] = []
        for rest_id in restaurant_ids:
            if rest_id in entity_map:
                ordered.append(entity_map[rest_id])

        return ordered

    def find_candidates(
        self,
        location: str,
        budget: BudgetBucket = BudgetBucket.ANY,
        cuisines: list[str] | None = None,
        min_rating: float = 0.0,
        limit: int = 50,
    ) -> list[Restaurant]:
        """Query restaurants matching filter criteria using parameterized SQL.

        Matching Logic:
            - location: Matches either normalized `city` (exact) OR `area` (contains).
            - budget: Exact match on `budget_bucket` unless `BudgetBucket.ANY`.
            - min_rating: `rating >= min_rating`.
            - cuisines: If specified, requires at least one cuisine match in `restaurant_cuisines`.
        """
        norm_loc = location.strip().lower()
        where_clauses: list[str] = []
        params: list[Any] = []

        # 1. Location constraint (city exact match, or area/address substring match)
        where_clauses.append(
            "(LOWER(r.city) = ? OR LOWER(COALESCE(r.area, '')) LIKE ? "
            "OR LOWER(COALESCE(r.address, '')) LIKE ?)"
        )
        params.extend([norm_loc, f"%{norm_loc}%", f"%{norm_loc}%"])

        # 2. Budget constraint
        if budget != BudgetBucket.ANY:
            where_clauses.append("r.budget_bucket = ?")
            params.append(budget.value)

        # 3. Minimum rating constraint
        if min_rating > 0.0:
            where_clauses.append("r.rating >= ?")
            params.append(round(min_rating, 2))

        # 4. Cuisine constraint (Set Intersection > 0)
        if cuisines:
            clean_cuisines = [c.strip().lower() for c in cuisines if c.strip()]
            if clean_cuisines:
                cuisine_placeholders = ",".join(["?"] * len(clean_cuisines))
                where_clauses.append(f"""
                    EXISTS (
                        SELECT 1 FROM restaurant_cuisines rc
                        WHERE rc.restaurant_id = r.id
                        AND LOWER(rc.cuisine) IN ({cuisine_placeholders})
                    )
                """)
                params.extend(clean_cuisines)

        # Assemble full query
        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT r.* FROM restaurants r
            WHERE {where_sql}
            ORDER BY r.rating DESC, r.votes DESC, r.cost_for_two ASC, r.id ASC
            LIMIT ?;
        """
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def list_cities(self) -> list[str]:
        """List all distinct normalized cities in the dataset."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT city FROM restaurants WHERE city IS NOT NULL ORDER BY city ASC;")
            return [row["city"] for row in cursor.fetchall()]

    def list_cuisines(self, city: str | None = None) -> list[str]:
        """List all distinct cuisines, optionally filtered by city."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if city:
                norm_city = city.strip().lower()
                query = """
                    SELECT DISTINCT rc.cuisine
                    FROM restaurant_cuisines rc
                    JOIN restaurants r ON rc.restaurant_id = r.id
                    WHERE LOWER(r.city) = ?
                    ORDER BY rc.cuisine ASC;
                """
                cursor.execute(query, (norm_city,))
            else:
                query = "SELECT DISTINCT cuisine FROM restaurant_cuisines ORDER BY cuisine ASC;"
                cursor.execute(query)

            return [row["cuisine"].title() for row in cursor.fetchall()]

    def count_total(self) -> int:
        """Return total count of restaurants in catalog."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM restaurants;")
            row = cursor.fetchone()
            return int(row["total"]) if row else 0

    def get_catalog_stats(self) -> dict[str, Any]:
        """Return aggregate summary metrics of the restaurant database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_count,
                    MIN(rating) AS min_rating,
                    MAX(rating) AS max_rating,
                    AVG(rating) AS avg_rating,
                    MIN(cost_for_two) AS min_cost,
                    MAX(cost_for_two) AS max_cost,
                    AVG(cost_for_two) AS avg_cost
                FROM restaurants;
            """)
            stats_row = cursor.fetchone()
            if not stats_row or stats_row["total_count"] == 0:
                return {
                    "total_count": 0,
                    "min_rating": 0.0,
                    "max_rating": 0.0,
                    "avg_rating": 0.0,
                    "min_cost": 0,
                    "max_cost": 0,
                    "avg_cost": 0.0,
                }

            return {
                "total_count": int(stats_row["total_count"]),
                "min_rating": round(float(stats_row["min_rating"] or 0.0), 2),
                "max_rating": round(float(stats_row["max_rating"] or 0.0), 2),
                "avg_rating": round(float(stats_row["avg_rating"] or 0.0), 2),
                "min_cost": int(stats_row["min_cost"] or 0),
                "max_cost": int(stats_row["max_cost"] or 0),
                "avg_cost": round(float(stats_row["avg_cost"] or 0.0), 2),
            }
