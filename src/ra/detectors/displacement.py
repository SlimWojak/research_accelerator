"""Displacement detector: single bar + cluster-2 + decisive override.

Implements:
- Single bar ATR: atr_ratio >= threshold AND body_ratio >= threshold AND close_gate
- Cluster-2: two consecutive bars with net_efficiency >= 0.65, overlap <= 0.35,
  progressive extremes, same-direction bodies
- Decisive override: body >= 0.75, close <= 0.10, pip floor per TF
- Quality grades: STRONG (>=2.0x), VALID (>=1.5x), WEAK (>=1.25x), null (<1.25x)
- Evaluation order: cluster_2 -> single_atr -> single_override

Pipeline emits ALL displacement candidates that pass the loosest OR gate
(atr >= 1.0 OR body >= 0.55) with full grade metadata. This module reproduces
that full candidate set.

Reference: pipeline/preprocess_data_v2.py detect_displacement() function.
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

# Pipeline sweep arrays for the qualifies grid
DISP_ATR_MULTS = [1.0, 1.25, 1.5, 2.0]
DISP_BODY_RATIOS = [0.55, 0.60, 0.65, 0.70]

# Keep local aliases for backward compatibility within this module
_TF_MINUTES = TF_MINUTES


_map_session = map_session
_bar_time_str = bar_time_str


def _close_location_pass(
    high: float, low: float, close: float, direction: str, threshold: float
) -> bool:
    """Close location gate: bar's close must be in the extreme % of its range.

    For bullish: (high - close) / range <= threshold
    For bearish: (close - low) / range <= threshold

    Args:
        high: Bar's high price.
        low: Bar's low price.
        close: Bar's close price.
        direction: "bullish" or "bearish".
        threshold: Maximum distance from extreme as fraction of range.

    Returns:
        True if close is within threshold of the directional extreme.
    """
    rng = high - low
    if rng == 0:
        return False
    if direction == "bullish":
        return (high - close) / rng <= threshold
    else:
        return (close - low) / rng <= threshold


def _quality_grade(atr_ratio: float) -> Optional[str]:
    """Assign quality grade based on ATR ratio.

    STRONG: >= 2.0x
    VALID:  >= 1.5x
    WEAK:   >= 1.25x
    None:   < 1.25x
    """
    if atr_ratio >= 2.0:
        return "STRONG"
    if atr_ratio >= 1.5:
        return "VALID"
    if atr_ratio >= 1.25:
        return "WEAK"
    return None



# _compute_atr extracted to ra.detectors._common.compute_atr


def _try_cluster2(
    highs, lows, opens, closes, i: int, atr: float,
    net_efficiency_min: float, overlap_max: float,
) -> Optional[dict]:
    """Check if bars[i:i+2] form a valid 2-bar impulse cluster.

    Four filters applied:
    1. Net efficiency >= net_efficiency_min (combined body / sum of individual ranges)
    2. Internal overlap <= overlap_max (overlap / smaller range)
    3. Progressive extremes (b1 extends beyond b0 in direction)
    4. Same-direction bodies (both bullish or both bearish)

    Args:
        highs, lows, opens, closes: NumPy arrays from the DataFrame.
        i: Index of first bar in potential cluster.
        atr: ATR value at bar i.
        net_efficiency_min: Minimum net efficiency threshold.
        overlap_max: Maximum overlap ratio threshold.

    Returns:
        Dict with cluster metrics if valid, None otherwise.
    """
    n = len(highs)
    if i + 2 > n:
        return None

    h0, l0, o0, c0 = highs[i], lows[i], opens[i], closes[i]
    h1, l1, o1, c1 = highs[i + 1], lows[i + 1], opens[i + 1], closes[i + 1]

    # Same direction check
    dir0 = "bullish" if c0 > o0 else "bearish"
    dir1 = "bullish" if c1 > o1 else "bearish"
    if dir0 != dir1:
        return None

    r0 = h0 - l0
    r1 = h1 - l1
    if r0 == 0 or r1 == 0:
        return None

    # Progressive extremes
    if dir0 == "bullish":
        if not (h1 > h0 and l1 >= l0):
            return None
    else:
        if not (l1 < l0 and h1 <= h0):
            return None

    combined_high = max(h0, h1)
    combined_low = min(l0, l1)
    combined_range = combined_high - combined_low
    if combined_range == 0:
        return None
    combined_body = abs(c1 - o0)
    body_ratio = combined_body / combined_range
    atr_multiple = combined_range / atr if atr > 0 else 0

    # Net efficiency: combined body / sum of individual ranges
    net_eff = abs(c1 - o0) / (r0 + r1) if (r0 + r1) > 0 else 0
    if net_eff < net_efficiency_min:
        return None

    # Overlap check
    overlap_top = min(h0, h1)
    overlap_bot = max(l0, l1)
    overlap = max(0, overlap_top - overlap_bot)
    smaller_range = min(r0, r1)
    overlap_ratio = overlap / smaller_range if smaller_range > 0 else 0
    if overlap_ratio > overlap_max:
        return None

    return {
        "direction": dir0,
        "combined_range": combined_range,
        "combined_body": combined_body,
        "body_ratio": body_ratio,
        "atr_multiple": atr_multiple,
        "high": combined_high,
        "low": combined_low,
        "net_efficiency": round(net_eff, 4),
        "overlap_ratio": round(overlap_ratio, 4),
    }


class DisplacementDetector(PrimitiveDetector):
    """Displacement detector: single bar + cluster-2 + decisive override.

    Leaf detector (no upstream dependencies).
    Evaluation order: cluster_2 -> single_atr -> single_override.
    """

    primitive_name = "displacement"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        """Displacement is a leaf node — no upstream dependencies."""
        return []

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Detect displacement events on the given bar DataFrame.

        Args:
            bars: DataFrame with bar contract columns (integer index).
            params: Displacement config params.
            upstream: Not used (leaf detector).
            context: Must contain 'timeframe' (str, e.g., '5m').

        Returns:
            DetectionResult with displacement detections.
        """
        context = context or {}
        tf = context.get("timeframe", "1m")
        tf_minutes = _TF_MINUTES.get(tf, 1)

        # Extract tier-specific params
        atr_period = params.get("atr_period", 14)
        cluster_params = params.get("cluster", {})
        cluster_2_enabled = cluster_params.get("cluster_2_enabled", True)
        net_efficiency_min = cluster_params.get("net_efficiency_min", 0.65)
        overlap_max = cluster_params.get("overlap_max", 0.35)
        override_params = params.get("decisive_override", {})
        override_enabled = override_params.get("enabled", True)

        # Get TF-tier defaults (pipeline uses same close_str for LTF/HTF)
        ltf_applies = params.get("ltf", {}).get("applies_to", ["1m", "5m", "15m"])
        htf_applies = params.get("htf", {}).get("applies_to", ["1H", "4H", "1D"])

        if tf in htf_applies:
            close_threshold = params.get("htf", {}).get("close_gate", 0.25)
        else:
            close_threshold = params.get("ltf", {}).get("close_gate", 0.25)

        # Compute ATR
        atrs = compute_atr(bars, period=atr_period)

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

        # NY window columns
        ny_window_col = bars["ny_window"].values if "ny_window" in bars.columns else None

        displacements = []
        used_in_cluster: set[int] = set()

        for i in range(1, n):
            if i in used_in_cluster:
                continue

            # Skip ghost bars
            if is_ghost is not None and is_ghost[i]:
                continue

            atr = atrs[i]
            if atr is None or atr == 0:
                continue

            bar_range = highs[i] - lows[i]
            if bar_range == 0:
                continue

            body = abs(closes[i] - opens[i])
            body_ratio = body / bar_range
            atr_multiple = bar_range / atr
            direction = "bullish" if closes[i] > opens[i] else "bearish"

            # ── Evaluation order: cluster_2 -> single_atr -> single_override ──

            is_cluster = False
            cluster2 = None

            # Step 1: Try cluster-2
            if cluster_2_enabled and i + 1 < n:
                # Check ghost for next bar too
                next_ghost = (
                    is_ghost is not None and is_ghost[i + 1]
                ) if i + 1 < n else True

                if not next_ghost:
                    cluster2 = _try_cluster2(
                        highs, lows, opens, closes, i, atr,
                        net_efficiency_min, overlap_max,
                    )

            if cluster2 is not None:
                # Close check on the final bar (bar i+1)
                c2_close = _close_location_pass(
                    highs[i + 1], lows[i + 1], closes[i + 1],
                    cluster2["direction"], close_threshold,
                )
                # Loose gate check: atr >= loosest OR body >= loosest
                c2_loose = (
                    cluster2["atr_multiple"] >= DISP_ATR_MULTS[0]
                    or cluster2["body_ratio"] >= DISP_BODY_RATIOS[0]
                )
                if c2_loose and c2_close:
                    is_cluster = True
                    used_atr = cluster2["atr_multiple"]
                    used_body = cluster2["body_ratio"]
                    used_dir = cluster2["direction"]
                    used_range = cluster2["combined_range"]
                    used_body_abs = cluster2["combined_body"]
                    close_loc = c2_close
                    disp_type = "CLUSTER_2"
                    used_in_cluster.add(i + 1)

            # Step 2: If not cluster, use single bar
            if not is_cluster:
                used_atr = atr_multiple
                used_body = body_ratio
                used_dir = direction
                used_range = bar_range
                used_body_abs = body
                close_loc = _close_location_pass(
                    highs[i], lows[i], closes[i], direction, close_threshold,
                )
                disp_type = "SINGLE"

            # Determine quality grade and qualification path
            grade = _quality_grade(used_atr)
            qual_path = "ATR_RELATIVE"

            # Step 3: Check decisive override (only for SINGLE bars with no grade)
            if disp_type == "SINGLE" and grade is None and override_enabled:
                ov_body_min = override_params.get("body_min", 0.75)
                ov_close_max = override_params.get("close_max", 0.10)
                ov_pip_floor = override_params.get("pip_floor", {})
                pip_floor = ov_pip_floor.get(
                    tf, ov_pip_floor.get("5m", 5.0)
                )
                range_pips = bar_range / PIP
                override_close = _close_location_pass(
                    highs[i], lows[i], closes[i], direction, ov_close_max,
                )
                if (
                    body_ratio >= ov_body_min
                    and override_close
                    and range_pips >= pip_floor
                ):
                    qual_path = "DECISIVE_OVERRIDE"
                    grade = "VALID"
                    close_loc = True

            # Compute extreme price: directional extreme of the displacement move
            # Bullish → highest high; Bearish → lowest low
            # Also identify the bar that produced the extreme for body/wick exposure
            if is_cluster and cluster2:
                extreme_price = cluster2["high"] if used_dir == "bullish" else cluster2["low"]
                # Find which bar of the cluster produced the extreme
                if used_dir == "bullish":
                    ext_idx = i if highs[i] >= highs[i + 1] else i + 1
                else:
                    ext_idx = i if lows[i] <= lows[i + 1] else i + 1
            else:
                extreme_price = float(highs[i] if used_dir == "bullish" else lows[i])
                ext_idx = i

            extreme_candle = {
                "body_high": float(max(opens[ext_idx], closes[ext_idx])),
                "body_low": float(min(opens[ext_idx], closes[ext_idx])),
                "wick_high": float(highs[ext_idx]),
                "wick_low": float(lows[ext_idx]),
            }

            # Build time strings
            bar_time = _bar_time_str(ts_ny_series.iloc[i], tf_minutes)
            if is_cluster:
                final_bar_time = _bar_time_str(ts_ny_series.iloc[i + 1], tf_minutes)
            else:
                final_bar_time = bar_time

            # Map session to pipeline-compatible label
            bar_session = _map_session(sessions[i])

            # NY window flags
            if ny_window_col is not None:
                ny_a_i = ny_window_col[i] == "a"
                ny_b_i = ny_window_col[i] == "b"
                if is_cluster and i + 1 < n:
                    ny_a_final = ny_window_col[i + 1] == "a"
                    ny_b_final = ny_window_col[i + 1] == "b"
                    ny_window_a = ny_a_i or ny_a_final
                    ny_window_b = ny_b_i or ny_b_final
                else:
                    ny_window_a = ny_a_i
                    ny_window_b = ny_b_i
            else:
                ny_window_a = False
                ny_window_b = False

            disp = {
                "bar_index": i,
                "bar_index_end": i + (1 if is_cluster else 0),
                "time": bar_time,
                "time_end": final_bar_time,
                "direction": used_dir,
                "body_pips": round(used_body_abs / PIP, 2),
                "range_pips": round(used_range / PIP, 2),
                "body_ratio": round(used_body, 4),
                "atr_multiple": round(used_atr, 4),
                "atr_value": round(atr / PIP, 2),
                "extreme_price": extreme_price,
                "extreme_candle": extreme_candle,
                "forex_day": forex_days[i],
                "session": bar_session,
                "ny_window_a": ny_window_a,
                "ny_window_b": ny_window_b,
                "tf": tf,
                "displacement_type": disp_type,
                "close_location_pass": close_loc,
                "quality_grade": grade,
                "qualification_path": qual_path,
            }

            # Cluster-specific fields
            if is_cluster and cluster2:
                disp["cluster_net_eff"] = cluster2["net_efficiency"]
                disp["cluster_overlap"] = cluster2["overlap_ratio"]

            # Build qualifies grid (same as pipeline)
            qualifies = {}
            is_override = qual_path == "DECISIVE_OVERRIDE"
            for atr_m in DISP_ATR_MULTS:
                for br in DISP_BODY_RATIOS:
                    meets_atr = used_atr >= atr_m
                    meets_body = used_body >= br
                    key = f"atr{atr_m}_br{br}"
                    qualifies[key] = {
                        "and": (meets_atr and meets_body) or is_override,
                        "or": meets_atr or meets_body or is_override,
                        "atr_only": meets_atr,
                        "body_only": meets_body,
                        "and_close": (
                            (meets_atr and meets_body) or is_override
                        ) and close_loc,
                        "override": is_override,
                    }
            disp["qualifies"] = qualifies

            # Emission gate: passes loosest OR gate
            loosest_key = f"atr{DISP_ATR_MULTS[0]}_br{DISP_BODY_RATIOS[0]}"
            if qualifies[loosest_key]["or"]:
                displacements.append(disp)

        # Cross-reference with FVG: mark which displacements created an FVG
        # FVG is detected at bar_index = candle C (i.e., gap between A and C).
        # The displacement that "created" the FVG is the bar that IS the middle
        # candle (B). FVG's bar_index is C = B+1, so B = fvg.bar_index - 1.
        # We need the FVG baseline data, but since this is a leaf detector,
        # we compute FVG indices inline by checking the 3-candle gap pattern.
        fvg_b_indices = self._compute_fvg_creating_indices(
            highs, lows, is_ghost, n, params.get("floor_threshold_pips", 0.5)
        )

        for disp in displacements:
            disp["created_fvg"] = disp["bar_index"] in fvg_b_indices

        # Build Detection objects
        detections = []
        for disp in displacements:
            det_time = pd.Timestamp(disp["time"])
            det_id = make_detection_id(
                primitive="displacement",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=disp["direction"],
            )

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=disp["direction"],
                type="displacement",
                price=disp["range_pips"] * PIP,  # range as primary price
                properties=disp,
                tags={
                    "session": disp["session"],
                    "forex_day": disp["forex_day"],
                },
            )
            detections.append(detection)

        # Build metadata
        type_counts = {}
        grade_counts = {}
        path_counts = {}
        for d in displacements:
            dt = d["displacement_type"]
            type_counts[dt] = type_counts.get(dt, 0) + 1
            g = d["quality_grade"]
            grade_counts[g] = grade_counts.get(g, 0) + 1
            qp = d["qualification_path"]
            path_counts[qp] = path_counts.get(qp, 0) + 1

        fvg_creating_count = sum(1 for d in displacements if d["created_fvg"])

        metadata = {
            "total_count": len(detections),
            "fvg_creating_count": fvg_creating_count,
            "type_counts": type_counts,
            "grade_counts": grade_counts,
            "path_counts": path_counts,
            "atr_multipliers": DISP_ATR_MULTS,
            "body_ratios": DISP_BODY_RATIOS,
        }

        return DetectionResult(
            primitive="displacement",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=dict(params),
        )

    @staticmethod
    def _compute_fvg_creating_indices(
        highs, lows, is_ghost, n: int, floor_pips: float = 0.5,
    ) -> set[int]:
        """Compute bar indices that created an FVG (are the 'B' candle).

        The pipeline marks displacement as 'created_fvg' when bar_index is
        in the FVG's B-candle set (fvg.bar_index - 1). The pipeline computes
        gap_pips with round(..., 2), then filters at >= 0.5. We replicate
        that rounding to match exactly.

        Args:
            highs, lows: Price arrays.
            is_ghost: Ghost bar flag array (or None).
            n: Number of bars.
            floor_pips: FVG floor threshold in pips.

        Returns:
            Set of bar indices that are B candles of FVGs with gap >= floor_pips.
        """
        fvg_b_indices: set[int] = set()

        for i in range(2, n):
            # Skip ghost bars
            if is_ghost is not None and (
                is_ghost[i] or is_ghost[i - 1] or is_ghost[i - 2]
            ):
                continue

            a_high = highs[i - 2]
            a_low = lows[i - 2]
            c_high = highs[i]
            c_low = lows[i]

            # Bullish FVG: C.low > A.high (gap > 0, then round and check floor)
            gap_bull = (c_low - a_high) / PIP
            if gap_bull > 0 and round(gap_bull, 2) >= floor_pips:
                fvg_b_indices.add(i - 1)

            # Bearish FVG: C.high < A.low (gap > 0, then round and check floor)
            gap_bear = (a_low - c_high) / PIP
            if gap_bear > 0 and round(gap_bear, 2) >= floor_pips:
                fvg_b_indices.add(i - 1)

        return fvg_b_indices
