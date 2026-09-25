"""Data Access and Storage Package.

The lightweight ``repository`` layer is imported eagerly because it powers the
runtime API (serverless-safe, stdlib ``sqlite3`` only). The ``storage`` helpers
depend on heavy libraries (``pandas``/``pyarrow``) used exclusively by the
offline ingestion pipeline, so they are exposed lazily via ``__getattr__`` to
keep them out of the serverless import path and function bundle.
"""

from typing import TYPE_CHECKING, Any

from app.data.repository import RestaurantRepository, SQLiteRestaurantRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.data.storage import (
        init_sqlite_database,
        load_restaurants_from_sqlite,
        save_restaurants_to_parquet,
        save_restaurants_to_sqlite,
    )

_STORAGE_EXPORTS = {
    "init_sqlite_database",
    "load_restaurants_from_sqlite",
    "save_restaurants_to_parquet",
    "save_restaurants_to_sqlite",
}

__all__ = [
    "RestaurantRepository",
    "SQLiteRestaurantRepository",
    "init_sqlite_database",
    "load_restaurants_from_sqlite",
    "save_restaurants_to_parquet",
    "save_restaurants_to_sqlite",
]


def __getattr__(name: str) -> Any:
    """Lazily import heavy storage helpers only when actually accessed."""
    if name in _STORAGE_EXPORTS:
        from app.data import storage

        return getattr(storage, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
