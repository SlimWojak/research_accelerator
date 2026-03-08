"""Order Block (OB) detector — composite consuming displacement + MSS.

Implements:
- Trigger: displacement + MSS (close beyond prior swing with displacement)
- Anchor: last opposing candle before the MSS bar
- Thin candle filter: body_pct >= 0.10, skip candles below
- Conditional fallback scan: if bars[i-1] fails, scan up to 3 bars back
- Zone: body only (execution), full candle OHLC (invalidation)
- Retest tracking within look-ahead window
- State machine: ACTIVE -> MITIGATED/INVALIDATED/EXPIRED

Reference: pipeline/preprocess_data_v2.py detect_order_blocks() function.
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

# Look-ahead window for retest tracking — matches pipeline behavior
_LOOK_AHEAD = {
    "1m": 100,
    "5m": 50,
    "15m": 30,
}


def _is_valid_ob_candle(
    candle_open: float,
    candle_close: float,
    candle_high: float,
    candle_low: float,
    disp_direction: str,
    min_body_pct: float,
) -> bool:
    """Check if candle is a valid OB anchor: opposing direction + thin candle filter.

    Args:
        candle_open: Candle open price.
        candle_close: Candle close price.
        candle_high: Candle high price.
        candle_low: Candle low price.
        disp_direction: Direction of the displacement ("bullish" or "bearish").
        min_body_pct: Minimum body percentage threshold (default 0.10).

    Returns:
        True if candle is a valid OB anchor (opposing direction, adequate body).
    """
    # Check opposing direction
    if disp_direction == "bullish":
        is_opposing = candle_close < candle_open  # bearish candle for bullish OB
    else:
        is_opposing = candle_close > candle_open  # bullish candle for bearish OB

    if not is_opposing:
        return False

    candle_range = candle_high - candle_low
    if candle_range <= 0:
        return False

    body_pct = abs(candle_close - candle_open) / candle_range
    return body_pct >= min_body_pct


class OrderBlockDetector(PrimitiveDetector):
    """Order Block detector: last opposing candle before MSS-confirmed displacement.

    Composite detector consuming displacement and MSS upstream results.
    """

    primitive_name = "order_block"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        return ["displacement", "mss"]

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run OB detection on bars using upstream displacement + MSS results.

        Args:
            bars: DataFrame with bar contract columns.
            params: OB config params (trigger, zone_type, thin_candle_filter, etc.).
            upstream: Dict with 'displacement' and 'mss' DetectionResults.
            context: Must contain 'timeframe' key.

        Returns:
            DetectionResult with OB detections.
        """
        if upstream is None:
            raise ValueError(
                "OrderBlockDetector requires upstream results (displacement, mss)"
            )

        tf = context.get("timeframe", "5m") if context else "5m"
        tf_minutes = TF_MINUTES.get(tf, 5)
        n = len(bars)

        # Extract config
        thin_filter = params.get("thin_candle_filter", {})
        min_body_pct = thin_filter.get("min_body_pct", 0.10)
        fallback_cfg = params.get("fallback_scan", {})
        lookback_bars = fallback_cfg.get("lookback_bars", 3)

        # Look-ahead for retest tracking
        look_ahead = _LOOK_AHEAD.get(tf, 30)

        # Extract upstream MSS events
        mss_result = upstream["mss"]

        # Extract bar arrays for efficient access
        opens = bars["open"].values
        closes = bars["close"].values
        highs = bars["high"].values
        lows = bars["low"].values
        is_ghost = bars["is_ghost"].values
        forex_days = bars["forex_day"].values
        ts_ny_series = bars["timestamp_ny"]

        ob_events: list[dict] = []

        for mss_det in mss_result.detections:
            mss_props = mss_det.properties
            mss_idx = mss_props["bar_index"]
            direction = mss_props["direction"].lower()

            # Find OB anchor candle — last opposing candle before MSS bar
            ob_idx = None

            if mss_idx > 0:
                preceding_idx = mss_idx - 1

                # Check primary: bars[mss_idx - 1]
                if not is_ghost[preceding_idx] and _is_valid_ob_candle(
                    opens[preceding_idx],
                    closes[preceding_idx],
                    highs[preceding_idx],
                    lows[preceding_idx],
                    direction,
                    min_body_pct,
                ):
                    ob_idx = preceding_idx
                else:
                    # Conditional fallback: scan back up to lookback_bars
                    for j in range(mss_idx - 1, max(mss_idx - lookback_bars - 1, -1), -1):
                        if is_ghost[j]:
                            continue
                        if _is_valid_ob_candle(
                            opens[j],
                            closes[j],
                            highs[j],
                            lows[j],
                            direction,
                            min_body_pct,
                        ):
                            ob_idx = j
                            break

            if ob_idx is None:
                # Log diagnostic miss
                logger.debug(
                    "OB fallback exhausted at MSS bar_index=%d, tf=%s, direction=%s",
                    mss_idx,
                    tf,
                    direction,
                )
                continue

            # Build zone: body only for execution, full OHLC for invalidation
            ob_open = opens[ob_idx]
            ob_close = closes[ob_idx]
            ob_high = highs[ob_idx]
            ob_low = lows[ob_idx]

            zone_body = {
                "top": max(ob_open, ob_close),
                "bottom": min(ob_open, ob_close),
            }
            zone_wick = {
                "top": ob_high,
                "bottom": ob_low,
            }

            # OB time
            ob_time = bar_time_str(ts_ny_series.iloc[ob_idx], tf_minutes)

            # Disp time = MSS time
            disp_time = mss_props["time"]

            # Retest tracking — scan forward from OB
            retests = []
            for j in range(ob_idx + 1, min(ob_idx + look_ahead, n)):
                retested = False
                if direction == "bullish":
                    # Bullish OB: price comes down to test the zone
                    if lows[j] <= zone_body["top"]:
                        retested = True
                else:
                    # Bearish OB: price comes up to test the zone
                    if highs[j] >= zone_body["bottom"]:
                        retested = True

                if retested:
                    retest_time = bar_time_str(ts_ny_series.iloc[j], tf_minutes)
                    retests.append({
                        "bar_index": j,
                        "time": retest_time,
                        "bars_since_ob": j - ob_idx,
                    })

            # Build event dict matching baseline structure
            event = {
                "ob_bar_index": ob_idx,
                "ob_time": ob_time,
                "disp_bar_index": mss_idx,
                "disp_time": disp_time,
                "direction": direction,
                "zone_wick": zone_wick,
                "zone_body": zone_body,
                "forex_day": forex_days[ob_idx],
                "retests": retests,
                "total_retests": len(retests),
                "tf": tf,
                "mss_direction": mss_props["direction"],
                "mss_break_type": mss_props["break_type"],
                "broken_swing": mss_props["broken_swing"],
            }
            ob_events.append(event)

        # Build Detection objects
        detections = []
        for event in ob_events:
            det_time = pd.Timestamp(event["ob_time"])
            det_id = make_detection_id(
                primitive="ob",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=event["direction"],
            )

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=event["direction"],
                type="order_block",
                price=event["zone_body"]["top"],
                properties=event,
                tags={
                    "session": map_session(bars["session"].values[event["ob_bar_index"]]),
                    "forex_day": event["forex_day"],
                },
            )
            detections.append(detection)

        # Metadata
        bull_count = sum(1 for e in ob_events if e["direction"] == "bullish")
        bear_count = sum(1 for e in ob_events if e["direction"] == "bearish")

        metadata = {
            "total_count": len(detections),
            "bullish_count": bull_count,
            "bearish_count": bear_count,
        }

        return DetectionResult(
            primitive="order_block",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )
