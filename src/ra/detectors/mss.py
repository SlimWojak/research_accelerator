"""MSS (Market Structure Shift) detector — composite consuming swing + displacement + FVG.

Implements:
- Close beyond prior swing WITH displacement on break bar or within confirmation window
- Confirmation window: 3 bars (LTF), 1 bar (HTF)
- Impulse suppression: prevents same-direction re-fire until reset
- Reset triggers: pullback > max(5 pips, 0.25*ATR), opposite displacement, new forex day
- Swing consumption: each swing consumed once (no re-break)
- FVG presence tagged but not gated (fvg_tag_only=true)
- Break classification: REVERSAL or CONTINUATION (internal tag)

Reference: pipeline/preprocess_data_v2.py detect_mss() function.
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import PIP, TF_MINUTES, bar_time_str, compute_atr, map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)



# _compute_atr extracted to ra.detectors._common.compute_atr


def _find_displacement_in_window(
    break_idx: int,
    n_bars: int,
    disp_by_idx: dict[int, dict],
    direction: str,
    window: int,
) -> Optional[dict]:
    """Search for displacement in same direction within confirmation window.

    Also checks 1 bar back — a cluster starting at break_idx-1 whose second bar
    is the break bar is a valid displacement for this break.

    Matches pipeline _find_displacement_in_window() exactly.
    """
    search_start = max(0, break_idx - 1)
    for k in range(search_start, min(break_idx + window + 1, n_bars)):
        disp = disp_by_idx.get(k)
        if disp and disp["direction"] == direction:
            disp_end = disp.get("bar_index_end", disp["bar_index"])
            if disp_end >= break_idx or k >= break_idx:
                return disp
    return None


class MSSDetector(PrimitiveDetector):
    """MSS detector: close beyond swing + displacement confirmation.

    Composite detector consuming swing_points, displacement, and fvg upstream.
    """

    primitive_name = "mss"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        return ["swing_points", "displacement", "fvg"]

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run MSS detection on bars using upstream swing/displacement/fvg results.

        Args:
            bars: DataFrame with bar contract columns.
            params: MSS config params (ltf/htf/fvg_tag_only/etc.).
            upstream: Dict with 'swing_points', 'displacement', 'fvg' DetectionResults.
            context: Must contain 'timeframe' key.

        Returns:
            DetectionResult with MSS detections.
        """
        if upstream is None:
            raise ValueError("MSSDetector requires upstream results (swing_points, displacement, fvg)")

        tf = context.get("timeframe", "5m") if context else "5m"
        tf_minutes = TF_MINUTES.get(tf, 5)
        n = len(bars)

        # Determine LTF vs HTF params
        ltf_applies = params.get("ltf", {}).get("applies_to", ["1m", "5m", "15m"])
        htf_applies = params.get("htf", {}).get("applies_to", ["1H", "4H", "1D"])

        if tf in ltf_applies:
            tf_params = params["ltf"]
        elif tf in htf_applies:
            tf_params = params["htf"]
        else:
            tf_params = params["ltf"]  # default to LTF

        confirmation_window = tf_params.get("confirmation_window_bars", 3)
        suppression_cfg = tf_params.get("impulse_suppression", {})
        pullback_pips = suppression_cfg.get("pullback_reset_pips", 5)
        pullback_atr_factor = suppression_cfg.get("pullback_reset_atr_factor", 0.25)
        opp_disp_reset = suppression_cfg.get("opposite_displacement_reset", True)
        new_day_reset = suppression_cfg.get("new_day_reset", True)

        # Extract upstream data
        swing_result = upstream["swing_points"]
        disp_result = upstream["displacement"]
        fvg_result = upstream["fvg"]

        # Build swing lists sorted by bar_index
        # Note: Swing Detection objects store price in Detection.price,
        # and bar_index/time in Detection.properties
        swing_highs = sorted(
            [d for d in swing_result.detections if d.direction == "high"],
            key=lambda d: d.properties["bar_index"],
        )
        swing_lows = sorted(
            [d for d in swing_result.detections if d.direction == "low"],
            key=lambda d: d.properties["bar_index"],
        )

        # Build displacement lookup by bar_index
        # Pipeline uses disp_key = 'atr1.5_br0.6' and checks .and or .override
        disp_key = "atr1.5_br0.6"
        disp_by_idx: dict[int, dict] = {}
        for d in disp_result.detections:
            props = d.properties
            q = props.get("qualifies", {}).get(disp_key, {})
            if q.get("and") or q.get("override"):
                disp_by_idx[props["bar_index"]] = props
                end_idx = props.get("bar_index_end")
                if end_idx is not None and end_idx != props["bar_index"]:
                    disp_by_idx[end_idx] = props

        # Build FVG bar index set (bar_index - 1 = the displacement bar that created FVG)
        fvg_bar_indices: set[int] = set()
        for f in fvg_result.detections:
            if f.properties.get("gap_pips", 0) >= 0.5:
                fvg_bar_indices.add(f.properties["bar_index"] - 1)

        # Compute ATR for suppression
        atrs = compute_atr(bars, period=14)

        # Extract bar arrays for efficient access
        closes = bars["close"].values
        highs = bars["high"].values
        lows = bars["low"].values
        is_ghost = bars["is_ghost"].values
        forex_days = bars["forex_day"].values
        sessions = bars["session"].values
        ts_ny_series = bars["timestamp_ny"]

        mss_events: list[dict] = []
        suppression: Optional[dict] = None
        broken_swings: set[tuple] = set()

        for i in range(1, n):
            # Skip ghost bars
            if is_ghost[i]:
                continue

            # Suppression check
            if suppression is not None:
                if i <= suppression.get("suppress_until", suppression["start_idx"]):
                    continue

                atr_at = atrs[i] if i < len(atrs) and atrs[i] is not None else 0
                min_pb = max(pullback_pips * PIP, pullback_atr_factor * atr_at)
                reset = False

                if suppression["direction"] == "BULLISH":
                    retrace = suppression["extreme_price"] - lows[i]
                    if retrace >= min_pb:
                        reset = True
                    if highs[i] > suppression["extreme_price"]:
                        suppression["extreme_price"] = highs[i]
                else:
                    retrace = highs[i] - suppression["extreme_price"]
                    if retrace >= min_pb:
                        reset = True
                    if lows[i] < suppression["extreme_price"]:
                        suppression["extreme_price"] = lows[i]

                # Opposite displacement reset
                if opp_disp_reset:
                    opp_disp = disp_by_idx.get(i)
                    if opp_disp and opp_disp["direction"] != suppression["direction"].lower():
                        reset = True

                # New forex day reset
                if new_day_reset:
                    if forex_days[i] != suppression.get("forex_day"):
                        reset = True

                if reset:
                    suppression = None
                else:
                    continue

            # Find most recent swings before this bar
            recent_sh = None
            for s in reversed(swing_highs):
                if s.properties["bar_index"] < i:
                    recent_sh = s
                    break

            recent_sl = None
            for s in reversed(swing_lows):
                if s.properties["bar_index"] < i:
                    recent_sl = s
                    break

            # Check bullish break: close > prior swing high
            if recent_sh and closes[i] > recent_sh.price:
                sh_props = recent_sh.properties
                sh_bar_idx = sh_props["bar_index"]
                swing_id = ("high", sh_bar_idx)
                if swing_id not in broken_swings:
                    confirmed_disp = _find_displacement_in_window(
                        i, n, disp_by_idx, "bullish", confirmation_window,
                    )
                    if confirmed_disp:
                        broken_swings.add(swing_id)
                        disp = confirmed_disp

                        # Determine break type: REVERSAL if prior trend was bearish
                        trend_lows = [s for s in swing_lows if s.properties["bar_index"] < sh_bar_idx]
                        trend_highs = [s for s in swing_highs if s.properties["bar_index"] < sh_bar_idx]
                        prior_bearish = (
                            len(trend_highs) >= 2
                            and len(trend_lows) >= 2
                            and trend_highs[-1].price < trend_highs[-2].price
                        )

                        disp_end = disp.get("bar_index_end", disp["bar_index"])
                        bar_time = bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                        bar_session = map_session(sessions[i])

                        # Check FVG created by displacement
                        fvg_created = any(
                            k in fvg_bar_indices
                            for k in range(disp["bar_index"], disp_end + 1)
                        )

                        event = {
                            "direction": "BULLISH",
                            "break_type": "REVERSAL" if prior_bearish else "CONTINUATION",
                            "bar_index": i,
                            "time": bar_time,
                            "window_used": disp["bar_index"] - i,
                            "broken_swing": {
                                "type": "SwingHigh",
                                "price": recent_sh.price,
                                "time": sh_props["time"],
                                "bar_index": sh_bar_idx,
                            },
                            "displacement": {
                                "atr_multiple": disp["atr_multiple"],
                                "body_ratio": disp["body_ratio"],
                                "quality_grade": disp.get("quality_grade", "VALID"),
                                "path": disp.get("qualification_path", "ATR_RELATIVE"),
                                "displacement_type": disp.get("displacement_type", "SINGLE"),
                            },
                            "fvg_created": fvg_created,
                            "forex_day": forex_days[i],
                            "session": bar_session,
                            "tf": tf,
                        }
                        mss_events.append(event)

                        # Set up suppression
                        suppress_end = max(i, disp_end)
                        high_range = range(i, min(suppress_end + 1, n))
                        suppression = {
                            "direction": "BULLISH",
                            "extreme_price": max(highs[k] for k in high_range) if high_range else highs[i],
                            "start_idx": i,
                            "suppress_until": suppress_end,
                            "forex_day": forex_days[i],
                        }
                        continue
                    else:
                        broken_swings.add(swing_id)

            # Check bearish break: close < prior swing low
            if recent_sl and closes[i] < recent_sl.price:
                sl_props = recent_sl.properties
                sl_bar_idx = sl_props["bar_index"]
                swing_id = ("low", sl_bar_idx)
                if swing_id not in broken_swings:
                    confirmed_disp = _find_displacement_in_window(
                        i, n, disp_by_idx, "bearish", confirmation_window,
                    )
                    if confirmed_disp:
                        broken_swings.add(swing_id)
                        disp = confirmed_disp

                        # Determine break type: REVERSAL if prior trend was bullish
                        trend_highs = [s for s in swing_highs if s.properties["bar_index"] < sl_bar_idx]
                        trend_lows = [s for s in swing_lows if s.properties["bar_index"] < sl_bar_idx]
                        prior_bullish = (
                            len(trend_lows) >= 2
                            and len(trend_highs) >= 2
                            and trend_lows[-1].price > trend_lows[-2].price
                        )

                        disp_end = disp.get("bar_index_end", disp["bar_index"])
                        bar_time = bar_time_str(ts_ny_series.iloc[i], tf_minutes)
                        bar_session = map_session(sessions[i])

                        # Check FVG created by displacement
                        fvg_created = any(
                            k in fvg_bar_indices
                            for k in range(disp["bar_index"], disp_end + 1)
                        )

                        event = {
                            "direction": "BEARISH",
                            "break_type": "REVERSAL" if prior_bullish else "CONTINUATION",
                            "bar_index": i,
                            "time": bar_time,
                            "window_used": disp["bar_index"] - i,
                            "broken_swing": {
                                "type": "SwingLow",
                                "price": recent_sl.price,
                                "time": sl_props["time"],
                                "bar_index": sl_bar_idx,
                            },
                            "displacement": {
                                "atr_multiple": disp["atr_multiple"],
                                "body_ratio": disp["body_ratio"],
                                "quality_grade": disp.get("quality_grade", "VALID"),
                                "path": disp.get("qualification_path", "ATR_RELATIVE"),
                                "displacement_type": disp.get("displacement_type", "SINGLE"),
                            },
                            "fvg_created": fvg_created,
                            "forex_day": forex_days[i],
                            "session": bar_session,
                            "tf": tf,
                        }
                        mss_events.append(event)

                        # Set up suppression
                        suppress_end = max(i, disp_end)
                        low_range = range(i, min(suppress_end + 1, n))
                        suppression = {
                            "direction": "BEARISH",
                            "extreme_price": min(lows[k] for k in low_range) if low_range else lows[i],
                            "start_idx": i,
                            "suppress_until": suppress_end,
                            "forex_day": forex_days[i],
                        }
                        continue
                    else:
                        broken_swings.add(swing_id)

        # Build Detection objects
        detections = []
        for event in mss_events:
            det_time = pd.Timestamp(event["time"])
            dir_map = {"BULLISH": "bullish", "BEARISH": "bearish"}
            det_direction = dir_map.get(event["direction"], event["direction"].lower())
            det_id = make_detection_id(
                primitive="mss",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=det_direction,
            )

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=det_direction,
                type="mss",
                price=event["broken_swing"]["price"],
                properties=event,
                tags={
                    "session": event["session"],
                    "forex_day": event["forex_day"],
                },
            )
            detections.append(detection)

        # Build metadata
        rev_count = sum(1 for e in mss_events if e["break_type"] == "REVERSAL")
        cont_count = sum(1 for e in mss_events if e["break_type"] == "CONTINUATION")
        fvg_count = sum(1 for e in mss_events if e["fvg_created"])
        bull_count = sum(1 for e in mss_events if e["direction"] == "BULLISH")
        bear_count = sum(1 for e in mss_events if e["direction"] == "BEARISH")

        metadata = {
            "total_count": len(detections),
            "reversal_count": rev_count,
            "continuation_count": cont_count,
            "fvg_tagged_count": fvg_count,
            "bullish_count": bull_count,
            "bearish_count": bear_count,
        }

        return DetectionResult(
            primitive="mss",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )
