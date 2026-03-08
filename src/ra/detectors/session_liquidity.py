"""Session Liquidity detector — four-gate box classifier with interaction tracking.

Implements:
- Session box computation for asia, pre_london, pre_ny per forex day
- Four-gate classification: range cap, efficiency, mid_cross, balance
- CONSOLIDATION_BOX if all 4 gates pass, TREND_OR_EXPANSION if any fails
- Trend direction (UP/DOWN/null) for non-consolidation boxes
- Level interaction tracking (traded_above/below, closed_above/below)

Reference: pipeline/preprocess_data_v2.py compute_session_boxes() function.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

PIP = 0.0001

# Session box type -> session filter config
# Maps box type name to the session/hour filter criteria
_BOX_CONFIG = {
    "ASIA_BOX": {
        "filter_mode": "session",
        "session_name": "asia",
    },
    "PRE_LONDON_BOX": {
        "filter_mode": "hour",
        "hour_start": 0,
        "hour_end": 2,
    },
    "PRE_NY_BOX": {
        "filter_mode": "hour",
        "hour_start": 5,
        "hour_end": 7,
    },
}


def _filter_bars_for_box(day_bars: pd.DataFrame, box_type: str) -> pd.DataFrame:
    """Filter bars for a specific box type within a forex day."""
    cfg = _BOX_CONFIG[box_type]
    if cfg["filter_mode"] == "session":
        return day_bars[day_bars["session"] == cfg["session_name"]]
    else:
        hours = day_bars["timestamp_ny"].dt.hour
        return day_bars[(hours >= cfg["hour_start"]) & (hours < cfg["hour_end"])]


def _track_level_interactions(
    bars: pd.DataFrame,
    start_idx: int,
    forex_day: str,
    level: float,
) -> dict:
    """Track four raw price events against a single level.

    Scans bars from start_idx forward within the same forex_day.
    For each event type, records whether it occurred and the first time.

    Args:
        bars: Full 1m bar DataFrame (integer-indexed).
        start_idx: Index to start scanning from (after box end).
        forex_day: Only scan bars matching this forex day.
        level: Price level to track against.

    Returns:
        Dict with traded_above, traded_below, closed_above, closed_below events.
    """
    events = {
        "traded_above": {"occurred": False, "first_time": None},
        "traded_below": {"occurred": False, "first_time": None},
        "closed_above": {"occurred": False, "first_time": None},
        "closed_below": {"occurred": False, "first_time": None},
    }

    for i in range(start_idx, len(bars)):
        row = bars.iloc[i]
        if row["forex_day"] != forex_day:
            break

        bar_time = row["timestamp_ny"].strftime("%Y-%m-%dT%H:%M:%S")

        if not events["traded_above"]["occurred"] and row["high"] > level:
            events["traded_above"] = {"occurred": True, "first_time": bar_time}
        if not events["traded_below"]["occurred"] and row["low"] < level:
            events["traded_below"] = {"occurred": True, "first_time": bar_time}
        if not events["closed_above"]["occurred"] and row["close"] > level:
            events["closed_above"] = {"occurred": True, "first_time": bar_time}
        if not events["closed_below"]["occurred"] and row["close"] < level:
            events["closed_below"] = {"occurred": True, "first_time": bar_time}

        if all(v["occurred"] for v in events.values()):
            break

    return events


class SessionLiquidityDetector(PrimitiveDetector):
    """Four-gate session box classifier with interaction tracking.

    Gates (all must pass for CONSOLIDATION_BOX):
      1. range_pips <= range_cap (per session type)
      2. efficiency <= efficiency_threshold (0.60)
      3. mid_cross_count >= mid_cross_min (2)
      4. balance_score >= balance_score_min (0.30)

    If any gate fails: TREND_OR_EXPANSION with trend_direction UP/DOWN.
    """

    primitive_name = "session_liquidity"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Compute session boxes with four-gate classification.

        Args:
            bars: 1m bar DataFrame with session tagging.
            params: session_liquidity params from config.
            upstream: Not used (leaf detector).
            context: Optional context dict.

        Returns:
            DetectionResult with one Detection per session box.
        """
        four_gate = params.get("four_gate_model", {})
        eff_threshold = four_gate.get("efficiency_threshold", {}).get("locked", 0.60)
        mid_cross_min = four_gate.get("mid_cross_min", {}).get("locked", 2)
        balance_min = four_gate.get("balance_score_min", {}).get("locked", 0.30)

        box_objects = params.get("box_objects", {})
        range_caps = {
            "ASIA_BOX": box_objects.get("asia", {}).get("range_cap_pips", 30),
            "PRE_LONDON_BOX": box_objects.get("pre_london", {}).get("range_cap_pips", 15),
            "PRE_NY_BOX": box_objects.get("pre_ny", {}).get("range_cap_pips", 20),
        }

        forex_days = sorted(bars["forex_day"].unique())
        boxes = []

        for day in forex_days:
            day_mask = bars["forex_day"] == day
            day_bars = bars[day_mask]
            if day_bars.empty:
                continue

            # Get day end time for line_end
            day_end_time = day_bars.iloc[-1]["timestamp_ny"].strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            for box_type in ["ASIA_BOX", "PRE_LONDON_BOX", "PRE_NY_BOX"]:
                win_bars = _filter_bars_for_box(day_bars, box_type)
                if len(win_bars) < 3:
                    continue

                h = win_bars["high"].max()
                l = win_bars["low"].min()
                mid = (h + l) / 2
                rng = (h - l) / PIP
                net = abs(
                    win_bars.iloc[-1]["close"] - win_bars.iloc[0]["open"]
                ) / PIP
                eff = net / rng if rng > 0 else 0

                # Mid cross count
                mid_crosses = 0
                closes = win_bars["close"].values
                for i in range(1, len(closes)):
                    prev_c = closes[i - 1]
                    curr_c = closes[i]
                    if (prev_c < mid and curr_c > mid) or (
                        prev_c > mid and curr_c < mid
                    ):
                        mid_crosses += 1

                # Balance score
                above_mid = (win_bars["close"] > mid).sum()
                below_mid = (win_bars["close"] < mid).sum()
                total = len(win_bars)
                balance = (
                    min(above_mid / total, below_mid / total) if total > 0 else 0
                )

                # Four-gate classification
                is_consol = (
                    rng <= range_caps[box_type]
                    and eff <= eff_threshold
                    and mid_crosses >= mid_cross_min
                    and balance >= balance_min
                )
                classification = (
                    "CONSOLIDATION_BOX" if is_consol else "TREND_OR_EXPANSION"
                )

                trend_dir = None
                if not is_consol:
                    trend_dir = (
                        "UP"
                        if win_bars.iloc[-1]["close"] > win_bars.iloc[0]["open"]
                        else "DOWN"
                    )

                # Interaction tracking
                last_bar_pos = win_bars.index[-1]
                # Find the position in the full bars DataFrame
                scan_start = last_bar_pos + 1
                interactions = {"high": {}, "low": {}}
                if scan_start < len(bars):
                    interactions["high"] = _track_level_interactions(
                        bars, scan_start, day, h
                    )
                    interactions["low"] = _track_level_interactions(
                        bars, scan_start, day, l
                    )

                start_time = win_bars.iloc[0]["timestamp_ny"].strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                end_time = win_bars.iloc[-1]["timestamp_ny"].strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                box_data = {
                    "type": box_type,
                    "forex_day": day,
                    "start_time": start_time,
                    "end_time": end_time,
                    "high": h,
                    "low": l,
                    "mid": mid,
                    "range_pips": round(rng, 1),
                    "net_change_pips": round(net, 1),
                    "efficiency": round(eff, 3),
                    "mid_cross_count": mid_crosses,
                    "balance_score": round(balance, 3),
                    "classification": classification,
                    "trend_direction": trend_dir,
                    "interactions": interactions,
                    "line_end": day_end_time,
                }

                # Create Detection object
                box_time = win_bars.iloc[0]["timestamp_ny"].to_pydatetime()
                det_id = make_detection_id(
                    "session_liquidity",
                    "1m",
                    box_time,
                    "neutral",
                )
                detection = Detection(
                    id=det_id,
                    time=box_time,
                    direction="neutral",
                    type=box_type,
                    price=mid,
                    properties=box_data,
                    tags={
                        "forex_day": day,
                        "classification": classification,
                        "trend_direction": trend_dir,
                    },
                )
                boxes.append(detection)

        return DetectionResult(
            primitive="session_liquidity",
            variant="a8ra_v1",
            timeframe="1m",
            detections=boxes,
            metadata={
                "total_boxes": len(boxes),
                "consolidation_count": sum(
                    1
                    for d in boxes
                    if d.properties["classification"] == "CONSOLIDATION_BOX"
                ),
                "trend_count": sum(
                    1
                    for d in boxes
                    if d.properties["classification"] == "TREND_OR_EXPANSION"
                ),
            },
            params_used=params,
        )

    def required_upstream(self) -> list[str]:
        """No upstream dependencies (leaf detector)."""
        return []
