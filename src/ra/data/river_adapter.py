"""River adapter for Phoenix River parquet data.

DuckDB-backed parquet reader for ~/phoenix-river/{pair}/{year}/{mm}/{dd}.parquet.
Timezone normalization: Asia/Bangkok → UTC → NY.
Ghost bar convention: volume==0 is ghost, volume==-1 (IBKR midpoint) is NOT ghost.

INV-RA-RIVER-READONLY: RA never writes to phoenix-river/. Read-only consumer.
"""

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from ra.data.session_tagger import tag_sessions
from ra.data.tf_aggregator import aggregate

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Forex day starts at 17:00 NY (1020 minutes from midnight).
_FOREX_DAY_OFFSET_MIN = 17 * 60


class RiverAdapter:
    """Read-only adapter for Phoenix River parquet data.

    Reads 1m bar parquet files via DuckDB, normalizes timezones,
    adds is_ghost flag, and delegates to TF aggregator for higher timeframes.
    """

    def __init__(self, river_root: str | None = None):
        """Initialize the adapter.

        Args:
            river_root: Path to phoenix-river/ directory.
                        Defaults to RIVER_ROOT env var, then ~/phoenix-river.
        """
        if river_root is not None:
            self.river_root = Path(river_root)
        else:
            env_root = os.environ.get("RIVER_ROOT")
            if env_root:
                self.river_root = Path(env_root)
            else:
                self.river_root = Path(os.path.expanduser("~/phoenix-river"))

        logger.info("RiverAdapter initialized (root=%s)", self.river_root)

    def load_bars(
        self,
        pair: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1m",
    ) -> pd.DataFrame:
        """Load bars from River parquet files.

        Reads parquet files for each calendar day in [start_date, end_date],
        skipping missing days (weekends/holidays). Normalizes timestamps
        from Asia/Bangkok to UTC and computes timestamp_ny.

        Args:
            pair: Currency pair (e.g. "EURUSD").
            start_date: Start date inclusive (e.g. "2024-01-08").
            end_date: End date inclusive (e.g. "2024-01-08").
            timeframe: Base resolution (only "1m" supported here).

        Returns:
            DataFrame with bar contract columns: timestamp (UTC),
            timestamp_ny (NY), open, high, low, close, volume, source,
            knowledge_time, bar_hash, is_ghost, session, kill_zone,
            ny_window, forex_day. Integer positional index, sorted ascending.
        """
        parquet_files = self._collect_parquet_files(pair, start_date, end_date)

        if not parquet_files:
            return self._empty_bars_df()

        # Read all matching parquet files with DuckDB
        df = self._read_parquets(parquet_files)

        # Normalize timestamps: Asia/Bangkok → UTC
        df = self._normalize_timestamps(df)

        # Add is_ghost flag: volume == 0 is ghost, volume == -1 is NOT ghost
        df["is_ghost"] = df["volume"] == 0.0

        # Ensure volume is float64 (matching csv_loader convention)
        df["volume"] = df["volume"].astype("float64")

        # Compute NY timestamp
        df["timestamp_ny"] = df["timestamp"].dt.tz_convert(NY_TZ)

        # Sort by timestamp ascending and reset index
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Remove duplicates by timestamp (keep first)
        df = df.drop_duplicates(subset=["timestamp"], keep="first").reset_index(drop=True)

        # Tag sessions
        df = tag_sessions(df)

        # Ensure integer positional index
        df = df.reset_index(drop=True)

        logger.info(
            "Loaded %d 1m bars for %s [%s to %s]",
            len(df),
            pair,
            start_date,
            end_date,
        )
        return df

    def load_and_aggregate(
        self,
        pair: str,
        start_date: str,
        end_date: str,
        timeframe: str,
    ) -> pd.DataFrame:
        """Load 1m bars and aggregate to target timeframe.

        Delegates to the existing TF aggregator for 5m/15m/1H.
        For 4H, uses forex-day-aligned 4H aggregation: bars are grouped
        into 4-hour windows starting at 17:00 NY (the forex day boundary),
        producing bars at [17:00, 21:00, 01:00, 05:00, 09:00, 13:00] NY.
        For 1D, delegates to the existing TF aggregator (forex day grouping).

        Args:
            pair: Currency pair.
            start_date: Start date inclusive.
            end_date: End date inclusive.
            timeframe: Target timeframe ("1m", "5m", "15m", "1H", "4H", "1D").

        Returns:
            Aggregated DataFrame with bar contract columns.
        """
        bars_1m = self.load_bars(pair, start_date, end_date)

        if timeframe == "1m":
            return bars_1m

        if timeframe == "4H":
            return self._aggregate_4h_forex_aligned(bars_1m)

        return aggregate(bars_1m, timeframe)

    def available_range(self, pair: str) -> tuple[str, str]:
        """Return (earliest_date, latest_date) for a pair.

        Scans the filesystem directory structure to find the min and max
        dates that have parquet files.

        Args:
            pair: Currency pair (e.g. "EURUSD").

        Returns:
            Tuple of (earliest_date, latest_date) as "YYYY-MM-DD" strings.

        Raises:
            FileNotFoundError: If no parquet files found for the pair.
        """
        pair_dir = self.river_root / pair

        if not pair_dir.exists():
            raise FileNotFoundError(f"No River data directory for {pair}: {pair_dir}")

        earliest = None
        latest = None

        for year_dir in sorted(pair_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            year = year_dir.name

            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                month = month_dir.name

                for parquet_file in sorted(month_dir.iterdir()):
                    if parquet_file.suffix != ".parquet":
                        continue
                    day = parquet_file.stem
                    try:
                        dt = date(int(year), int(month), int(day))
                    except ValueError:
                        continue

                    date_str = dt.strftime("%Y-%m-%d")
                    if earliest is None or date_str < earliest:
                        earliest = date_str
                    if latest is None or date_str > latest:
                        latest = date_str

        if earliest is None or latest is None:
            raise FileNotFoundError(f"No parquet files found for {pair}")

        return (earliest, latest)

    def validate_integrity(
        self,
        pair: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """Quick integrity check: gap count, bar count, ghost count.

        Loads bars for the date range and reports:
        - bar_count: total number of 1m bars
        - ghost_count: number of ghost bars (volume == 0)
        - gap_count: number of missing minutes within trading days

        Args:
            pair: Currency pair.
            start_date: Start date inclusive.
            end_date: End date inclusive.

        Returns:
            Dict with keys: bar_count, ghost_count, gap_count.
        """
        df = self.load_bars(pair, start_date, end_date)

        bar_count = len(df)
        ghost_count = int(df["is_ghost"].sum())

        # Compute gap count: for each trading day, check we have 1440 bars
        # A "gap" is a missing minute within a day that has a parquet file
        parquet_files = self._collect_parquet_files(pair, start_date, end_date)
        expected_bars = len(parquet_files) * 1440
        gap_count = max(0, expected_bars - bar_count)

        return {
            "bar_count": bar_count,
            "ghost_count": ghost_count,
            "gap_count": gap_count,
        }

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

    # ----------------------------------------------------------------
    # 4H forex-day-aligned aggregation
    # ----------------------------------------------------------------

    def _aggregate_4h_forex_aligned(self, bars_1m: pd.DataFrame) -> pd.DataFrame:
        """Aggregate 1m bars to 4H with forex-day boundary alignment.

        Forex 4H periods within a forex day (17:00 NY to 17:00 NY):
          [17:00-20:59, 21:00-00:59, 01:00-04:59, 05:00-08:59, 09:00-12:59, 13:00-16:59]

        This produces bars at NY hours [17, 21, 1, 5, 9, 13].
        """
        df = bars_1m.copy()

        # Compute the 4H group key using forex day + bucket within forex day
        ny_hour = df["timestamp_ny"].dt.hour
        ny_minute = df["timestamp_ny"].dt.minute
        total_min = ny_hour * 60 + ny_minute

        # Minutes since 17:00 NY (forex day start), wrapping at 24h
        offset_min = (total_min - _FOREX_DAY_OFFSET_MIN) % (24 * 60)
        bucket = offset_min // 240  # 0-5 (6 buckets per forex day)

        # Group key: forex_day + bucket
        df["_group_key"] = df["forex_day"] + "_" + bucket.astype(str)

        # Aggregate per group
        agg_records = []
        for _key, group in df.groupby("_group_key", sort=True):
            record = self._aggregate_group(group)
            agg_records.append(record)

        result = pd.DataFrame(agg_records)

        # Drop temporary column from result if present
        if "_group_key" in result.columns:
            result = result.drop(columns=["_group_key"])

        # Re-tag sessions on the aggregated bars
        result = tag_sessions(result)

        # Ensure integer index
        result = result.reset_index(drop=True)

        logger.info(
            "Aggregated %d 1m bars to %d forex-aligned 4H bars",
            len(bars_1m),
            len(result),
        )
        return result

    @staticmethod
    def _aggregate_group(group: pd.DataFrame) -> dict:
        """Aggregate a group of constituent 1m bars into one OHLCV bar.

        Same rules as tf_aggregator._aggregate_group:
          open  = first bar's open
          high  = max(high)
          low   = min(low)
          close = last bar's close
          volume = sum(volume)
          is_ghost = True iff ALL constituent bars are ghost
          timestamp = first bar's timestamp (UTC)
          timestamp_ny = first bar's timestamp_ny
        """
        first = group.iloc[0]
        last = group.iloc[-1]

        return {
            "timestamp": first["timestamp"],
            "timestamp_ny": first["timestamp_ny"],
            "open": first["open"],
            "high": group["high"].max(),
            "low": group["low"].min(),
            "close": last["close"],
            "volume": group["volume"].sum(),
            "is_ghost": group["is_ghost"].all(),
        }

    # ----------------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------------

    def _collect_parquet_files(
        self,
        pair: str,
        start_date: str,
        end_date: str,
    ) -> list[Path]:
        """Collect all parquet file paths for the given date range.

        Iterates calendar days from start_date to end_date inclusive,
        returning paths for files that exist on disk.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        files = []
        current = start
        while current <= end:
            year = f"{current.year}"
            month = f"{current.month:02d}"
            day = f"{current.day:02d}"
            path = self.river_root / pair / year / month / f"{day}.parquet"
            if path.exists():
                files.append(path)
            current += timedelta(days=1)

        return files

    def _read_parquets(self, parquet_files: list[Path]) -> pd.DataFrame:
        """Read multiple parquet files using DuckDB and return a DataFrame."""
        file_list = [str(f) for f in parquet_files]

        # Build DuckDB query with file list
        file_list_str = ", ".join(f"'{f}'" for f in file_list)
        query = f"""
            SELECT *
            FROM read_parquet([{file_list_str}])
            ORDER BY timestamp
        """
        conn = duckdb.connect()
        try:
            df = conn.execute(query).fetchdf()
        finally:
            conn.close()

        return df

    def _normalize_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize timestamps from Asia/Bangkok to UTC.

        Raw parquet timestamps are in Asia/Bangkok (UTC+7).
        Convert to UTC timezone-aware timestamps.
        """
        ts = df["timestamp"]

        if ts.dt.tz is not None:
            # Already timezone-aware (Asia/Bangkok from parquet) — convert to UTC
            df["timestamp"] = ts.dt.tz_convert(UTC_TZ)
        else:
            # If somehow tz-naive, assume Asia/Bangkok and localize then convert
            df["timestamp"] = ts.dt.tz_localize("Asia/Bangkok").dt.tz_convert(UTC_TZ)

        # Also normalize knowledge_time if present
        if "knowledge_time" in df.columns:
            kt = df["knowledge_time"]
            if kt.dt.tz is not None:
                df["knowledge_time"] = kt.dt.tz_convert(UTC_TZ)
            else:
                df["knowledge_time"] = kt.dt.tz_localize("Asia/Bangkok").dt.tz_convert(UTC_TZ)

        return df

    def _empty_bars_df(self) -> pd.DataFrame:
        """Return an empty DataFrame with the correct bar contract schema."""
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "source",
                "knowledge_time",
                "bar_hash",
                "is_ghost",
                "timestamp_ny",
                "session",
                "kill_zone",
                "ny_window",
                "forex_day",
            ]
        )
