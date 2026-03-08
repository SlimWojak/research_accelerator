"""Session tagger for bar DataFrames.

Tags each bar with session context based on NY timezone:
  - session: asia, lokz, nyokz, pre_london, pre_ny, other
  - kill_zone: lokz, nyokz, or None
  - ny_window: "a" (08:00-09:00), "b" (10:00-11:00), or None
  - forex_day: date string (17:00 NY boundary)

All times interpreted in NY timezone.
"""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Session definitions (NY time hours)
# Asia:        19:00 - 00:00  (h >= 19)
# Pre-London:  00:00 - 02:00  (0 <= h < 2)
# LOKZ:        02:00 - 05:00  (2 <= h < 5)
# Pre-NY:      05:00 - 07:00  (5 <= h < 7)
# NYOKZ:       07:00 - 10:00  (7 <= h < 10)
# Other:       10:00 - 19:00  (10 <= h < 19)


def _classify_session(hour: int) -> str:
    """Classify NY hour into session name."""
    if hour >= 19:
        return "asia"
    if hour < 2:
        return "pre_london"
    if hour < 5:
        return "lokz"
    if hour < 7:
        return "pre_ny"
    if hour < 10:
        return "nyokz"
    return "other"


def _classify_kill_zone(hour: int) -> str | None:
    """Classify NY hour into kill zone (lokz/nyokz/None)."""
    if 2 <= hour < 5:
        return "lokz"
    if 7 <= hour < 10:
        return "nyokz"
    return None


def _classify_ny_window(hour: int) -> str | None:
    """Classify NY hour into NY window (a/b/None).

    Window A: 08:00-09:00 NY (reversal energy, inside NYOKZ)
    Window B: 10:00-11:00 NY (continuation energy, overlaps NYOKZ end)
    """
    if 8 <= hour < 9:
        return "a"
    if 10 <= hour < 11:
        return "b"
    return None


def _compute_forex_day(ny_dt: pd.Timestamp) -> str:
    """Compute the forex trading day for a NY timestamp.

    Forex day boundary is 17:00 NY.
    Bars at or after 17:00 NY belong to the NEXT calendar day's forex day.
    """
    if ny_dt.hour >= 17:
        return (ny_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    return ny_dt.strftime("%Y-%m-%d")


def tag_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Add session columns to a bar DataFrame.

    Expects a ``timestamp_ny`` column (timezone-aware, NY).
    Adds columns: session, kill_zone, ny_window, forex_day.

    Args:
        df: Bar DataFrame with ``timestamp_ny`` column.

    Returns:
        DataFrame with session columns added (modified in-place for
        efficiency, but also returned for chaining).
    """
    ny_hours = df["timestamp_ny"].dt.hour

    df["session"] = ny_hours.map(_classify_session)
    df["kill_zone"] = ny_hours.map(_classify_kill_zone)
    df["ny_window"] = ny_hours.map(_classify_ny_window)
    df["forex_day"] = df["timestamp_ny"].map(_compute_forex_day)

    return df
