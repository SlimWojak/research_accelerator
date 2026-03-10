"""LuxAlgo-inspired Order Block (OB) detector — clean-room implementation.

Implements Order Block detection inspired by LuxAlgo Smart Money Concepts.
Key differences from a8ra_v1 OrderBlockDetector:

1. **Anchor candle selection**: Most extreme candle in the structure interval
   (not last opposing candle before MSS bar). For bearish OB: highest high.
   For bullish OB: lowest low.
2. **ATR filter on anchor**: Candle range must be < ATR × multiplier
   (default 2.0). Removes volatile candles from consideration.
3. **Zone uses full candle range**: wick-to-wick (not body-only).
   zone_high = anchor candle high, zone_low = anchor candle low.
4. **Mitigation on touch**: Price touching the zone boundary → MITIGATED.
5. **Invalidation on close through opposite side**: Close penetrates through
   the opposite side of the zone → INVALIDATED. Invalidated OBs are terminal.

Reference: .factory/research/luxalgo-smc-analysis.md section 3.
License: Clean-room implementation (CC BY-NC-SA 4.0 compliance).
Registered as: (order_block, luxalgo_v1).
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import TF_MINUTES, bar_time_str, compute_atr, map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)


class LuxAlgoOBDetector(PrimitiveDetector):
    """LuxAlgo-inspired Order Block detector.

    Composite detector consuming upstream LuxAlgo MSS (BOS/CHoCH) results.
    Creates an order block zone for each structure break event, using the
    most extreme candle in the structure interval as the anchor.

    Registered as (order_block, luxalgo_v1).
    """

    primitive_name = "order_block"
    variant_name = "luxalgo_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        return ["mss"]

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run OB detection on bars using upstream LuxAlgo MSS results.

        Args:
            bars: DataFrame with bar contract columns.
            params: OB config params:
                - atr_period (int): ATR period for filtering (default 14).
                - atr_filter_multiplier (float): Candle range must be
                  < ATR × this value (default 2.0).
            upstream: Dict with 'mss' DetectionResult from LuxAlgo MSS.
            context: Must contain 'timeframe' key.

        Returns:
            DetectionResult with OB detections, variant='luxalgo_v1'.
        """
        if upstream is None:
            raise ValueError(
                "LuxAlgoOBDetector requires upstream results (mss)"
            )

        tf = (context or {}).get("timeframe", "5m")
        tf_minutes = TF_MINUTES.get(tf, 5)
        n = len(bars)

        # Extract config
        atr_period = params.get("atr_period", 14)
        atr_multiplier = params.get("atr_filter_multiplier", 2.0)

        # Extract upstream MSS events
        mss_result = upstream["mss"]

        # Extract bar arrays for efficient access
        opens = bars["open"].values
        closes = bars["close"].values
        highs = bars["high"].values
        lows = bars["low"].values
        is_ghost = bars["is_ghost"].values
        sessions = bars["session"].values
        forex_days = bars["forex_day"].values
        ts_ny_series = bars["timestamp_ny"]

        # Compute ATR for the entire bar series
        atrs = compute_atr(bars, atr_period)

        detections: list[Detection] = []

        for mss_det in mss_result.detections:
            mss_props = mss_det.properties
            mss_bar_index = mss_props["bar_index"]
            direction = mss_det.direction  # "bullish" or "bearish"
            broken_swing = mss_props.get("broken_swing", {})
            swing_bar_index = broken_swing.get("bar_index")

            if swing_bar_index is None:
                logger.debug(
                    "MSS detection %s has no broken_swing.bar_index, skipping OB.",
                    mss_det.id,
                )
                continue

            # The structure interval is from the swing bar to the MSS bar.
            # We scan this interval to find the extreme candle.
            # LuxAlgo scans from bar 1 to (n - loc) - 1 where n = current bar,
            # loc = swing bar. In our terms: from swing_bar_index+1 to mss_bar_index-1.
            interval_start = swing_bar_index + 1
            interval_end = mss_bar_index  # exclusive

            if interval_start >= interval_end:
                # No bars in the structure interval
                logger.debug(
                    "Empty structure interval [%d, %d) for MSS %s, skipping OB.",
                    interval_start, interval_end, mss_det.id,
                )
                continue

            # Find the extreme candle in the interval with ATR filter
            anchor_idx = self._find_anchor(
                highs, lows, is_ghost, atrs,
                interval_start, interval_end,
                direction, atr_multiplier,
            )

            if anchor_idx is None:
                # No candle passed the ATR filter
                logger.debug(
                    "No valid anchor in [%d, %d) for MSS %s (ATR filter), "
                    "skipping OB.",
                    interval_start, interval_end, mss_det.id,
                )
                continue

            # Build zone: wick-to-wick (full candle range)
            zone_high = highs[anchor_idx]
            zone_low = lows[anchor_idx]

            # Determine OB lifecycle state by scanning forward
            state, mitigation_bar, invalidation_bar = self._compute_lifecycle(
                highs, lows, closes, is_ghost,
                anchor_idx, n,
                zone_high, zone_low,
                direction,
            )

            # Build OB time
            ob_time = bar_time_str(ts_ny_series.iloc[anchor_idx], tf_minutes)

            # Build Detection
            det_id = make_detection_id(
                primitive="ob",
                timeframe=tf,
                timestamp_ny=pd.Timestamp(ob_time),
                direction=direction,
            )

            properties = {
                "zone_high": zone_high,
                "zone_low": zone_low,
                "anchor_bar_index": anchor_idx,
                "anchor_time": ob_time,
                "mss_bar_index": mss_bar_index,
                "mss_time": bar_time_str(ts_ny_series.iloc[mss_bar_index], tf_minutes),
                "direction": direction,
                "state": state,
                "break_type": mss_props.get("break_type", "BOS"),
                "structure_level": mss_props.get("structure_level", "internal"),
                "broken_swing": broken_swing,
                "forex_day": forex_days[anchor_idx],
                "tf": tf,
            }

            if mitigation_bar is not None:
                properties["mitigation_bar_index"] = mitigation_bar
                properties["mitigation_time"] = bar_time_str(
                    ts_ny_series.iloc[mitigation_bar], tf_minutes
                )

            if invalidation_bar is not None:
                properties["invalidation_bar_index"] = invalidation_bar
                properties["invalidation_time"] = bar_time_str(
                    ts_ny_series.iloc[invalidation_bar], tf_minutes
                )

            detection = Detection(
                id=det_id,
                time=pd.Timestamp(ob_time),
                direction=direction,
                type="order_block",
                price=zone_high if direction == "bearish" else zone_low,
                properties=properties,
                tags={
                    "session": map_session(sessions[anchor_idx]),
                    "forex_day": forex_days[anchor_idx],
                },
                upstream_refs=[mss_det.id],
            )
            detections.append(detection)

        # Build metadata
        bull_count = sum(1 for d in detections if d.direction == "bullish")
        bear_count = sum(1 for d in detections if d.direction == "bearish")
        state_counts = {}
        for d in detections:
            s = d.properties["state"]
            state_counts[s] = state_counts.get(s, 0) + 1

        metadata = {
            "total_count": len(detections),
            "bullish_count": bull_count,
            "bearish_count": bear_count,
            "state_counts": state_counts,
        }

        return DetectionResult(
            primitive="order_block",
            variant="luxalgo_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )

    @staticmethod
    def _find_anchor(
        highs,
        lows,
        is_ghost,
        atrs: list,
        interval_start: int,
        interval_end: int,
        direction: str,
        atr_multiplier: float,
    ) -> Optional[int]:
        """Find the most extreme candle in the structure interval with ATR filter.

        For **bullish OB**: find the candle with the **lowest low** in the interval.
        For **bearish OB**: find the candle with the **highest high** in the interval.

        Only considers candles where ``range < ATR × atr_multiplier`` (filters
        out overly volatile candles).

        Args:
            highs, lows: Price arrays.
            is_ghost: Ghost bar flags.
            atrs: Pre-computed ATR values (None for insufficient data).
            interval_start: Start index (inclusive).
            interval_end: End index (exclusive).
            direction: "bullish" or "bearish".
            atr_multiplier: ATR filter multiplier (default 2.0).

        Returns:
            Index of the anchor candle, or None if no valid candle found.
        """
        best_idx = None
        best_value = None

        for i in range(interval_start, interval_end):
            if is_ghost[i]:
                continue

            candle_range = highs[i] - lows[i]

            # ATR filter: candle range must be < ATR × multiplier
            atr_val = atrs[i] if i < len(atrs) else None
            if atr_val is not None and candle_range >= atr_val * atr_multiplier:
                continue

            if direction == "bullish":
                # Bullish OB: find lowest low
                if best_value is None or lows[i] < best_value:
                    best_value = lows[i]
                    best_idx = i
            else:
                # Bearish OB: find highest high
                if best_value is None or highs[i] > best_value:
                    best_value = highs[i]
                    best_idx = i

        return best_idx

    @staticmethod
    def _compute_lifecycle(
        highs,
        lows,
        closes,
        is_ghost,
        anchor_idx: int,
        n: int,
        zone_high: float,
        zone_low: float,
        direction: str,
    ) -> tuple[str, Optional[int], Optional[int]]:
        """Compute the OB lifecycle state by scanning forward from the anchor.

        Mitigation: price *touches* the zone boundary.
        - Bullish OB: low touches zone_high (price comes down to the zone)
        - Bearish OB: high touches zone_low (price comes up to the zone)

        Invalidation: close penetrates through the opposite side.
        - Bullish OB: close < zone_low (price closes below the zone)
        - Bearish OB: close > zone_high (price closes above the zone)

        Once invalidated, the OB is terminal (cannot be subsequently mitigated).

        Args:
            highs, lows, closes: Price arrays.
            is_ghost: Ghost bar flags.
            anchor_idx: Index of the OB anchor candle.
            n: Total number of bars.
            zone_high, zone_low: OB zone boundaries.
            direction: "bullish" or "bearish".

        Returns:
            Tuple of (state, mitigation_bar_index, invalidation_bar_index).
            state is one of "ACTIVE", "MITIGATED", "INVALIDATED".
        """
        state = "ACTIVE"
        mitigation_bar: Optional[int] = None
        invalidation_bar: Optional[int] = None

        for j in range(anchor_idx + 1, n):
            if is_ghost[j]:
                continue

            if direction == "bullish":
                # Mitigation: price touches the OB zone (low taps zone_high)
                if state == "ACTIVE" and lows[j] <= zone_high:
                    state = "MITIGATED"
                    mitigation_bar = j

                # Invalidation: close below zone_low
                if closes[j] < zone_low:
                    state = "INVALIDATED"
                    invalidation_bar = j
                    break  # Terminal state

            else:  # bearish
                # Mitigation: price touches the OB zone (high taps zone_low)
                if state == "ACTIVE" and highs[j] >= zone_low:
                    state = "MITIGATED"
                    mitigation_bar = j

                # Invalidation: close above zone_high
                if closes[j] > zone_high:
                    state = "INVALIDATED"
                    invalidation_bar = j
                    break  # Terminal state

        return state, mitigation_bar, invalidation_bar
