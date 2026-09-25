#!/usr/bin/env python3
"""Dataset Ingestion CLI Runner.

Executes the offline ingestion pipeline to download, clean, normalize,
and store the Zomato restaurant recommendation dataset into Parquet & SQLite.

Usage:
    python scripts/run_ingestion.py
    python scripts/run_ingestion.py --force
    python scripts/run_ingestion.py --file tests/fixtures/sample_raw_zomato.json --limit 500
"""

import argparse
import sys
from pathlib import Path

# Add src to python path for standalone CLI execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.config import get_settings
from app.exceptions import DataIngestionError
from app.ingestion.pipeline import IngestionPipeline
from app.logging import get_logger, setup_logging

logger = get_logger("scripts.run_ingestion")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest and preprocess Zomato restaurant dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download and reprocessing of dataset even if artifacts exist.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to local raw dataset file (JSON/CSV/Parquet) for offline ingestion.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of raw records processed (useful for rapid testing).",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Format logs as structured JSON lines.",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(level=settings.log_level, json_format=args.json_logs or settings.json_logs)

    logger.info("Starting ingestion workflow for: %s", settings.dataset_name)

    try:
        pipeline = IngestionPipeline(settings=settings)
        report = pipeline.run(
            local_file=args.file,
            limit=args.limit,
            force_reload=args.force,
        )

        print("\n" + "=" * 60)
        print("🎉 INGESTION PIPELINE EXECUTION COMPLETED")
        print("=" * 60)
        print(f"Source Dataset:       {report.source_dataset} ({report.dataset_revision})")
        print(f"Total Raw Rows:       {report.total_raw_rows:,}")
        print(f"Clean Deduped Rows:   {report.clean_deduped_rows:,}")
        print(f"Duplicates Removed:   {report.duplicates_removed:,}")
        print(f"Dropped Rows:         {report.dropped_rows:,}")
        print(f"Execution Duration:   {report.duration_seconds:.2f} seconds")
        print(f"SQLite DB:            {report.sqlite_path}")
        print(f"Parquet File:         {report.parquet_path}")
        print("\nBudget Tier Breakdown:")
        for bucket, count in report.budget_distribution.items():
            print(f"  • {bucket.upper():<8}: {count:,} restaurants")
        print("=" * 60 + "\n")

    except DataIngestionError as e:
        logger.error("Data ingestion failed: %s", str(e), exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.critical("Unexpected error during ingestion: %s", str(e), exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
