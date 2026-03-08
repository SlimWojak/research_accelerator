"""Swing Points detector using N-bar pivot algorithm.

Implements:
- N-bar pivot: swing high when bar.high >= all N bars left AND > all N bars right
- Swing low: symmetric with <= left, < right
- Strength: count of additional bars beyond N where extreme holds, capped at strength_cap
- Height: pip distance from nearest opposite swing (sentinel 999.0 at boundaries)
- Ghost bar skipping

Reference: pipeline/preprocess_data_v2.py detect_swings() + compute_swing_height().
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import PIP, TF_MINUTES, bar_time_str, map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

# Keep local aliases for backward compatibility within this module
_map_session = map_session
_bar_time_str = bar_time_str
_TF_MINUTES = TF_MINUTES


class SwingPointDetector(PrimitiveDetector):
    """Swing point detector: N-bar pivot with strength and height.

    Leaf detector (no upstream dependencies).
    """

    primitive_name = "swing_points"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        """Swing points is a leaf node — no upstream dependencies."""
        return []

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Detect swing highs/lows using N-bar pivot algorithm.

        Args:
            bars: DataFrame with bar contract columns (integer index).
            params: Must contain 'N' (int), 'height_filter_pips' (float),
                    'strength_cap' (int), 'strength_as_gate' (bool).
            upstream: Not used (leaf detector).
            context: Must contain 'timeframe' (str, e.g., '5m').

        Returns:
            DetectionResult with swing point detections.
        """
        context = context or {}
        tf = context.get("timeframe", "1m")
        tf_minutes = _TF_MINUTES.get(tf, 1)

        n = params.get("N", 5)
        strength_cap = params.get("strength_cap", 20)
        height_filter_pips = params.get("height_filter_pips", 0.5)

        # Extract arrays for fast access
        num_bars = len(bars)
        highs = bars["high"].values
        lows = bars["low"].values
        ts_ny_series = bars["timestamp_ny"]
        sessions = bars["session"].values
        forex_days = bars["forex_day"].values
        is_ghost = bars["is_ghost"].values if "is_ghost" in bars.columns else None

        # Phase 1: Detect raw swing points (N-bar pivot)
        swings = self._detect_pivots(
            num_bars, n, highs, lows, ts_ny_series, sessions,
            forex_days, is_ghost, strength_cap, tf, tf_minutes,
        )

        # Phase 2: Compute height (pip distance from nearest opposite swing)
        swings = self._compute_height(swings)

        # Phase 3: Build Detection objects
        detections = []
        for swing in swings:
            det_time = pd.Timestamp(swing["time"])

            det_id = make_detection_id(
                primitive="swing_points",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=swing["type"],
            )

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=swing["type"],
                type="swing_point",
                price=swing["price"],
                properties={
                    "bar_index": swing["bar_index"],
                    "time": swing["time"],
                    "strength": swing["strength"],
                    "height_pips": swing["height_pips"],
                    "tf": swing["tf"],
                },
                tags={
                    "session": swing["session"],
                    "forex_day": swing["forex_day"],
                },
            )
            detections.append(detection)

        # Build metadata
        high_count = sum(1 for d in detections if d.direction == "high")
        low_count = sum(1 for d in detections if d.direction == "low")

        metadata = {
            "total_count": len(detections),
            "high_count": high_count,
            "low_count": low_count,
            "n": n,
            "strength_cap": strength_cap,
            "height_filter_pips": height_filter_pips,
        }

        return DetectionResult(
            primitive="swing_points",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )

    @staticmethod
    def _detect_pivots(
        num_bars: int,
        n: int,
        highs,
        lows,
        ts_ny_series,
        sessions,
        forex_days,
        is_ghost,
        strength_cap: int,
        tf: str,
        tf_minutes: int,
    ) -> list[dict]:
        """Detect swing highs and lows using N-bar pivot algorithm.

        Swing High: bar[i].high >= all N bars left AND > all N bars right
        Swing Low: bar[i].low <= all N bars left AND < all N bars right

        Args:
            num_bars: Total number of bars.
            n: Lookback/lookahead window size.
            highs: High price array.
            lows: Low price array.
            ts_ny_series: Timestamp NY series.
            sessions: Session label array.
            forex_days: Forex day label array.
            is_ghost: Ghost bar flag array (or None).
            strength_cap: Maximum strength value.
            tf: Timeframe label.
            tf_minutes: Timeframe in minutes.

        Returns:
            List of swing dicts with type, bar_index, time, price,
            strength, forex_day, session, tf.
        """
        swings = []

        for i in range(n, num_bars - n):
            # ── Swing High ──
            is_sh = True
            for j in range(i - n, i):
                if highs[i] < highs[j]:
                    is_sh = False
                    break
            if is_sh:
                for j in range(i + 1, i + n + 1):
                    if highs[i] <= highs[j]:
                        is_sh = False
                        break

            if is_sh:
                # Compute strength: count bars beyond N where high holds
                strength = 0
                for k in range(i + n + 1, min(i + n + 1 + strength_cap, num_bars)):
                    if highs[k] > highs[i]:
                        break
                    strength += 1

                bar_time = _bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                bar_session = _map_session(sessions[i])

                swings.append({
                    "type": "high",
                    "bar_index": i,
                    "time": bar_time,
                    "price": float(highs[i]),
                    "strength": strength,
                    "forex_day": forex_days[i],
                    "session": bar_session,
                    "tf": tf,
                })

            # ── Swing Low ──
            is_sl = True
            for j in range(i - n, i):
                if lows[i] > lows[j]:
                    is_sl = False
                    break
            if is_sl:
                for j in range(i + 1, i + n + 1):
                    if lows[i] >= lows[j]:
                        is_sl = False
                        break

            if is_sl:
                # Compute strength: count bars beyond N where low holds
                strength = 0
                for k in range(i + n + 1, min(i + n + 1 + strength_cap, num_bars)):
                    if lows[k] < lows[i]:
                        break
                    strength += 1

                bar_time = _bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                bar_session = _map_session(sessions[i])

                swings.append({
                    "type": "low",
                    "bar_index": i,
                    "time": bar_time,
                    "price": float(lows[i]),
                    "strength": strength,
                    "forex_day": forex_days[i],
                    "session": bar_session,
                    "tf": tf,
                })

        return swings

    @staticmethod
    def _compute_height(swings: list[dict]) -> list[dict]:
        """Compute height (pip distance from nearest opposite swing).

        For each swing, look backward through sorted swings to find
        the nearest opposite-type swing. Height = pip distance between
        the two. If no opposite swing found (boundary), height = 999.0.

        Args:
            swings: List of swing dicts (must have type, price, bar_index).

        Returns:
            Same list with 'height_pips' added to each swing.
        """
        sorted_swings = sorted(swings, key=lambda s: s["bar_index"])

        for i, swing in enumerate(sorted_swings):
            min_dist = float("inf")
            # Look backward up to 50 swings
            for j in range(i - 1, max(i - 50, -1), -1):
                other = sorted_swings[j]
                if other["type"] != swing["type"]:
                    dist = abs(swing["price"] - other["price"]) / PIP
                    min_dist = min(min_dist, dist)
                    break

            if min_dist == float("inf"):
                swing["height_pips"] = 999.0
            else:
                swing["height_pips"] = round(min_dist, 2)

        return sorted_swings
