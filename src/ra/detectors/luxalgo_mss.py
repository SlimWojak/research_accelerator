"""LuxAlgo-inspired MSS (BOS/CHoCH) detector — clean-room implementation.

Implements Market Structure Shift detection inspired by LuxAlgo Smart Money
Concepts BOS/CHoCH logic. Key differences from a8ra_v1 MSSDetector:

1. **No displacement gate** — fires on any close beyond swing level,
   regardless of candle size or ATR multiple.
2. **Right-side N-bar pivot** for swing detection (not left-side).
   Uses ``ta.highest`` / ``ta.lowest`` equivalent: bar[N] > all bars[0..N-1].
3. **Two structure levels**: internal (5-bar pivot) and swing (configurable N-bar).
4. **BOS vs CHoCH classification** based on trend state:
   - BOS (Break of Structure): break in same direction as existing trend.
   - CHoCH (Change of Character): break against existing trend → flips trend.
5. **No impulse suppression** — can fire repeatedly.
6. **No upstream dependencies** — runs its own inline swing detection.

Reference: .factory/research/luxalgo-smc-analysis.md
License: Clean-room implementation (CC BY-NC-SA 4.0 compliance).
Registered as: (mss, luxalgo_v1).
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import TF_MINUTES, bar_time_str, map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)


def _detect_swings_right_side(
    highs,
    lows,
    is_ghost,
    length: int,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Detect swing points using LuxAlgo's right-side N-bar pivot algorithm.

    Equivalent to the PineScript ``swings(len)`` function:
    - ``upper = ta.highest(len)`` → highest high of the last ``len`` bars [0..len-1]
    - If ``high[len] > upper``, bar[len] is a swing high candidate
    - State variable ``os`` prevents re-firing until opposite swing occurs

    This is a **right-side pivot**: checks if bar[N] is higher than all N bars
    to its right (bars 0 to N-1 in PineScript's lookback notation).

    Args:
        highs: Array of high prices.
        lows: Array of low prices.
        is_ghost: Array of ghost bar flags.
        length: Pivot length (e.g., 5 for internal, 50 for swing).

    Returns:
        Tuple of (swing_highs, swing_lows), each a list of (bar_index, price).
        The bar_index is the actual index of the swing point bar.
    """
    n = len(highs)
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    # os (oscillator state): 0 = last swing was high, 1 = last swing was low
    # Initialized to -1 to indicate no state yet
    os_state = -1

    for i in range(length, n):
        # The candidate bar is at index (i - length) in the original sense,
        # but in PineScript: bar[len] is `length` bars back from current bar `i`.
        # high[len] = highs[i - length]
        # ta.highest(len) = max(highs[i - length + 1], ..., highs[i])
        # i.e. the highest of the `length` bars AFTER the candidate bar.

        candidate_idx = i - length

        # Skip ghost bars as candidates
        if is_ghost[candidate_idx]:
            continue

        # Compute rolling max/min of the `length` bars AFTER the candidate
        # These are bars [candidate_idx+1 .. candidate_idx+length] = bars [i-length+1 .. i]
        window_highs = highs[candidate_idx + 1: i + 1]
        window_lows = lows[candidate_idx + 1: i + 1]

        upper = max(window_highs) if len(window_highs) > 0 else 0
        lower = min(window_lows) if len(window_lows) > 0 else float("inf")

        # Determine new state
        new_os = os_state
        if highs[candidate_idx] > upper:
            new_os = 0  # swing high territory
        elif lows[candidate_idx] < lower:
            new_os = 1  # swing low territory

        # Swing high: transition INTO state 0 (from non-0)
        if new_os == 0 and os_state != 0:
            swing_highs.append((candidate_idx, highs[candidate_idx]))

        # Swing low: transition INTO state 1 (from non-1)
        if new_os == 1 and os_state != 1:
            swing_lows.append((candidate_idx, lows[candidate_idx]))

        os_state = new_os

    return swing_highs, swing_lows


class LuxAlgoMSSDetector(PrimitiveDetector):
    """LuxAlgo-inspired BOS/CHoCH detector for MSS primitive.

    Clean-room implementation based on algorithm description.
    Registered as (mss, luxalgo_v1).

    No upstream dependencies — performs its own inline swing detection
    using the right-side N-bar pivot algorithm.
    """

    primitive_name = "mss"
    variant_name = "luxalgo_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        """No upstream dependencies — swing detection is inline."""
        return []

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, "DetectionResult"]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run BOS/CHoCH detection on bars.

        Args:
            bars: DataFrame with bar contract columns.
            params: Config params:
                - internal_length (int): Pivot length for internal structure (default 5).
                - swing_length (int): Pivot length for swing structure (default 50).
                - confluence_filter (bool): Optional candle shape filter (default False).
            context: Must contain 'timeframe' key.

        Returns:
            DetectionResult with BOS/CHoCH detections, variant='luxalgo_v1'.
        """
        tf = (context or {}).get("timeframe", "5m")
        tf_minutes = TF_MINUTES.get(tf, 5)
        n = len(bars)

        internal_length = params.get("internal_length", 5)
        swing_length = params.get("swing_length", 50)

        # Extract arrays
        highs = bars["high"].values
        lows = bars["low"].values
        closes = bars["close"].values
        is_ghost = bars["is_ghost"].values
        ts_ny_series = bars["timestamp_ny"]
        sessions = bars["session"].values
        forex_days = bars["forex_day"].values

        # Detect swings at both levels
        int_sh, int_sl = _detect_swings_right_side(highs, lows, is_ghost, internal_length)
        swing_sh, swing_sl = _detect_swings_right_side(highs, lows, is_ghost, swing_length)

        # Run BOS/CHoCH detection for each level
        all_detections: list[Detection] = []

        int_dets = self._detect_breaks(
            highs, lows, closes, is_ghost, ts_ny_series, sessions, forex_days,
            int_sh, int_sl, "internal", tf, tf_minutes,
        )
        all_detections.extend(int_dets)

        swing_dets = self._detect_breaks(
            highs, lows, closes, is_ghost, ts_ny_series, sessions, forex_days,
            swing_sh, swing_sl, "swing", tf, tf_minutes,
        )
        all_detections.extend(swing_dets)

        # Sort all detections by time
        all_detections.sort(key=lambda d: d.time)

        # Build metadata
        bos_count = sum(1 for d in all_detections if d.properties["break_type"] == "BOS")
        choch_count = sum(1 for d in all_detections if d.properties["break_type"] == "CHoCH")
        bull_count = sum(1 for d in all_detections if d.direction == "bullish")
        bear_count = sum(1 for d in all_detections if d.direction == "bearish")
        internal_count = sum(1 for d in all_detections if d.properties["structure_level"] == "internal")
        swing_count = sum(1 for d in all_detections if d.properties["structure_level"] == "swing")

        metadata = {
            "total_count": len(all_detections),
            "bos_count": bos_count,
            "choch_count": choch_count,
            "bullish_count": bull_count,
            "bearish_count": bear_count,
            "internal_count": internal_count,
            "swing_count": swing_count,
        }

        return DetectionResult(
            primitive="mss",
            variant="luxalgo_v1",
            timeframe=tf,
            detections=all_detections,
            metadata=metadata,
            params_used=dict(params),
        )

    def _detect_breaks(
        self,
        highs,
        lows,
        closes,
        is_ghost,
        ts_ny_series,
        sessions,
        forex_days,
        swing_highs: list[tuple[int, float]],
        swing_lows: list[tuple[int, float]],
        structure_level: str,
        tf: str,
        tf_minutes: int,
    ) -> list[Detection]:
        """Detect BOS/CHoCH breaks at a given structure level.

        Implements the LuxAlgo BOS/CHoCH classification:
        - Tracks the most recent unfired swing high and swing low.
        - When close crosses above a swing high → bullish break.
        - When close crosses below a swing low → bearish break.
        - BOS if the break continues the existing trend.
        - CHoCH if the break reverses the existing trend.
        - Trend flips on CHoCH, stays on BOS.

        Each swing is consumed once (one-shot via ``top_cross`` / ``btm_cross`` flags).

        Args:
            highs, lows, closes: Price arrays.
            is_ghost: Ghost bar flags.
            ts_ny_series: Timestamp series.
            sessions, forex_days: Session/day tags.
            swing_highs: List of (bar_index, price) for swing highs.
            swing_lows: List of (bar_index, price) for swing lows.
            structure_level: "internal" or "swing".
            tf: Timeframe string.
            tf_minutes: Timeframe in minutes.

        Returns:
            List of Detection objects.
        """
        n = len(closes)
        detections: list[Detection] = []

        # Trend state: 0 = undetermined, 1 = bullish, -1 = bearish
        trend = 0

        # Track the "active" (unconsumed) swing high and low
        # These are the most recent swing that hasn't been broken yet
        active_sh_price: Optional[float] = None
        active_sh_idx: Optional[int] = None
        active_sh_consumed = True  # True = no active swing high to break

        active_sl_price: Optional[float] = None
        active_sl_idx: Optional[int] = None
        active_sl_consumed = True  # True = no active swing low to break

        # Index into swing_highs and swing_lows lists
        sh_ptr = 0
        sl_ptr = 0

        for i in range(n):
            if is_ghost[i]:
                continue

            # Check if any new swing highs are now "confirmed" (their bar_index < i)
            # A swing at bar_index B is confirmed once we've processed enough
            # bars after B. But in the LuxAlgo model, swings are detected at
            # bar[candidate] when bar i = candidate + length. Since we pre-computed
            # all swings, we just activate them when the current bar passes them.
            while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][0] < i:
                active_sh_idx, active_sh_price = swing_highs[sh_ptr]
                active_sh_consumed = False
                sh_ptr += 1

            while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][0] < i:
                active_sl_idx, active_sl_price = swing_lows[sl_ptr]
                active_sl_consumed = False
                sl_ptr += 1

            # Check bullish break: close crosses above active swing high
            if not active_sh_consumed and active_sh_price is not None:
                # ta.crossover: close[i] > level AND close[i-1] <= level
                if i > 0 and closes[i] > active_sh_price and closes[i - 1] <= active_sh_price:
                    # Determine BOS vs CHoCH
                    if trend <= 0:
                        # Trend was bearish or undetermined → CHoCH (reversal)
                        break_type = "CHoCH" if trend < 0 else "BOS"
                    else:
                        # Trend was bullish → BOS (continuation)
                        break_type = "BOS"

                    # For the very first break with undetermined trend, call it BOS
                    if trend == 0:
                        break_type = "BOS"

                    # Update trend
                    new_trend = 1  # bullish
                    trend_state_label = "bullish"

                    bar_time = bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                    bar_session = map_session(sessions[i])

                    det_id = make_detection_id(
                        primitive="mss",
                        timeframe=tf,
                        timestamp_ny=pd.Timestamp(bar_time),
                        direction="bullish",
                    )

                    detection = Detection(
                        id=det_id,
                        time=pd.Timestamp(bar_time),
                        direction="bullish",
                        type="mss",
                        price=active_sh_price,
                        properties={
                            "break_type": break_type,
                            "structure_level": structure_level,
                            "trend_state": trend_state_label,
                            "bar_index": i,
                            "broken_swing": {
                                "type": "SwingHigh",
                                "price": active_sh_price,
                                "bar_index": active_sh_idx,
                            },
                        },
                        tags={
                            "session": bar_session,
                            "forex_day": forex_days[i],
                        },
                    )
                    detections.append(detection)

                    # Consume the swing (one-shot)
                    active_sh_consumed = True
                    trend = new_trend

            # Check bearish break: close crosses below active swing low
            if not active_sl_consumed and active_sl_price is not None:
                # ta.crossunder: close[i] < level AND close[i-1] >= level
                if i > 0 and closes[i] < active_sl_price and closes[i - 1] >= active_sl_price:
                    # Determine BOS vs CHoCH
                    if trend >= 0:
                        # Trend was bullish or undetermined → CHoCH (reversal)
                        break_type = "CHoCH" if trend > 0 else "BOS"
                    else:
                        # Trend was bearish → BOS (continuation)
                        break_type = "BOS"

                    # For the very first break with undetermined trend, call it BOS
                    if trend == 0:
                        break_type = "BOS"

                    # Update trend
                    new_trend = -1  # bearish
                    trend_state_label = "bearish"

                    bar_time = bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                    bar_session = map_session(sessions[i])

                    det_id = make_detection_id(
                        primitive="mss",
                        timeframe=tf,
                        timestamp_ny=pd.Timestamp(bar_time),
                        direction="bearish",
                    )

                    detection = Detection(
                        id=det_id,
                        time=pd.Timestamp(bar_time),
                        direction="bearish",
                        type="mss",
                        price=active_sl_price,
                        properties={
                            "break_type": break_type,
                            "structure_level": structure_level,
                            "trend_state": trend_state_label,
                            "bar_index": i,
                            "broken_swing": {
                                "type": "SwingLow",
                                "price": active_sl_price,
                                "bar_index": active_sl_idx,
                            },
                        },
                        tags={
                            "session": bar_session,
                            "forex_day": forex_days[i],
                        },
                    )
                    detections.append(detection)

                    # Consume the swing (one-shot)
                    active_sl_consumed = True
                    trend = new_trend

        return detections
