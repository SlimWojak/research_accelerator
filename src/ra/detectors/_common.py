"""Shared utilities for RA detector modules.

Common constants, helpers, and mappings used across multiple detectors.
Extracted to avoid duplication across leaf and composite detectors.
"""

from typing import Optional

import pandas as pd

# Pip constant for EURUSD (and most forex pairs with 4 decimal places)
PIP = 0.0001

# Pipeline session mapping: the RA data layer uses 6 session categories
# (asia, pre_london, lokz, pre_ny, nyokz, other) but the pipeline baseline
# only uses 4 (asia, lokz, nyokz, other). Map pre_london/pre_ny -> "other"
# for baseline-compatible output.
_SESSION_MAP = {
    "asia": "asia",
    "lokz": "lokz",
    "nyokz": "nyokz",
    "pre_london": "other",
    "pre_ny": "other",
    "other": "other",
}

# Timeframe to minutes mapping
TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1H": 60,
    "4H": 240,
    "1D": 1440,
}


def map_session(session: str) -> str:
    """Map RA session label to pipeline-compatible session label."""
    return _SESSION_MAP.get(session, session)


def bar_time_str(ts_ny: pd.Timestamp, tf_minutes: int) -> str:
    """Compute the clock-aligned group-key time string for a bar.

    The pipeline uses floor(minute / period) * period as the canonical
    time label. For 1m bars, this is just the bar's own timestamp.
    For 5m bars, a bar at 17:04 gets key 17:00, a bar at 17:07 gets 17:05, etc.

    Args:
        ts_ny: Bar's NY timezone timestamp.
        tf_minutes: Timeframe period in minutes (1, 5, 15, etc.).

    Returns:
        NY time string in ISO format (YYYY-MM-DDTHH:MM:SS).
    """
    if tf_minutes <= 1:
        return ts_ny.strftime("%Y-%m-%dT%H:%M:%S")

    total_min = ts_ny.hour * 60 + ts_ny.minute
    floored = (total_min // tf_minutes) * tf_minutes
    gh = floored // 60
    gm = floored % 60
    return ts_ny.strftime("%Y-%m-%d") + f"T{gh:02d}:{gm:02d}:00"


def compute_atr(bars: pd.DataFrame, period: int = 14) -> list[Optional[float]]:
    """Compute ATR(period) for each bar in a DataFrame.

    Uses classic Wilder smoothing: first ATR = simple average of first
    ``period`` TRs, then EMA: ATR[i] = (ATR[i-1] * (period-1) + TR[i]) / period.

    Args:
        bars: DataFrame with high, low, close columns.
        period: ATR period (default 14).

    Returns:
        List of ATR values aligned to bars (None for first period-1 bars).
    """
    n = len(bars)
    highs = bars["high"].values
    lows = bars["low"].values
    closes = bars["close"].values

    atrs: list[Optional[float]] = [None] * n
    trs: list[float] = []

    for i in range(n):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            prev_close = closes[i - 1]
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        trs.append(tr)

        if i >= period - 1:
            if i == period - 1:
                atrs[i] = sum(trs[:period]) / period
            else:
                atrs[i] = (atrs[i - 1] * (period - 1) + tr) / period

    return atrs


def compute_atr_from_dicts(
    bars: list[dict], period: int = 14
) -> list[Optional[float]]:
    """Compute ATR(period) for a list of bar dicts.

    Same algorithm as :func:`compute_atr` but accepts ``list[dict]`` input
    (used by HTF detectors that aggregate to dict bars).

    Args:
        bars: List of bar dicts with ``high``, ``low``, ``close`` keys.
        period: ATR period (default 14).

    Returns:
        List of ATR values aligned to bars (None for first period-1 bars).
    """
    n = len(bars)
    atrs: list[Optional[float]] = [None] * n
    trs: list[float] = []

    for i in range(n):
        bar = bars[i]
        if i == 0:
            tr = bar["high"] - bar["low"]
        else:
            prev_close = bars[i - 1]["close"]
            tr = max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev_close),
                abs(bar["low"] - prev_close),
            )
        trs.append(tr)

        if i >= period - 1:
            if i == period - 1:
                atrs[i] = sum(trs[:period]) / period
            else:
                atrs[i] = (atrs[i - 1] * (period - 1) + tr) / period

    return atrs
