"""CSV loader for 1m OHLCV bar data.

Reads a CSV file with columns: timestamp, open, high, low, close, volume.
Produces a pandas DataFrame matching the bar contract from
build_plan/03_RIVER_ADAPTER_SPEC.md section 7.

Output columns:
    timestamp (datetime UTC), timestamp_ny (datetime NY), open, high, low,
    close, volume (int64), is_ghost (bool), session (str), kill_zone (str|None),
    ny_window (str|None), forex_day (str).

Integer index (not timestamp-indexed).
"""

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ra.data.session_tagger import tag_sessions

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")


def load_csv(csv_path: str | Path) -> pd.DataFrame:
    """Load a 1m OHLCV CSV and return a fully tagged bar DataFrame.

    Args:
        csv_path: Path to the CSV file. Expected columns:
            timestamp (ISO 8601 UTC), open, high, low, close, volume.

    Returns:
        DataFrame with integer index and all bar contract columns:
        timestamp, timestamp_ny, open, high, low, close, volume,
        is_ghost, session, kill_zone, ny_window, forex_day.

    Raises:
        FileNotFoundError: If CSV file does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    # Validate required columns
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Parse timestamps as UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Sort by timestamp ascending
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Convert to NY timezone
    df["timestamp_ny"] = df["timestamp"].dt.tz_convert(NY_TZ)

    # Ensure OHLCV types
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype("float64")
    df["volume"] = df["volume"].astype("float64")

    # Ghost bar identification: volume == 0
    df["is_ghost"] = df["volume"] == 0.0

    # Tag sessions, kill zones, NY windows, forex day
    df = tag_sessions(df)

    # Ensure integer index
    df = df.reset_index(drop=True)

    logger.info("Loaded %d bars from %s", len(df), path)
    return df
