"""HTF Liquidity detector — structural EQH/EQL pools from fractal swing points.

Implements:
- Fractal swing detection (left=2, right=2) per HTF timeframe
- Pool clustering with price tolerance per TF
- Min bars between touches gate
- Rotation (pullback) gate
- Asia intra-box filter (same session, same day = skip)
- Invalidation during formation (price traded through level)
- Merge overlapping pools within 1.5x tolerance
- Status lifecycle: UNTOUCHED -> TAKEN (price broke through)

Operates on 1m bars internally — aggregates to H1/H4/D1/W1/MN and runs
fractal detection on each HTF. Does NOT use the upstream swing_points
detector (which uses N-bar pivots with different N values). Instead,
uses a fixed fractal left=2, right=2 on HTF bars.

Reference: pipeline/preprocess_data_v2.py compute_htf_liquidity(),
           _detect_htf_swings(), _build_htf_pools().
"""

import logging
from collections import defaultdict
from typing import Optional

import pandas as pd

from ra.detectors._common import PIP, bar_time_str
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

# Fixed fractal parameters for HTF swing detection
HTF_PIVOT_LEFT = 2
HTF_PIVOT_RIGHT = 2

# HTF timeframes to process and their aggregation minutes
_HTF_TF_CONFIG = {
    "H1": {"minutes": 60},
    "H4": {"minutes": 240},
    "D1": {"minutes": 1440},
    "W1": {"minutes": 10080},
    "MN": {"minutes": 43200},
}


def _compute_atr(bars: list[dict], period: int = 14) -> list[Optional[float]]:
    """Compute ATR(period) for a list of bar dicts. Matches pipeline compute_atr()."""
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


def _aggregate_htf_from_df(bars_1m: pd.DataFrame, tf_label: str) -> list[dict]:
    """Aggregate 1m DataFrame bars to HTF bar dicts.

    Matches pipeline's _aggregate_htf() logic:
    - H1/H4: minute-floor grouping in NY time
    - D1: forex_day grouping
    - W1: ISO week grouping
    - MN: month grouping
    """
    if tf_label in ("H1", "H4"):
        period = _HTF_TF_CONFIG[tf_label]["minutes"]
        return _aggregate_intraday_to_dicts(bars_1m, period)

    if tf_label == "D1":
        return _aggregate_by_column(bars_1m, "forex_day")

    if tf_label == "W1":
        return _aggregate_weekly(bars_1m)

    if tf_label == "MN":
        return _aggregate_monthly(bars_1m)

    return []


def _aggregate_intraday_to_dicts(bars_1m: pd.DataFrame, period: int) -> list[dict]:
    """Aggregate 1m bars to intraday HTF using NY time flooring."""
    groups: dict[str, list] = defaultdict(list)

    ny_ts = bars_1m["timestamp_ny"]
    opens = bars_1m["open"].values
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values
    forex_days = bars_1m["forex_day"].values
    sessions = bars_1m["session"].values

    for idx in range(len(bars_1m)):
        ts_ny = ny_ts.iloc[idx]
        total_min = ts_ny.hour * 60 + ts_ny.minute
        group_min = (total_min // period) * period
        gh = group_min // 60
        gm = group_min % 60
        key = ts_ny.strftime("%Y-%m-%d") + f"T{gh:02d}:{gm:02d}:00"
        groups[key].append(idx)

    result = []
    for key in sorted(groups.keys()):
        indices = groups[key]
        first = indices[0]
        last = indices[-1]
        result.append({
            "time": key,
            "open": opens[first],
            "high": float(highs[indices].max()) if hasattr(highs[indices], "max") else max(highs[i] for i in indices),
            "low": float(lows[indices].min()) if hasattr(lows[indices], "min") else min(lows[i] for i in indices),
            "close": closes[last],
            "forex_day": forex_days[first],
            "session": sessions[first],
        })
    return result


def _aggregate_by_column(bars_1m: pd.DataFrame, col: str) -> list[dict]:
    """Aggregate 1m bars by a grouping column (e.g., forex_day)."""
    groups: dict[str, list[int]] = defaultdict(list)
    col_vals = bars_1m[col].values

    for idx in range(len(bars_1m)):
        groups[str(col_vals[idx])].append(idx)

    opens = bars_1m["open"].values
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values
    ny_ts = bars_1m["timestamp_ny"]

    result = []
    for key in sorted(groups.keys()):
        indices = groups[key]
        first = indices[0]
        last = indices[-1]
        result.append({
            "time": ny_ts.iloc[first].strftime("%Y-%m-%dT%H:%M:%S"),
            "open": opens[first],
            "high": max(highs[i] for i in indices),
            "low": min(lows[i] for i in indices),
            "close": closes[last],
            "forex_day": key,
            "session": "d1",
        })
    return result


def _aggregate_weekly(bars_1m: pd.DataFrame) -> list[dict]:
    """Aggregate 1m bars to weekly (ISO week) bars."""
    groups: dict[str, list[int]] = defaultdict(list)
    ny_ts = bars_1m["timestamp_ny"]

    for idx in range(len(bars_1m)):
        ts = ny_ts.iloc[idx]
        iso = ts.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        groups[key].append(idx)

    opens = bars_1m["open"].values
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values

    result = []
    for key in sorted(groups.keys()):
        indices = groups[key]
        first = indices[0]
        last = indices[-1]
        result.append({
            "time": ny_ts.iloc[first].strftime("%Y-%m-%dT%H:%M:%S"),
            "open": opens[first],
            "high": max(highs[i] for i in indices),
            "low": min(lows[i] for i in indices),
            "close": closes[last],
            "forex_day": "",
            "session": "w1",
        })
    return result


def _aggregate_monthly(bars_1m: pd.DataFrame) -> list[dict]:
    """Aggregate 1m bars to monthly bars."""
    groups: dict[str, list[int]] = defaultdict(list)
    ny_ts = bars_1m["timestamp_ny"]

    for idx in range(len(bars_1m)):
        ts = ny_ts.iloc[idx]
        key = ts.strftime("%Y-%m")
        groups[key].append(idx)

    opens = bars_1m["open"].values
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values

    result = []
    for key in sorted(groups.keys()):
        indices = groups[key]
        first = indices[0]
        last = indices[-1]
        result.append({
            "time": ny_ts.iloc[first].strftime("%Y-%m-%dT%H:%M:%S"),
            "open": opens[first],
            "high": max(highs[i] for i in indices),
            "low": min(lows[i] for i in indices),
            "close": closes[last],
            "forex_day": "",
            "session": "mn",
        })
    return result


def _detect_htf_swings(bars: list[dict]) -> list[dict]:
    """Fractal SwingPoint detection for HTF bars (left=2, right=2).

    Matches pipeline's _detect_htf_swings() exactly.
    """
    swings = []
    left, right = HTF_PIVOT_LEFT, HTF_PIVOT_RIGHT

    for i in range(left, len(bars) - right):
        is_high = (
            all(bars[i]["high"] >= bars[i - k]["high"] for k in range(1, left + 1))
            and all(bars[i]["high"] > bars[i + k]["high"] for k in range(1, right + 1))
        )
        if is_high:
            swings.append({
                "type": "high",
                "bar_index": i,
                "time": bars[i]["time"],
                "price": bars[i]["high"],
                "session": bars[i].get("session", ""),
                "forex_day": bars[i].get("forex_day", ""),
            })

        is_low = (
            all(bars[i]["low"] <= bars[i - k]["low"] for k in range(1, left + 1))
            and all(bars[i]["low"] < bars[i + k]["low"] for k in range(1, right + 1))
        )
        if is_low:
            swings.append({
                "type": "low",
                "bar_index": i,
                "time": bars[i]["time"],
                "price": bars[i]["low"],
                "session": bars[i].get("session", ""),
                "forex_day": bars[i].get("forex_day", ""),
            })

    return swings


def _check_invalidation(
    bars: list[dict],
    a_idx: int,
    b_idx: int,
    level: float,
    pool_type: str,
    tol_buffer: float = 0,
) -> bool:
    """Check if price traded THROUGH the level between two touch bars.

    Matches pipeline's _check_invalidation() exactly.
    """
    for k in range(a_idx + 1, b_idx):
        if pool_type == "high" and bars[k]["high"] > level + tol_buffer:
            return True
        if pool_type == "low" and bars[k]["low"] < level - tol_buffer:
            return True
    return False


def _build_htf_pools(
    typed_swings: list[dict],
    bars: list[dict],
    atrs: list[Optional[float]],
    cfg: dict,
    swing_type: str,
    min_touches: int = 2,
    merge_factor: float = 1.5,
) -> list[dict]:
    """Cluster confirmed SwingPoints into EqualPools with invalidation gates.

    Matches pipeline's _build_htf_pools() exactly:
    1. Find candidate pools within lookback + tolerance
    2. Check min_bars_between gate
    3. Check rotation (pullback) gate
    4. Check invalidation: price traded through between touches?
    5. All gates pass + not invalidated → add touch, update median
    6. No match → start new pool
    After: merge overlapping pools within merge_factor * tolerance.
    """
    typed_swings = sorted(typed_swings, key=lambda p: p["bar_index"])
    if not typed_swings:
        return []

    tol_pip = cfg["tol_pip"]
    max_lookback = cfg["max_lookback"]
    min_between = cfg["min_between"]
    pb_pip = cfg["pb_pip"]
    pb_atr = cfg["pb_atr"]

    max_idx = len(bars) - 1
    min_idx = max(0, max_idx - max_lookback)
    filtered = [p for p in typed_swings if p["bar_index"] >= min_idx]
    if not filtered:
        return []

    pools: list[dict] = []

    for swing in filtered:
        atr_at = (
            atrs[swing["bar_index"]]
            if swing["bar_index"] < len(atrs) and atrs[swing["bar_index"]] is not None
            else 0
        )
        tol = tol_pip * PIP
        min_pb = max(pb_pip * PIP, pb_atr * atr_at)

        candidates = []
        for pool in pools:
            if pool.get("_invalidated"):
                continue
            dist = abs(swing["price"] - pool["price"])
            if dist <= tol:
                candidates.append((dist, pool))
        candidates.sort(key=lambda x: x[0])

        matched = False
        for _, cand_pool in candidates:
            last_touch = cand_pool["_touches"][-1]
            a_idx = last_touch["bar_index"]
            b_idx = swing["bar_index"]

            # Asia intra-box filter: skip if both in same asia session + same day
            if (
                last_touch.get("session") == "asia"
                and swing.get("session") == "asia"
                and last_touch.get("forex_day") == swing.get("forex_day")
            ):
                continue

            # Min bars between touches gate
            if b_idx - a_idx < min_between:
                continue

            # Rotation (pullback) gate
            if b_idx > a_idx + 1:
                level = cand_pool["price"]
                if swing_type == "high":
                    retrace = max(
                        (level - bars[k]["low"]) for k in range(a_idx + 1, b_idx)
                    )
                else:
                    retrace = max(
                        (bars[k]["high"] - level) for k in range(a_idx + 1, b_idx)
                    )
                if retrace < min_pb:
                    continue

            # Invalidation check
            if _check_invalidation(
                bars, a_idx, b_idx, cand_pool["price"], swing_type, tol
            ):
                cand_pool["_invalidated"] = True
                continue

            # All gates passed — add touch
            cand_pool["_touches"].append(swing)
            prices = sorted(t["price"] for t in cand_pool["_touches"])
            cand_pool["price"] = prices[len(prices) // 2]
            matched = True
            break

        if not matched:
            pools.append({
                "price": swing["price"],
                "_touches": [swing],
                "_invalidated": False,
            })

    # Filter: min touches and not invalidated
    valid = [
        p for p in pools
        if not p.get("_invalidated") and len(p["_touches"]) >= min_touches
    ]

    # Merge overlapping pools within merge_factor * tolerance
    if len(valid) > 1:
        valid.sort(key=lambda p: p["price"])
        merged = [valid[0]]
        for p in valid[1:]:
            prev = merged[-1]
            merge_tol = merge_factor * tol_pip * PIP
            if abs(p["price"] - prev["price"]) <= merge_tol:
                all_touches = prev["_touches"] + p["_touches"]
                all_touches.sort(key=lambda t: t["bar_index"])
                prices = sorted(t["price"] for t in all_touches)
                prev["_touches"] = all_touches
                prev["price"] = prices[len(prices) // 2]
            else:
                merged.append(p)
        valid = merged

    return valid


class HTFLiquidityDetector(PrimitiveDetector):
    """HTF Liquidity detector — structural EQH/EQL pools.

    Detects equal highs/lows across HTF timeframes (H1, H4, D1, W1, MN)
    using fractal swing detection (left=2, right=2) followed by pool
    clustering with invalidation gates.

    Accepts 1m bars and internally aggregates to each HTF.
    """

    primitive_name = "htf_liquidity"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run HTF liquidity detection across all configured TFs.

        Args:
            bars: 1m bar DataFrame.
            params: HTF liquidity params from config.
            upstream: Not used (detects fractal swings internally).
            context: Optional context.

        Returns:
            DetectionResult with one Detection per pool found.
        """
        all_detections = []
        summary: dict[str, dict] = {}

        tol_pips_per_tf = params.get("price_tolerance_pips", {}).get("per_tf", {})
        min_between_per_tf = params.get("min_bars_between_touches", {}).get("per_tf", {})
        rotation_per_tf = params.get("rotation_required", {}).get("per_tf", {})
        max_lookback_per_tf = params.get("max_lookback", {}).get("per_tf", {})
        min_touches = params.get("min_touches", 2)
        merge_factor = params.get("merge_tolerance_factor", 1.5)

        for tf_label in _HTF_TF_CONFIG:
            tol_pip = tol_pips_per_tf.get(tf_label, 2)
            min_between = min_between_per_tf.get(tf_label, 2)
            rotation = rotation_per_tf.get(tf_label, {"pip_floor": 5, "atr_factor": 0.25})
            max_lb = max_lookback_per_tf.get(tf_label, 500)

            cfg = {
                "tol_pip": tol_pip,
                "min_between": min_between,
                "pb_pip": rotation.get("pip_floor", 5),
                "pb_atr": rotation.get("atr_factor", 0.25),
                "max_lookback": max_lb,
            }

            # Aggregate 1m bars to HTF
            htf_bars = _aggregate_htf_from_df(bars, tf_label)

            if len(htf_bars) < HTF_PIVOT_LEFT + HTF_PIVOT_RIGHT + 1:
                summary[tf_label] = {
                    "bars": len(htf_bars),
                    "swings": 0,
                    "pools": 0,
                    "untouched": 0,
                    "taken": 0,
                }
                continue

            # Compute ATR on HTF bars
            atrs = _compute_atr(htf_bars, period=min(14, len(htf_bars)))

            # Detect fractal swings
            swings = _detect_htf_swings(htf_bars)

            highs = [s for s in swings if s["type"] == "high"]
            lows = [s for s in swings if s["type"] == "low"]

            # Build pools
            high_pools = _build_htf_pools(
                highs, htf_bars, atrs, cfg, "high", min_touches, merge_factor
            )
            low_pools = _build_htf_pools(
                lows, htf_bars, atrs, cfg, "low", min_touches, merge_factor
            )

            # Process pools into detections
            tf_pools = []
            for pool_data in high_pools + low_pools:
                pool_type = "EQH" if pool_data["_touches"][0]["type"] == "high" else "EQL"
                touches = pool_data["_touches"]
                last_idx = touches[-1]["bar_index"]

                # Determine status: UNTOUCHED or TAKEN
                status = "UNTOUCHED"
                taken_time = None
                for k in range(last_idx + 1, len(htf_bars)):
                    b = htf_bars[k]
                    if pool_type == "EQH" and b["high"] > pool_data["price"]:
                        status = "TAKEN"
                        taken_time = b["time"]
                        break
                    if pool_type == "EQL" and b["low"] < pool_data["price"]:
                        status = "TAKEN"
                        taken_time = b["time"]
                        break

                pool_info = {
                    "type": pool_type,
                    "timeframe": tf_label,
                    "price": pool_data["price"],
                    "touches": len(touches),
                    "first_touch_time": touches[0]["time"],
                    "last_touch_time": touches[-1]["time"],
                    "status": status,
                    "taken_time": taken_time,
                    "touch_prices": [t["price"] for t in touches],
                    "tags": ["HTF_STRUCTURAL"],
                }
                tf_pools.append(pool_info)

            # Create Detection objects
            for pool_info in tf_pools:
                det_time = pd.Timestamp(pool_info["first_touch_time"])
                direction = "high" if pool_info["type"] == "EQH" else "low"
                det_id = make_detection_id(
                    primitive="htf_liquidity",
                    timeframe=tf_label,
                    timestamp_ny=det_time,
                    direction=direction,
                )

                detection = Detection(
                    id=det_id,
                    time=det_time,
                    direction=direction,
                    type="htf_pool",
                    price=pool_info["price"],
                    properties=pool_info,
                    tags={"timeframe": tf_label},
                )
                all_detections.append(detection)

            summary[tf_label] = {
                "bars": len(htf_bars),
                "swings": len(swings),
                "pools": len(tf_pools),
                "untouched": sum(1 for p in tf_pools if p["status"] == "UNTOUCHED"),
                "taken": sum(1 for p in tf_pools if p["status"] == "TAKEN"),
            }

        return DetectionResult(
            primitive="htf_liquidity",
            variant="a8ra_v1",
            timeframe="multi",
            detections=all_detections,
            metadata=summary,
            params_used=params,
        )

    def required_upstream(self) -> list[str]:
        """HTF Liquidity uses swing_points conceptually but detects internally."""
        return ["swing_points"]
