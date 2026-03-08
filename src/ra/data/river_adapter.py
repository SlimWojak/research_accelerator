"""River adapter stub for Phoenix River parquet data.

This is a stub for Phase 1. The 5-day calibration dataset predates River
ingestion, so the CSV loader is used as the primary data source.

River integration for multi-month data comes in Phase 2+ when data
acquisition expands to 6-12 months.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class RiverAdapter:
    """Read-only adapter for Phoenix River parquet data (STUB).

    Phase 1: Only CSV fallback is functional.
    Phase 2+: Parquet loading via DuckDB will be implemented.
    """

    def __init__(self, river_root: str | None = None):
        """Initialize the adapter.

        Args:
            river_root: Path to phoenix-river/ directory.
                        Not used in Phase 1 stub.
        """
        self.river_root = river_root
        logger.info("RiverAdapter initialized (stub mode)")

    def load_bars(
        self,
        pair: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1m",
    ) -> pd.DataFrame:
        """Load bars from River parquet files.

        Not implemented in Phase 1. Use load_from_csv() instead.

        Raises:
            NotImplementedError: Always in Phase 1.
        """
        raise NotImplementedError(
            "River parquet loading not available in Phase 1. "
            "Use load_from_csv() or ra.data.csv_loader.load_csv() instead."
        )

    def load_and_aggregate(
        self,
        pair: str,
        start_date: str,
        end_date: str,
        timeframe: str,
    ) -> pd.DataFrame:
        """Load 1m bars and aggregate to target timeframe.

        Not implemented in Phase 1.

        Raises:
            NotImplementedError: Always in Phase 1.
        """
        raise NotImplementedError(
            "River parquet loading not available in Phase 1. "
            "Use csv_loader + tf_aggregator instead."
        )

    def available_range(self, pair: str) -> tuple[str, str]:
        """Return (earliest_date, latest_date) for a pair.

        Not implemented in Phase 1.

        Raises:
            NotImplementedError: Always in Phase 1.
        """
        raise NotImplementedError("Not available in Phase 1 stub.")

    def validate_integrity(
        self,
        pair: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """Quick integrity check.

        Not implemented in Phase 1.

        Raises:
            NotImplementedError: Always in Phase 1.
        """
        raise NotImplementedError("Not available in Phase 1 stub.")

    def load_from_csv(
        self,
        csv_path: str | Path,
        pair: str = "EURUSD",
    ) -> pd.DataFrame:
        """Load from CSV (current pipeline format).

        Convenience method that delegates to csv_loader.load_csv().

        Args:
            csv_path: Path to 1m CSV file.
            pair: Currency pair name (metadata only).

        Returns:
            DataFrame with bar contract columns.
        """
        from ra.data.csv_loader import load_csv

        return load_csv(csv_path)
