"""Timeframe aggregator for 1m bar DataFrames.

Aggregates 1m bars to 5m, 15m, 1H, 4H, and 1D using clock-aligned
windows in NY timezone.

Aggregation rules (OHLCV):
  - open  = first bar's open
  - high  = max of all bars' high
  - low   = min of all bars' low
  - close = last bar's close
  - volume = sum of all bars' volume
  - is_ghost = True only if ALL constituent bars are ghost
  - timestamp = first bar's timestamp (window open)
  - Session tags propagated from constituent bars

Alignment:
  - 5m:  clock-aligned (00, 05, 10, ...)
  - 15m: clock-aligned (00, 15, 30, 45)
  - 1H:  clock-aligned (00:00, 01:00, ...)
  - 4H:  clock-aligned on NY time (240-minute floor)
  - 1D:  forex day (17:00 NY to 17:00 NY)
"""

import logging
from zoneinfo import ZoneInfo

import pandas as pd

from ra.data.session_tagger import tag_sessions

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Supported timeframe strings and their minute durations
TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1H": 60,
    "4H": 240,
    "1D": None,  # special handling
}


def aggregate(bars_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate 1m bars to the target timeframe.

    Args:
        bars_1m: 1m bar DataFrame with bar contract columns.
        timeframe: Target timeframe string ("5m", "15m", "1H", "4H", "1D").

    Returns:
        Aggregated DataFrame with same column schema as input,
        integer index, sorted by timestamp ascending.

    Raises:
        ValueError: If timeframe is not supported.
    """
    if timeframe == "1m":
        return bars_1m.copy()

    if timeframe not in TF_MINUTES:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}. "
            f"Supported: {list(TF_MINUTES.keys())}"
        )

    if timeframe == "1D":
        return _aggregate_daily(bars_1m)

    period = TF_MINUTES[timeframe]
    return _aggregate_intraday(bars_1m, period)


def _compute_group_key(ny_dt: pd.Series, period: int) -> pd.Series:
    """Compute group key for each bar based on NY time flooring.

    Groups bars by flooring NY time to the nearest ``period``-minute
    boundary, then combining with NY calendar date.
    """
    ny_hour = ny_dt.dt.hour
    ny_minute = ny_dt.dt.minute
    total_min = ny_hour * 60 + ny_minute
    group_min = (total_min // period) * period
    group_h = group_min // 60
    group_m = group_min % 60

    # Build group key from NY date + floored time
    date_str = ny_dt.dt.strftime("%Y-%m-%d")
    return date_str + "T" + group_h.astype(str).str.zfill(2) + ":" + group_m.astype(str).str.zfill(2)


def _aggregate_intraday(bars_1m: pd.DataFrame, period: int) -> pd.DataFrame:
    """Aggregate 1m bars to an intraday timeframe (5m, 15m, 1H, 4H)."""
    df = bars_1m.copy()

    # Compute group key from NY timestamps
    group_key = _compute_group_key(df["timestamp_ny"], period)
    df["_group_key"] = group_key

    # Aggregate per group
    agg_records = []
    for key, group in df.groupby("_group_key", sort=True):
        record = _aggregate_group(group)
        agg_records.append(record)

    result = pd.DataFrame(agg_records)

    # Re-tag sessions on the aggregated bars
    result = tag_sessions(result)

    # Ensure integer index
    result = result.reset_index(drop=True)

    logger.info(
        "Aggregated %d 1m bars to %d %dm bars",
        len(bars_1m),
        len(result),
        period,
    )
    return result


def _aggregate_daily(bars_1m: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1m bars to daily (forex day) bars.

    Forex day: 17:00 NY to 17:00 NY next day.
    """
    df = bars_1m.copy()

    # Group by forex_day
    agg_records = []
    for forex_day, group in df.groupby("forex_day", sort=True):
        record = _aggregate_group(group)
        agg_records.append(record)

    result = pd.DataFrame(agg_records)

    # Re-tag sessions on the aggregated bars
    result = tag_sessions(result)

    # Ensure integer index
    result = result.reset_index(drop=True)

    logger.info(
        "Aggregated %d 1m bars to %d daily bars",
        len(bars_1m),
        len(result),
    )
    return result


def _aggregate_group(group: pd.DataFrame) -> dict:
    """Aggregate a group of constituent 1m bars into one OHLCV bar.

    OHLCV rules:
      - open  = first bar's open
      - high  = max(high)
      - low   = min(low)
      - close = last bar's close
      - volume = sum(volume)
      - is_ghost = True iff ALL constituent bars are ghost
      - timestamp = first bar's timestamp (UTC)
      - timestamp_ny = first bar's timestamp_ny
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
