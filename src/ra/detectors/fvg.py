"""FVG (Fair Value Gap) detector with IFVG state tracking and BPR overlap.

Implements:
- FVG detection: bullish when bars[i].low > bars[i-2].high,
  bearish when bars[i].high < bars[i-2].low
- IFVG state machine: ACTIVE -> CE_TOUCHED -> BOUNDARY_CLOSED -> IFVG
- BPR (Balanced Price Range): geometric overlap of bull + bear FVGs
- VI (Volume Imbalance) confluence tagging

Reference: pipeline/preprocess_data_v2.py detect_fvgs() function.
"""

import logging
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

# Look-ahead windows for state tracking, scaled by TF
_LOOKAHEAD = {
    "1m": 500,
    "5m": 200,
    "15m": 100,
}
_LOOKAHEAD_DEFAULT = 200

# Pipeline session mapping: the pipeline only uses asia/lokz/nyokz/other.
# The RA data layer adds pre_london and pre_ny, which the pipeline classifies
# as "other". Map back for baseline-compatible output.
_SESSION_MAP = {
    "asia": "asia",
    "lokz": "lokz",
    "nyokz": "nyokz",
    "pre_london": "other",
    "pre_ny": "other",
    "other": "other",
}


def _map_session(session: str) -> str:
    """Map RA session label to pipeline-compatible session label."""
    return _SESSION_MAP.get(session, session)


def _bar_time_str(ts_ny: pd.Timestamp, tf_minutes: int) -> str:
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


# Timeframe to minutes mapping
_TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1H": 60,
    "4H": 240,
    "1D": 1440,
}


class FVGDetector(PrimitiveDetector):
    """FVG detector: 3-candle gap detection + IFVG state + BPR overlap.

    Leaf detector (no upstream dependencies).
    """

    primitive_name = "fvg"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        """FVG is a leaf node — no upstream dependencies."""
        return []

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Detect FVGs on the given bar DataFrame.

        Args:
            bars: DataFrame with bar contract columns (integer index).
            params: Must contain 'floor_threshold_pips' (float).
            upstream: Not used (leaf detector).
            context: Must contain 'timeframe' (str, e.g., '5m').

        Returns:
            DetectionResult with FVG detections, BPR zones in metadata.
        """
        context = context or {}
        tf = context.get("timeframe", "1m")
        tf_minutes = _TF_MINUTES.get(tf, 1)
        floor_threshold = params.get("floor_threshold_pips", 0.5)
        look_ahead = _LOOKAHEAD.get(tf, _LOOKAHEAD_DEFAULT)

        # Extract arrays for fast access
        n = len(bars)
        highs = bars["high"].values
        lows = bars["low"].values
        opens = bars["open"].values
        closes = bars["close"].values
        ts_ny_series = bars["timestamp_ny"]
        sessions = bars["session"].values
        forex_days = bars["forex_day"].values
        is_ghost = bars["is_ghost"].values if "is_ghost" in bars.columns else None

        # Phase 1: Detect raw FVGs
        fvg_records = []
        vi_set: set[tuple[int, str]] = set()

        for i in range(2, n):
            # Skip if any of the three bars is a ghost
            if is_ghost is not None and (
                is_ghost[i] or is_ghost[i - 1] or is_ghost[i - 2]
            ):
                continue

            a_high = highs[i - 2]
            a_low = lows[i - 2]
            c_high = highs[i]
            c_low = lows[i]

            # Compute bar time strings using group-key alignment
            anchor_time = _bar_time_str(ts_ny_series.iloc[i - 2], tf_minutes)
            detect_time = _bar_time_str(ts_ny_series.iloc[i], tf_minutes)

            # Map session to pipeline-compatible label
            bar_session = _map_session(sessions[i])

            # Bullish FVG: C.low > A.high
            gap_bull = (c_low - a_high) / PIP
            if gap_bull > 0:
                fvg_records.append({
                    "type": "bullish",
                    "bar_index": i,
                    "anchor_time": anchor_time,
                    "detect_time": detect_time,
                    "top": c_low,
                    "bottom": a_high,
                    "gap_pips": round(gap_bull, 2),
                    "ce": (c_low + a_high) / 2,
                    "forex_day": forex_days[i],
                    "session": bar_session,
                    "tf": tf,
                })

            # Bearish FVG: C.high < A.low
            gap_bear = (a_low - c_high) / PIP
            if gap_bear > 0:
                fvg_records.append({
                    "type": "bearish",
                    "bar_index": i,
                    "anchor_time": anchor_time,
                    "detect_time": detect_time,
                    "top": a_low,
                    "bottom": c_high,
                    "gap_pips": round(gap_bear, 2),
                    "ce": (a_low + c_high) / 2,
                    "forex_day": forex_days[i],
                    "session": bar_session,
                    "tf": tf,
                })

            # VI (body-to-body) for confluence check
            a_body_top = max(opens[i - 2], closes[i - 2])
            a_body_bot = min(opens[i - 2], closes[i - 2])
            c_body_top = max(opens[i], closes[i])
            c_body_bot = min(opens[i], closes[i])

            vi_bull_gap = (c_body_bot - a_body_top) / PIP
            if vi_bull_gap > 0:
                vi_set.add((i, "bullish"))

            vi_bear_gap = (a_body_bot - c_body_top) / PIP
            if vi_bear_gap > 0:
                vi_set.add((i, "bearish"))

        # Phase 2: Mark VI confluence
        for fvg in fvg_records:
            fvg["vi_confluent"] = (fvg["bar_index"], fvg["type"]) in vi_set

        # Phase 3: Track IFVG state transitions (CE_TOUCHED, BOUNDARY_CLOSED)
        for fvg in fvg_records:
            fvg["ce_touched_bar"] = None
            fvg["boundary_closed_bar"] = None
            fvg["ce_touched_time"] = None
            fvg["boundary_closed_time"] = None

            start_idx = fvg["bar_index"] + 1
            end_idx = min(start_idx + look_ahead, n)

            for j in range(start_idx, end_idx):
                bar_time = _bar_time_str(ts_ny_series.iloc[j], tf_minutes)

                if fvg["type"] == "bullish":
                    # CE touched: bar low <= CE
                    if fvg["ce_touched_bar"] is None and lows[j] <= fvg["ce"]:
                        fvg["ce_touched_bar"] = j
                        fvg["ce_touched_time"] = bar_time

                    # Boundary closed: bar close < bottom
                    if fvg["boundary_closed_bar"] is None and closes[j] < fvg["bottom"]:
                        fvg["boundary_closed_bar"] = j
                        fvg["boundary_closed_time"] = bar_time
                else:
                    # Bearish: CE touched: bar high >= CE
                    if fvg["ce_touched_bar"] is None and highs[j] >= fvg["ce"]:
                        fvg["ce_touched_bar"] = j
                        fvg["ce_touched_time"] = bar_time

                    # Boundary closed: bar close > top
                    if fvg["boundary_closed_bar"] is None and closes[j] > fvg["top"]:
                        fvg["boundary_closed_bar"] = j
                        fvg["boundary_closed_time"] = bar_time

                # Both found — stop looking
                if (
                    fvg["ce_touched_bar"] is not None
                    and fvg["boundary_closed_bar"] is not None
                ):
                    break

        # Phase 4: Compute BPR (Balanced Price Range) zones
        bpr_zones = self._compute_bpr(fvg_records)

        # Phase 5: Build Detection objects
        detections = []
        for fvg in fvg_records:
            # Use anchor time for the detection timestamp (candle A)
            det_time = pd.Timestamp(fvg["anchor_time"])

            det_id = make_detection_id(
                primitive="fvg",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=fvg["type"],
            )

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=fvg["type"],
                type="fvg",
                price=fvg["ce"],
                properties={
                    "bar_index": fvg["bar_index"],
                    "anchor_time": fvg["anchor_time"],
                    "detect_time": fvg["detect_time"],
                    "top": fvg["top"],
                    "bottom": fvg["bottom"],
                    "gap_pips": fvg["gap_pips"],
                    "ce": fvg["ce"],
                    "tf": fvg["tf"],
                    "vi_confluent": fvg["vi_confluent"],
                    "ce_touched_bar": fvg["ce_touched_bar"],
                    "ce_touched_time": fvg["ce_touched_time"],
                    "boundary_closed_bar": fvg["boundary_closed_bar"],
                    "boundary_closed_time": fvg["boundary_closed_time"],
                },
                tags={
                    "session": fvg["session"],
                    "forex_day": fvg["forex_day"],
                },
            )
            detections.append(detection)

        # Build metadata
        bull_count = sum(1 for d in detections if d.direction == "bullish")
        bear_count = sum(1 for d in detections if d.direction == "bearish")
        above_floor = sum(
            1 for d in detections
            if d.properties["gap_pips"] >= floor_threshold
        )

        metadata = {
            "total_count": len(detections),
            "bullish_count": bull_count,
            "bearish_count": bear_count,
            "above_floor_count": above_floor,
            "below_floor_count": len(detections) - above_floor,
            "floor_threshold_pips": floor_threshold,
            "bpr_zones": bpr_zones,
        }

        return DetectionResult(
            primitive="fvg",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )

    @staticmethod
    def _compute_bpr(fvg_records: list[dict]) -> list[dict]:
        """Compute Balanced Price Range zones from overlapping bull+bear FVGs.

        BPR = geometric overlap of a bullish FVG zone with a bearish FVG zone
        on the same timeframe. Both source FVGs must exist for the overlap.

        Returns:
            List of BPR zone dicts with overlap_top, overlap_bottom,
            bull_source_idx, bear_source_idx.
        """
        bulls = [
            (i, f) for i, f in enumerate(fvg_records) if f["type"] == "bullish"
        ]
        bears = [
            (i, f) for i, f in enumerate(fvg_records) if f["type"] == "bearish"
        ]

        bpr_zones = []
        for bi, bull in bulls:
            for bei, bear in bears:
                overlap_top = min(bull["top"], bear["top"])
                overlap_bot = max(bull["bottom"], bear["bottom"])
                if overlap_top > overlap_bot:
                    bpr_zones.append({
                        "overlap_top": overlap_top,
                        "overlap_bottom": overlap_bot,
                        "overlap_pips": round(
                            (overlap_top - overlap_bot) / PIP, 2
                        ),
                        "bull_source_idx": bi,
                        "bear_source_idx": bei,
                        "bull_bar_index": bull["bar_index"],
                        "bear_bar_index": bear["bar_index"],
                    })

        return bpr_zones
