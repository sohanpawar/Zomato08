"""Dataset Ingestion and Preprocessing Pipeline.

Orchestrates loading raw data from Hugging Face or local fixtures, cleaning,
normalizing, deduplicating, and persisting to Parquet, SQLite, and metadata reports.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import Settings
from app.data.storage import save_restaurants_to_parquet, save_restaurants_to_sqlite
from app.exceptions import DataIngestionError
from app.ingestion.cleaner import deduplicate_restaurants, normalize_raw_record
from app.logging import get_logger
from app.models.restaurant import Restaurant

logger = get_logger(__name__)


@dataclass
class IngestionReport:
    """Detailed summary report of the dataset ingestion execution."""

    source_dataset: str
    dataset_revision: str | None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_raw_rows: int = 0
    valid_rows: int = 0
    clean_deduped_rows: int = 0
    dropped_rows: int = 0
    duplicates_removed: int = 0
    drop_reasons: dict[str, int] = field(default_factory=dict)
    budget_distribution: dict[str, int] = field(default_factory=dict)
    sqlite_path: str | None = None
    parquet_path: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return asdict(self)


class IngestionPipeline:
    """Pipeline for loading, cleaning, normalizing, and indexing the Zomato dataset."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load_raw_dataset(
        self,
        local_file: Path | str | None = None,
        limit: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Load raw records from Hugging Face datasets or a local file.

        Args:
            local_file: Optional path to a local JSON, CSV, or Parquet file.
            limit: Optional limit on the number of raw rows to load.

        Returns:
            Iterable of raw dictionary records.
        """
        # 1. Load from local file if provided
        if local_file:
            path = Path(local_file)
            if not path.is_file():
                raise DataIngestionError(f"Local dataset file not found: {path}")

            logger.info("Loading raw dataset from local file: %s", path)
            if path.suffix == ".json":
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[:limit] if limit else data
                    raise DataIngestionError("Local JSON file must contain a top-level array of objects.")
            elif path.suffix == ".csv":
                import pandas as pd
                df = pd.read_csv(path, nrows=limit)
                records: list[dict[str, Any]] = df.to_dict(orient="records")
                return records
            elif path.suffix in {".parquet", ".pq"}:
                import pandas as pd
                df = pd.read_parquet(path)
                if limit:
                    df = df.head(limit)
                records_pq: list[dict[str, Any]] = df.to_dict(orient="records")
                return records_pq
            else:
                raise DataIngestionError(f"Unsupported local file extension: {path.suffix}")

        # 2. Load from Hugging Face Hub
        try:
            from datasets import load_dataset

            logger.info(
                "Fetching dataset '%s' (revision: %s) from Hugging Face Hub...",
                self.settings.dataset_name,
                self.settings.dataset_revision,
            )

            ds = load_dataset(
                self.settings.dataset_name,
                revision=self.settings.dataset_revision,
                split="train",
            )

            if limit:
                ds = ds.select(range(min(limit, len(ds))))

            logger.info("Successfully fetched %d raw records from Hugging Face Hub.", len(ds))
            return iter(ds)
        except Exception as e:
            logger.error("Failed to load dataset from Hugging Face: %s", str(e), exc_info=True)
            raise DataIngestionError(
                f"Could not load dataset '{self.settings.dataset_name}' from Hugging Face: {e}"
            ) from e

    def transform_records(
        self,
        raw_records: Iterable[dict[str, Any]],
    ) -> tuple[list[Restaurant], IngestionReport]:
        """Normalize, validate, and deduplicate raw records.

        Args:
            raw_records: Stream or list of raw dictionary records.

        Returns:
            tuple[list[Restaurant], IngestionReport]: Clean deduplicated restaurants and execution report.
        """
        report = IngestionReport(
            source_dataset=self.settings.dataset_name,
            dataset_revision=self.settings.dataset_revision,
        )

        valid_restaurants: list[Restaurant] = []
        drop_reasons: dict[str, int] = {}
        total_raw = 0

        for raw_row in raw_records:
            total_raw += 1
            restaurant, drop_reason = normalize_raw_record(raw_row, default_city="bangalore")

            if restaurant is not None:
                valid_restaurants.append(restaurant)
            else:
                reason = drop_reason or "unknown_drop_reason"
                drop_reasons[reason] = drop_reasons.get(reason, 0) + 1

        report.total_raw_rows = total_raw
        report.valid_rows = len(valid_restaurants)
        report.dropped_rows = total_raw - len(valid_restaurants)
        report.drop_reasons = drop_reasons

        # Deduplicate multiple zone entries
        deduped_restaurants, duplicates_removed = deduplicate_restaurants(valid_restaurants)
        report.clean_deduped_rows = len(deduped_restaurants)
        report.duplicates_removed = duplicates_removed

        # Calculate budget distribution
        budget_counts: dict[str, int] = {}
        for r in deduped_restaurants:
            b_val = r.budget_bucket.value
            budget_counts[b_val] = budget_counts.get(b_val, 0) + 1
        report.budget_distribution = budget_counts

        return deduped_restaurants, report

    def run(
        self,
        local_file: Path | str | None = None,
        limit: int | None = None,
        force_reload: bool = False,
    ) -> IngestionReport:
        """Execute the end-to-end ingestion pipeline.

        Args:
            local_file: Optional path to a local raw dataset file for offline ingestion.
            limit: Optional limit on the number of records to ingest.
            force_reload: Force reprocessing even if artifacts already exist.

        Returns:
            IngestionReport with detailed stats.
        """
        start_time = time.perf_counter()
        self.settings.ensure_directories_exist()

        sqlite_path = self.settings.sqlite_path
        parquet_path = self.settings.parquet_path

        if not force_reload and sqlite_path.is_file() and parquet_path.is_file():
            logger.info("Processed artifacts already exist. Skipping ingestion (use force_reload=True to re-run).")
            report = IngestionReport(
                source_dataset=self.settings.dataset_name,
                dataset_revision=self.settings.dataset_revision,
                sqlite_path=str(sqlite_path),
                parquet_path=str(parquet_path),
            )
            return report

        logger.info("Starting ingestion workflow for dataset: %s", self.settings.dataset_name)

        # 1. Load raw data
        raw_data = self.load_raw_dataset(local_file=local_file, limit=limit)

        # 2. Clean, normalize, and deduplicate
        restaurants, report = self.transform_records(raw_data)

        if not restaurants:
            raise DataIngestionError("Ingestion produced 0 valid restaurant records. Check source dataset.")

        # 3. Persist to SQLite
        save_restaurants_to_sqlite(restaurants, sqlite_path)
        report.sqlite_path = str(sqlite_path)

        # 4. Persist to Parquet
        save_restaurants_to_parquet(restaurants, parquet_path)
        report.parquet_path = str(parquet_path)

        # 5. Save report metadata JSON
        report.duration_seconds = round(time.perf_counter() - start_time, 2)
        report_path = self.settings.processed_data_dir / "ingestion_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info(
            "Ingestion pipeline completed in %.2fs. Valid restaurants: %d (Duplicates removed: %d, Dropped: %d)",
            report.duration_seconds,
            report.clean_deduped_rows,
            report.duplicates_removed,
            report.dropped_rows,
        )

        return report
