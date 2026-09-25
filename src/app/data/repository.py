"""Restaurant Data Repository Protocol and SQLite Implementation.

Provides high-performance, indexed candidate querying, parameterized filtering,
entity rehydration, and catalog metadata introspection.
"""

from collections.abc import Generator
from contextlib import contextmanager
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
        self._memory_conn: sqlite3.Connection | None = None

    def _resolve_db_path(self) -> Path | None:
        """Find the SQLite database file across potential serverless and container locations."""
        candidates = [
            self.db_path,
            Path.cwd() / self.db_path,
            Path(__file__).resolve().parent / "restaurants.db",
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "processed" / "restaurants.db",
            Path(__file__).resolve().parent.parent.parent.parent / "src" / "app" / "data" / "restaurants.db",
            Path("/var/task") / self.db_path,
            Path("/var/task/data/processed/restaurants.db"),
            Path("/var/task/src/app/data/restaurants.db"),
            Path("/tmp/restaurants.db"),
        ]
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate.resolve()
            except Exception:
                continue
        return None

    def _init_in_memory_fallback(self) -> sqlite3.Connection:
        """Initialize and populate an in-memory SQLite database from bundled JSON fixtures."""
        if self._memory_conn is not None:
            return self._memory_conn

        logger.info("Initializing resilient in-memory SQLite catalog...")
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row

        schema_sql = """
        CREATE TABLE IF NOT EXISTS restaurants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            area TEXT,
            cuisines TEXT NOT NULL,
            cost_for_two INTEGER NOT NULL,
            budget_bucket TEXT NOT NULL,
            rating REAL NOT NULL,
            votes INTEGER NOT NULL DEFAULT 0,
            features TEXT NOT NULL,
            address TEXT
        );
        CREATE TABLE IF NOT EXISTS restaurant_cuisines (
            restaurant_id TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            PRIMARY KEY (restaurant_id, cuisine)
        );
        CREATE INDEX IF NOT EXISTS idx_r_city ON restaurants(city);
        CREATE INDEX IF NOT EXISTS idx_r_area ON restaurants(area);
        CREATE INDEX IF NOT EXISTS idx_r_budget ON restaurants(budget_bucket);
        CREATE INDEX IF NOT EXISTS idx_r_rating ON restaurants(rating DESC);
        CREATE INDEX IF NOT EXISTS idx_rc_cuisine ON restaurant_cuisines(cuisine);
        CREATE INDEX IF NOT EXISTS idx_rc_rest_id ON restaurant_cuisines(restaurant_id);
        """
        conn.executescript(schema_sql)

        # Look for fallback JSON data files
        json_candidates = [
            Path(__file__).resolve().parent / "fallback_restaurants.json",
            Path(__file__).resolve().parent.parent.parent.parent / "src" / "app" / "data" / "fallback_restaurants.json",
            Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "sample_restaurants.json",
            Path("/var/task/src/app/data/fallback_restaurants.json"),
            Path("/var/task/tests/fixtures/sample_restaurants.json"),
        ]

        restaurants_loaded = 0
        for json_path in json_candidates:
            if json_path.is_file():
                try:
                    with open(json_path, encoding="utf-8") as f:
                        records = json.load(f)
                    for rec in records:
                        c_list = rec.get("cuisines", [])
                        f_list = rec.get("features", [])
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO restaurants (
                                id, name, city, area, cuisines, cost_for_two,
                                budget_bucket, rating, votes, features, address
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                rec["id"],
                                rec["name"],
                                rec.get("city", "bangalore").lower(),
                                rec.get("area", ""),
                                json.dumps(c_list),
                                int(rec.get("cost_for_two", 500)),
                                rec.get("budget_bucket", "medium"),
                                float(rec.get("rating", 4.0)),
                                int(rec.get("votes", 100)),
                                json.dumps(f_list),
                                rec.get("address", ""),
                            ),
                        )
                        for c in c_list:
                            conn.execute(
                                "INSERT OR IGNORE INTO restaurant_cuisines (restaurant_id, cuisine) VALUES (?, ?);",
                                (rec["id"], c.strip().lower()),
                            )
                        restaurants_loaded += 1
                    conn.commit()
                    logger.info("Loaded %d fallback restaurants into in-memory database from %s", restaurants_loaded, json_path)
                    break
                except Exception as ex:
                    logger.warning("Failed loading fallback JSON from %s: %s", json_path, ex)

        self._memory_conn = conn
        return self._memory_conn

    def _get_connection(self) -> sqlite3.Connection:
        """Open a read-only connection to SQLite, falling back to resilient in-memory database."""
        resolved = self._resolve_db_path()

        if resolved is not None:
            # 1. Attempt Read-Only URI connection (safe on read-only serverless/Vercel filesystems)
            try:
                uri_path = f"file:{resolved}?mode=ro"
                conn = sqlite3.connect(
                    uri_path,
                    uri=True,
                    timeout=30.0,
                    check_same_thread=False,
                )
                conn.row_factory = sqlite3.Row
                try:
                    conn.execute("PRAGMA query_only = ON;")
                except Exception:
                    pass
                return conn
            except sqlite3.Error as e:
                logger.debug("Read-only URI connection failed for %s (%s). Attempting standard connection.", resolved, e)

            # 2. Attempt Standard SQLite connection
            try:
                conn = sqlite3.connect(
                    str(resolved),
                    timeout=30.0,
                    check_same_thread=False,
                )
                conn.row_factory = sqlite3.Row
                try:
                    conn.execute("PRAGMA busy_timeout=5000;")
                except Exception:
                    pass
                return conn
            except sqlite3.Error as e:
                logger.warning("Standard SQLite connection failed for %s: %s. Falling back to in-memory catalog.", resolved, e)

        # 3. Resilient In-Memory Fallback
        return self._init_in_memory_fallback()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Safe connection context manager ensuring non-memory connections are cleanly closed."""
        conn = self._get_connection()
        try:
            yield conn
        finally:
            if conn != self._memory_conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def is_available(self) -> bool:
        """Check if the SQLite database exists or in-memory fallback is queryable."""
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM restaurants;")
                count = cursor.fetchone()[0]
                return count > 0
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
        with self._connection() as conn:
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

        with self._connection() as conn:
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

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def list_cities(self) -> list[str]:
        """List all distinct normalized cities in the dataset."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT city FROM restaurants WHERE city IS NOT NULL ORDER BY city ASC;")
            return [row["city"] for row in cursor.fetchall()]

    def list_cuisines(self, city: str | None = None) -> list[str]:
        """List all distinct cuisines, optionally filtered by city."""
        with self._connection() as conn:
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
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM restaurants;")
            row = cursor.fetchone()
            return int(row["total"]) if row else 0

    def get_catalog_stats(self) -> dict[str, Any]:
        """Return aggregate summary metrics of the restaurant database."""
        with self._connection() as conn:
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
