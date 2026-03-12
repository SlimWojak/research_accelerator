"""Liquidity Sweep detector — multi-source curated level pool with temporal gating.

Implements:
- Curated level pool assembly from:
  - session_liquidity (box H/L for Asia, Pre-London, Pre-NY)
  - reference_levels (PDH/PDL, PWH/PWL)
  - htf_liquidity (EQH/EQL pools, untouched only)
  - swing_points (promoted swings: strength>=10, height>=10pip, current forex day)
- Temporal gating per source (canonical rules from advisory synthesis)
- Level merge within 1.0 pip tolerance
- Detection: breach + close back within per-TF return window + rejection wick >= 40%
  Return windows: M1=2, M5=3, M15=4
  Reclaim checked BEFORE ATR cap — a large breach that rejects is a sweep, not breakout
- Continuation: breach > 1.5x ATR AND no reclaim within window (true breakout)
- Qualified sweep: displacement tag (before 10 bars / after 5 bars), NOT a gate

Reference: pipeline/preprocess_data_v2.py detect_liquidity_sweeps(),
           qualify_sweeps()
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from ra.detectors._common import PIP, bar_time_str, compute_atr, map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

# Session sources that contribute Asia/London levels
_SWEEP_SESSION_SOURCES = {"asia", "prev_asia", "lokz", "prev_lokz"}

# Source priority for merge: lower number = higher priority
_SRC_PRIORITY = {
    "PROMOTED_SWING": 0, "PDH_PDL": 1, "PWH": 2, "PWL": 3,
    "HTF_EQH": 4, "HTF_EQL": 5, "LONDON_H_L": 6, "ASIA_H_L": 7, "LTF_BOX": 8,
    "SWEEP_EVENT": 9,
}

# Forex session boundaries (NY hours) for max_age_sessions calculation
_SESSION_BOUNDARIES_NY = [0, 5, 8, 17]  # Asia open, London open, NY open, NY close

# TF rank for HTF pools
_TF_RANK = {"MN": 5, "W1": 4, "D1": 3, "H4": 2, "H1": 1}



# _compute_atr extracted to ra.detectors._common.compute_atr


def _session_close_time(forex_day_str: str, session_type: str) -> str:
    """Compute valid_from time for session-based levels."""
    day = datetime.strptime(forex_day_str, "%Y-%m-%d")
    if session_type in ("asia", "prev_asia"):
        return day.replace(hour=0, minute=0).strftime("%Y-%m-%dT%H:%M:%S")
    elif session_type in ("lokz", "prev_lokz"):
        return day.replace(hour=5, minute=0).strftime("%Y-%m-%dT%H:%M:%S")
    return forex_day_str + "T00:00:00"


def _deduplicate_levels(levels: list, pip_tolerance: float = 0.1) -> list:
    """Deduplicate levels by (source, side, price) within pip tolerance.

    Prefers current session over prev_*, higher TF over lower TF.
    """
    seen = {}
    for lv in levels:
        key = (lv["source"], lv["side"], round(lv["price"] / (pip_tolerance * PIP)))
        if key not in seen:
            seen[key] = lv
        else:
            existing = seen[key]
            is_prev = "prev_" in lv.get("id", "")
            existing_is_prev = "prev_" in existing.get("id", "")
            if existing_is_prev and not is_prev:
                seen[key] = lv
    return list(seen.values())


def _merge_levels(levels: list, merge_tol: float) -> list:
    """Merge nearby levels into pools (by side and forex_day) within merge_tol.

    Levels from different forex days are never merged, because they represent
    distinct session events with different valid_from times. HTF/PWH/PWL levels
    with empty forex_day merge only with other empty-day levels.
    """
    if not levels:
        return []
    # Partition by (side, forex_day) before merging
    from collections import defaultdict
    partitions = defaultdict(list)
    for lv in levels:
        key = (lv["side"], lv.get("forex_day", ""))
        partitions[key].append(lv)
    merged = []
    for (side, _day), group in partitions.items():
        group.sort(key=lambda x: x["price"])
        pools = []
        for lv in group:
            if pools and abs(lv["price"] - pools[-1]["price"]) <= merge_tol:
                pools[-1]["_sources"].append(lv)
            else:
                pools.append({**lv, "_sources": [lv]})
        for p in pools:
            srcs = p["_sources"]
            srcs.sort(key=lambda x: _SRC_PRIORITY.get(x["source"], 99))
            best = srcs[0]
            merged.append({
                "price": best["price"],
                "side": best["side"],
                "source": best["source"],
                "tf_class": best.get("tf_class", "LTF"),
                "id": best["id"],
                "bar_index": best.get("bar_index", 0),
                "forex_day": best.get("forex_day", ""),
                "valid_from": best.get("valid_from", ""),
                "sources_merged": [s["source"] for s in srcs],
                "touch_count": len(srcs),
            })
    return merged


def _compute_session_levels(bars_1m: pd.DataFrame) -> list:
    """Compute session H/L for all windows per forex day.

    This mirrors the pipeline's compute_session_liquidity() function which
    computes high/low across all bars tagged with each session type.
    These are DIFFERENT from session box H/L.

    Returns list of dicts with type, price, forex_day fields.
    """
    levels = []
    forex_days = bars_1m["forex_day"].unique().tolist()

    for day in forex_days:
        day_bars = bars_1m[bars_1m["forex_day"] == day]
        if day_bars.empty:
            continue

        for sess_name in ["asia", "lokz", "nyokz"]:
            sess_bars = day_bars[day_bars["session"] == sess_name]
            if sess_bars.empty:
                continue
            h = sess_bars["high"].max()
            l = sess_bars["low"].min()
            levels.append({"type": f"{sess_name}_H", "price": h, "forex_day": day})
            levels.append({"type": f"{sess_name}_L", "price": l, "forex_day": day})

        # Pre-london: 00:00-02:00 NY
        pre_london = day_bars[
            (day_bars["timestamp_ny"].dt.hour >= 0) & (day_bars["timestamp_ny"].dt.hour < 2)
        ]
        if not pre_london.empty:
            levels.append({"type": "pre_london_H", "price": pre_london["high"].max(), "forex_day": day})
            levels.append({"type": "pre_london_L", "price": pre_london["low"].min(), "forex_day": day})

        # Pre-NY: 05:00-07:00 NY
        pre_ny = day_bars[
            (day_bars["timestamp_ny"].dt.hour >= 5) & (day_bars["timestamp_ny"].dt.hour < 7)
        ]
        if not pre_ny.empty:
            levels.append({"type": "pre_ny_H", "price": pre_ny["high"].max(), "forex_day": day})
            levels.append({"type": "pre_ny_L", "price": pre_ny["low"].min(), "forex_day": day})

    # Previous session levels (carry forward Asia/LOKZ from previous day)
    prev_levels = []
    for i, day in enumerate(forex_days):
        if i == 0:
            continue
        prev_day = forex_days[i - 1]
        for lv in levels:
            if lv["forex_day"] == prev_day and lv["type"].startswith(("asia_", "lokz_")):
                prev_levels.append({**lv, "type": "prev_" + lv["type"], "forex_day": day})

    return levels + prev_levels


def _extract_session_boxes(sess_result: DetectionResult) -> list:
    """Extract all session box objects from SessionLiquidity output for LTF_BOX levels."""
    boxes = []
    for det in sess_result.detections:
        box_type = det.properties.get("type", "")
        if box_type not in ("ASIA_BOX", "PRE_LONDON_BOX", "PRE_NY_BOX"):
            continue
        boxes.append({
            "type": box_type,
            "high": det.properties.get("high"),
            "low": det.properties.get("low"),
            "forex_day": det.properties.get("forex_day", ""),
            "end_time": det.properties.get("end_time", ""),
        })
    return boxes


def _extract_pdh_pdl(ref_result: DetectionResult) -> dict:
    """Extract PDH/PDL dict from ReferenceLevelDetector output.

    The ReferenceLevelDetector outputs one Detection per forex day with
    properties containing pdh, pdl, day_high, day_low, etc.
    """
    pdh_pdl = {}
    for det in ref_result.detections:
        forex_day = det.tags.get("forex_day", "")
        if not forex_day:
            continue
        pdh = det.properties.get("pdh")
        pdl = det.properties.get("pdl")
        if pdh is not None or pdl is not None:
            pdh_pdl[forex_day] = {}
            if pdh is not None:
                pdh_pdl[forex_day]["pdh"] = pdh
            if pdl is not None:
                pdh_pdl[forex_day]["pdl"] = pdl
    return pdh_pdl


def _extract_pwh_pwl(ref_result: DetectionResult) -> dict:
    """Extract PWH/PWL from ReferenceLevelDetector output.

    PWH = max of all day_high values, PWL = min of all day_low values
    across the dataset. The ReferenceLevelDetector stores these per-day.
    """
    all_highs = []
    all_lows = []
    for det in ref_result.detections:
        dh = det.properties.get("day_high")
        dl = det.properties.get("day_low")
        if dh is not None:
            all_highs.append(dh)
        if dl is not None:
            all_lows.append(dl)
    pwh_pwl = {}
    if all_highs:
        pwh_pwl["pwh"] = max(all_highs)
    if all_lows:
        pwh_pwl["pwl"] = min(all_lows)
    return pwh_pwl


def _extract_htf_pools(htf_result: DetectionResult) -> list:
    """Extract HTF liquidity pools from HTFLiquidityDetector output."""
    pools = []
    for det in htf_result.detections:
        pool_type = det.properties.get("type", "")
        if pool_type not in ("EQH", "EQL"):
            continue
        pools.append({
            "type": pool_type,
            "price": det.price,
            "timeframe": det.properties.get("timeframe", ""),
            "status": det.properties.get("status", "UNTOUCHED"),
            "last_touch_time": det.properties.get("last_touch_time", ""),
            "first_touch_time": det.properties.get("first_touch_time", ""),
        })
    return pools


def _extract_swings(swing_result: DetectionResult) -> list:
    """Extract swing data from SwingPointDetector output for promoted swing filtering."""
    swings = []
    for det in swing_result.detections:
        swings.append({
            "type": det.direction,  # "high" or "low"
            "price": det.price,
            "bar_index": det.properties.get("bar_index", 0),
            "time": det.properties.get("time", ""),
            "strength": det.properties.get("strength", 0),
            "height_pips": det.properties.get("height_pips", 0.0),
            "forex_day": det.tags.get("forex_day", ""),
        })
    return swings


def _extract_displacements(disp_result: DetectionResult) -> list:
    """Extract displacement data for sweep qualification.

    The DisplacementDetector stores a full `qualifies` dict in properties
    with per-threshold gates (and, and_close, override, etc.). We pass
    this through directly for the sweep qualifier to check.
    """
    disps = []
    for det in disp_result.detections:
        disps.append({
            "bar_index": det.properties.get("bar_index", 0),
            "direction": det.direction,
            "qualifies": det.properties.get("qualifies", {}),
        })
    return disps


def _build_level_pool(
    session_levels: list,
    session_boxes: list,
    pdh_pdl: dict,
    htf_pools: list,
    pwh_pwl: dict,
    swings: list,
    params: dict,
) -> tuple:
    """Build the curated level pool from all upstream sources.

    Returns:
        (promoted_swings, merged_non_swing, all_levels, raw_levels_for_pool_info)
    """
    ps_cfg = params.get("level_sources", {}).get("promoted_swing", {})
    ps_min_strength = ps_cfg.get("strength_min", 10)
    ps_min_height = ps_cfg.get("height_pips_min", 10.0)
    merge_tol = params.get("level_merge_tolerance_pips", 1.0) * PIP

    raw_levels = []

    # Promoted swings — filtered from swing output
    promoted_swings = []
    for s in swings:
        if s.get("strength", 0) < ps_min_strength:
            continue
        if s.get("height_pips", 0) < ps_min_height:
            continue
        side = "high" if s["type"] == "high" else "low"
        promoted_swings.append({
            "price": s["price"],
            "side": side,
            "source": "PROMOTED_SWING",
            "tf_class": "LTF",
            "id": f"PS_{s['bar_index']}_{s['type']}",
            "bar_index": s["bar_index"],
            "forex_day": s.get("forex_day", ""),
            "valid_from": s.get("time", ""),
            "_strength": s.get("strength", 0),
            "_height": s.get("height_pips", 0),
        })

    # Session levels (Asia + London only)
    for lv in session_levels:
        sess_root = lv["type"].rsplit("_", 1)[0]
        if sess_root not in _SWEEP_SESSION_SOURCES:
            continue
        side = "high" if "_H" in lv["type"] else "low"
        src = "ASIA_H_L" if "asia" in lv["type"] else "LONDON_H_L"
        valid_from = _session_close_time(lv["forex_day"], sess_root)
        raw_levels.append({
            "price": lv["price"],
            "side": side,
            "source": src,
            "tf_class": "LTF",
            "id": f"{lv['type']}_{lv['forex_day']}",
            "bar_index": 0,
            "forex_day": lv["forex_day"],
            "valid_from": valid_from,
        })

    # PDH/PDL — valid from 17:00 NY previous day
    for day, vals in pdh_pdl.items():
        d = datetime.strptime(day, "%Y-%m-%d")
        prev = d - timedelta(days=1)
        valid_from = prev.replace(hour=17, minute=0).strftime("%Y-%m-%dT%H:%M:%S")
        if "pdh" in vals:
            raw_levels.append({
                "price": vals["pdh"],
                "side": "high",
                "source": "PDH_PDL",
                "tf_class": "LTF",
                "id": f"PDH_{day}",
                "bar_index": 0,
                "forex_day": day,
                "valid_from": valid_from,
            })
        if "pdl" in vals:
            raw_levels.append({
                "price": vals["pdl"],
                "side": "low",
                "source": "PDH_PDL",
                "tf_class": "LTF",
                "id": f"PDL_{day}",
                "bar_index": 0,
                "forex_day": day,
                "valid_from": valid_from,
            })

    # LTF Box H/L — valid from box.end_time
    for box in session_boxes:
        box_id = f"{box.get('type', 'BOX')}_{box.get('forex_day', '')}"
        valid_from = box.get("end_time", "")
        raw_levels.append({
            "price": box["high"],
            "side": "high",
            "source": "LTF_BOX",
            "tf_class": "LTF",
            "id": f"{box_id}_H",
            "bar_index": 0,
            "forex_day": box.get("forex_day", ""),
            "valid_from": valid_from,
        })
        raw_levels.append({
            "price": box["low"],
            "side": "low",
            "source": "LTF_BOX",
            "tf_class": "LTF",
            "id": f"{box_id}_L",
            "bar_index": 0,
            "forex_day": box.get("forex_day", ""),
            "valid_from": valid_from,
        })

    # HTF EQH/EQL pools — untouched only, ranked by TF
    if htf_pools:
        htf_raw = []
        for pool in htf_pools:
            if pool.get("status") == "TAKEN":
                continue
            side = "high" if pool["type"] == "EQH" else "low"
            src = "HTF_EQH" if pool["type"] == "EQH" else "HTF_EQL"
            htf_raw.append({
                "price": pool["price"],
                "side": side,
                "source": src,
                "tf_class": "HTF",
                "id": f"{src}_{pool['timeframe']}_{pool['price']:.5f}",
                "tf_origin": pool["timeframe"],
                "bar_index": 0,
                "forex_day": "",
                "valid_from": pool.get("last_touch_time", ""),
                "_tf_rank": _TF_RANK.get(pool["timeframe"], 0),
            })
        htf_raw.sort(key=lambda x: -x["_tf_rank"])
        for lv in htf_raw:
            del lv["_tf_rank"]
        raw_levels.extend(htf_raw)

    # PWH/PWL — valid from week open (Sunday 17:00 NY)
    # Pipeline hardcodes '2024-01-07T17:00:00' for this dataset
    if pwh_pwl:
        valid_from = "2024-01-07T17:00:00"
        if "pwh" in pwh_pwl:
            raw_levels.append({
                "price": pwh_pwl["pwh"],
                "side": "high",
                "source": "PWH",
                "tf_class": "HTF",
                "id": "PWH",
                "bar_index": 0,
                "forex_day": "",
                "valid_from": valid_from,
            })
        if "pwl" in pwh_pwl:
            raw_levels.append({
                "price": pwh_pwl["pwl"],
                "side": "low",
                "source": "PWL",
                "tf_class": "HTF",
                "id": "PWL",
                "bar_index": 0,
                "forex_day": "",
                "valid_from": valid_from,
            })

    # Deduplicate non-swing levels
    deduped = _deduplicate_levels(raw_levels)

    # Merge nearby levels into pools (within tolerance)
    merged_non_swing = _merge_levels(deduped, merge_tol)

    # Combined: promoted swings + merged non-swing
    all_levels = promoted_swings + merged_non_swing

    return promoted_swings, merged_non_swing, all_levels, raw_levels


def _consume_pass_through_levels(
    levels: list,
    swept_levels: set,
    bar_low: float,
    bar_high: float,
    target_price: float,
    side: str,
    bar_index: int,
    bar_time: str,
    forex_day: str,
    tf_label: str,
) -> list:
    """Consume all same-side levels the bar physically crossed on its way to the target.

    Olya rule (2026-03-12): when price passes through a level on its way to a
    deeper target, the intermediate level's liquidity is taken. These levels
    are marked PASS_THROUGH_CONSUMED — hidden from chart, audit trail only.

    The bar's full range (low to high) defines the zone. Any same-side level
    within that range (other than the target itself) was physically crossed.

    Temporal guard: level.valid_from must be <= bar_time. Levels from future
    dates cannot be consumed before they exist.
    """
    consumed = []
    direction = "BEARISH" if side == "high" else "BULLISH"
    for lv in levels:
        if lv["side"] != side:
            continue
        lv_key = (lv["id"], lv["side"])
        if lv_key in swept_levels:
            continue
        # Temporal guard — level must be valid at bar time
        vf = lv.get("valid_from", "")
        if vf and bar_time < vf:
            continue
        lv_price = lv["price"]
        if abs(lv_price - target_price) < 1e-10:
            continue
        if bar_low < lv_price < bar_high:
            swept_levels.add(lv_key)
            consumed.append({
                "type": "PASS_THROUGH_CONSUMED",
                "direction": direction,
                "bar_index": bar_index,
                "time": bar_time,
                "level_price": lv_price,
                "source": lv["source"],
                "source_id": lv["id"],
                "bar_range": [round(bar_low, 6), round(bar_high, 6)],
                "target_level": target_price,
                "reason": "pass_through_consumption",
                "forex_day": forex_day,
                "tf": tf_label,
            })
    return consumed


def _count_session_boundaries(t_start: str, t_end: str) -> int:
    """Count how many forex session boundaries (Asia/London/NY/NYClose) passed.

    Both t_start and t_end are NY-time strings like '2024-01-08T09:15:00'.
    """
    if not t_start or not t_end or t_end <= t_start:
        return 0
    try:
        dt_s = datetime.strptime(t_start[:19], "%Y-%m-%dT%H:%M:%S")
        dt_e = datetime.strptime(t_end[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return 0
    count = 0
    cur = dt_s
    while cur < dt_e:
        next_day = cur.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        for bh in _SESSION_BOUNDARIES_NY:
            boundary = cur.replace(hour=bh, minute=0, second=0)
            if boundary <= cur:
                continue
            if boundary <= dt_e:
                count += 1
        cur = next_day
    return count


def _detect_base_sweeps(
    bars: pd.DataFrame,
    levels: list,
    atrs: list,
    params: dict,
    tf_label: str,
) -> tuple:
    """Detect sweeps and continuations using per-TF return window.

    Return windows: M1=2, M5=3, M15=4 (configurable via params).
    Wick rejection (0.40) checked across the full window (best wick of any bar).
    Pass-through consumption: when a breach occurs, all same-side levels
    between the target level and the breach extreme are consumed.

    Sweep event levels: when a qualified sweep confirms, the sweep extreme
    (bar.low for bullish, bar.high for bearish) is added to the pool as a
    new SWEEP_EVENT level eligible for future detection. Max recursion depth=2.

    Returns:
        (sweeps_list, continuations_list, swept_levels_set, pass_through_consumed_list)
    """
    min_breach_cfg = params.get("min_breach_pips", {}).get("per_tf", {})
    min_reclaim_cfg = params.get("min_reclaim_pips", {}).get("per_tf", {})

    tf_floors = {
        "1m": {"min_breach": 0.5, "min_reclaim": 0.5},
        "5m": {"min_breach": 0.5, "min_reclaim": 0.5},
        "15m": {"min_breach": 1.0, "min_reclaim": 1.0},
    }
    floors = tf_floors.get(tf_label, tf_floors["5m"])
    if tf_label in min_breach_cfg:
        floors["min_breach"] = min_breach_cfg[tf_label]
    if tf_label in min_reclaim_cfg:
        floors["min_reclaim"] = min_reclaim_cfg[tf_label]

    MIN_BREACH = floors["min_breach"] * PIP
    MIN_RECLAIM = floors["min_reclaim"] * PIP
    MAX_ATR_MULT = params.get("max_sweep_size_atr_mult", 1.5)
    MIN_REJ_WICK = params.get("rejection_wick_pct", {}).get("locked", 0.40)
    SWING_STALENESS = params.get("level_sources", {}).get("promoted_swing", {}).get("staleness_bars", 20)

    # Sweep event levels config
    se_cfg = params.get("level_sources", {}).get("sweep_event_levels", {})
    SE_ENABLED = se_cfg.get("enabled", False)
    SE_MAX_DEPTH = se_cfg.get("max_recursion_depth", 2)
    SE_MAX_AGE = se_cfg.get("max_age_sessions", 3)

    # Per-TF return window
    rw_cfg = params.get("return_window_bars", {})
    if isinstance(rw_cfg, dict) and "per_tf" in rw_cfg:
        rw_map = rw_cfg["per_tf"]
    elif isinstance(rw_cfg, dict):
        rw_map = rw_cfg
    else:
        rw_map = {}
    rw_defaults = {"1m": 2, "5m": 3, "15m": 4}
    RETURN_WINDOW = rw_map.get(tf_label, rw_defaults.get(tf_label, 3))

    sweeps = []
    continuations = []
    pass_through_consumed = []
    cont_seen = set()
    swept_levels = set()
    n = len(bars)
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15}.get(tf_label, 5)
    sweep_event_counter = 0

    for i in range(n):
        row = bars.iloc[i]
        if row.get("is_ghost", False):
            continue
        atr_val = atrs[i] if i < len(atrs) and atrs[i] is not None else None
        if atr_val is None:
            continue
        max_breach = MAX_ATR_MULT * atr_val
        bar_time = bar_time_str(row["timestamp_ny"], tf_minutes)

        # Iterate over a snapshot — new SWEEP_EVENT levels appended to `levels`
        # during this bar's iteration won't be visible until the next bar
        # (step ordering: confirm → consume → create, then next bar sees it).
        levels_snapshot = list(levels)
        for lv in levels_snapshot:
            lv_key = (lv["id"], lv["side"])
            if lv_key in swept_levels:
                continue

            # Temporal gate
            if lv["source"] == "PROMOTED_SWING":
                if lv["bar_index"] >= i:
                    continue
                if i - lv["bar_index"] > SWING_STALENESS:
                    continue
                bar_fd = row.get("forex_day", "")
                if bar_fd and lv.get("forex_day", "") and lv["forex_day"] != bar_fd:
                    continue
            elif lv["source"] == "SWEEP_EVENT":
                vf = lv.get("valid_from", "")
                if vf and bar_time <= vf:
                    continue
                if SE_MAX_AGE > 0 and _count_session_boundaries(vf, bar_time) > SE_MAX_AGE:
                    continue
            else:
                vf = lv.get("valid_from", "")
                if vf and bar_time < vf:
                    continue

            # BEARISH sweep candidate (wick above high-side level)
            if lv["side"] == "high" and row["high"] > lv["price"]:
                breach = row["high"] - lv["price"]
                if breach < MIN_BREACH:
                    continue

                closed_back = False
                return_bar_idx = i
                for j in range(i, min(i + RETURN_WINDOW, n)):
                    if bars.iloc[j]["close"] < lv["price"]:
                        closed_back = True
                        return_bar_idx = j
                        break

                if closed_back:
                    actual_rw = return_bar_idx - i + 1
                    confirm_bar = bars.iloc[return_bar_idx]
                    reclaim = lv["price"] - confirm_bar["close"]
                    if reclaim < MIN_RECLAIM:
                        pass
                    else:
                        if actual_rw == 1:
                            cr = row["high"] - row["low"]
                            best_rej = (row["high"] - max(row["open"], row["close"])) / cr if cr > 0 else 0.0
                        else:
                            peak_above = row["high"] - lv["price"]
                            reclaim_below = lv["price"] - confirm_bar["close"]
                            total_range = peak_above + reclaim_below
                            best_rej = reclaim_below / total_range if total_range > 0 else 0.0
                        if best_rej >= MIN_REJ_WICK:
                            confirm_time = bar_time_str(confirm_bar["timestamp_ny"], tf_minutes)
                            session_name = map_session(confirm_bar.get("session", "other"))
                            kill_zone = (
                                "LOKZ" if session_name == "lokz"
                                else "NYOKZ" if session_name == "nyokz"
                                else "NONE"
                            )
                            sweep_rec = {
                                "type": "SWEEP",
                                "direction": "BEARISH",
                                "bar_index": return_bar_idx,
                                "time": confirm_time,
                                "breach_bar": i,
                                "breach_time": bar_time,
                                "level_price": lv["price"],
                                "source": lv["source"],
                                "source_id": lv["id"],
                                "tf_class": lv.get("tf_class", "LTF"),
                                "sources_merged": lv.get("sources_merged", [lv["source"]]),
                                "touch_count": lv.get("touch_count", 1),
                                "breach_pips": round(breach / PIP, 1),
                                "reclaim_pips": round(reclaim / PIP, 1),
                                "rejection_wick_pct": round(best_rej, 3),
                                "return_window_used": actual_rw,
                                "return_bar": return_bar_idx,
                                "forex_day": row.get("forex_day", ""),
                                "session": session_name,
                                "kill_zone": kill_zone,
                                "tf": tf_label,
                            }
                            sweeps.append(sweep_rec)
                            swept_levels.add(lv_key)
                            # Step 2: consume pass-through levels
                            pass_through_consumed.extend(
                                _consume_pass_through_levels(
                                    levels, swept_levels,
                                    row["low"], row["high"],
                                    lv["price"], "high", i, bar_time,
                                    row.get("forex_day", ""), tf_label,
                                )
                            )
                            # Step 3: create sweep event level
                            if SE_ENABLED:
                                parent_depth = lv.get("_recursion_depth", 0)
                                if parent_depth < SE_MAX_DEPTH:
                                    sweep_event_counter += 1
                                    se_price = row["high"]
                                    se_id = f"SE_{sweep_event_counter}_{tf_label}_high"
                                    levels.append({
                                        "price": se_price,
                                        "side": "high",
                                        "source": "SWEEP_EVENT",
                                        "tf_class": "LTF",
                                        "id": se_id,
                                        "bar_index": return_bar_idx,
                                        "forex_day": row.get("forex_day", ""),
                                        "valid_from": confirm_time,
                                        "sources_merged": ["SWEEP_EVENT"],
                                        "touch_count": 1,
                                        "_recursion_depth": parent_depth + 1,
                                        "_parent_sweep_id": lv["id"],
                                        "_created_at": confirm_time,
                                    })
                            continue

                # No valid reclaim — check ATR cap for continuation
                if breach > max_breach:
                    cont_key = (lv["id"], "BEARISH")
                    if cont_key not in cont_seen:
                        cont_seen.add(cont_key)
                        session_name = map_session(row.get("session", "other"))
                        continuations.append({
                            "type": "CONTINUATION",
                            "direction": "BEARISH",
                            "bar_index": i,
                            "time": bar_time,
                            "level_price": lv["price"],
                            "source": lv["source"],
                            "source_id": lv["id"],
                            "breach_pips": round(breach / PIP, 1),
                            "forex_day": row.get("forex_day", ""),
                            "tf": tf_label,
                        })
                    swept_levels.add(lv_key)
                    pass_through_consumed.extend(
                        _consume_pass_through_levels(
                            levels, swept_levels,
                            row["low"], row["high"],
                            lv["price"], "high", i, bar_time,
                            row.get("forex_day", ""), tf_label,
                        )
                    )

            # BULLISH sweep candidate (wick below low-side level)
            if lv["side"] == "low" and row["low"] < lv["price"]:
                breach = lv["price"] - row["low"]
                if breach < MIN_BREACH:
                    continue

                closed_back = False
                return_bar_idx = i
                for j in range(i, min(i + RETURN_WINDOW, n)):
                    if bars.iloc[j]["close"] > lv["price"]:
                        closed_back = True
                        return_bar_idx = j
                        break

                if closed_back:
                    actual_rw = return_bar_idx - i + 1
                    confirm_bar = bars.iloc[return_bar_idx]
                    reclaim = confirm_bar["close"] - lv["price"]
                    if reclaim < MIN_RECLAIM:
                        pass
                    else:
                        if actual_rw == 1:
                            cr = row["high"] - row["low"]
                            best_rej = (min(row["open"], row["close"]) - row["low"]) / cr if cr > 0 else 0.0
                        else:
                            peak_below = lv["price"] - row["low"]
                            reclaim_above = confirm_bar["close"] - lv["price"]
                            total_range = peak_below + reclaim_above
                            best_rej = reclaim_above / total_range if total_range > 0 else 0.0
                        if best_rej >= MIN_REJ_WICK:
                            confirm_time = bar_time_str(confirm_bar["timestamp_ny"], tf_minutes)
                            session_name = map_session(confirm_bar.get("session", "other"))
                            kill_zone = (
                                "LOKZ" if session_name == "lokz"
                                else "NYOKZ" if session_name == "nyokz"
                                else "NONE"
                            )
                            sweep_rec = {
                                "type": "SWEEP",
                                "direction": "BULLISH",
                                "bar_index": return_bar_idx,
                                "time": confirm_time,
                                "breach_bar": i,
                                "breach_time": bar_time,
                                "level_price": lv["price"],
                                "source": lv["source"],
                                "source_id": lv["id"],
                                "tf_class": lv.get("tf_class", "LTF"),
                                "sources_merged": lv.get("sources_merged", [lv["source"]]),
                                "touch_count": lv.get("touch_count", 1),
                                "breach_pips": round(breach / PIP, 1),
                                "reclaim_pips": round(reclaim / PIP, 1),
                                "rejection_wick_pct": round(best_rej, 3),
                                "return_window_used": actual_rw,
                                "return_bar": return_bar_idx,
                                "forex_day": row.get("forex_day", ""),
                                "session": session_name,
                                "kill_zone": kill_zone,
                                "tf": tf_label,
                            }
                            sweeps.append(sweep_rec)
                            swept_levels.add(lv_key)
                            # Step 2: consume pass-through levels
                            pass_through_consumed.extend(
                                _consume_pass_through_levels(
                                    levels, swept_levels,
                                    row["low"], row["high"],
                                    lv["price"], "low", i, bar_time,
                                    row.get("forex_day", ""), tf_label,
                                )
                            )
                            # Step 3: create sweep event level
                            if SE_ENABLED:
                                parent_depth = lv.get("_recursion_depth", 0)
                                if parent_depth < SE_MAX_DEPTH:
                                    sweep_event_counter += 1
                                    se_price = row["low"]
                                    se_id = f"SE_{sweep_event_counter}_{tf_label}_low"
                                    levels.append({
                                        "price": se_price,
                                        "side": "low",
                                        "source": "SWEEP_EVENT",
                                        "tf_class": "LTF",
                                        "id": se_id,
                                        "bar_index": return_bar_idx,
                                        "forex_day": row.get("forex_day", ""),
                                        "valid_from": confirm_time,
                                        "sources_merged": ["SWEEP_EVENT"],
                                        "touch_count": 1,
                                        "_recursion_depth": parent_depth + 1,
                                        "_parent_sweep_id": lv["id"],
                                        "_created_at": confirm_time,
                                    })
                            continue

                # No valid reclaim — check ATR cap for continuation
                if breach > max_breach:
                    cont_key = (lv["id"], "BULLISH")
                    if cont_key not in cont_seen:
                        cont_seen.add(cont_key)
                        session_name = map_session(row.get("session", "other"))
                        continuations.append({
                            "type": "CONTINUATION",
                            "direction": "BULLISH",
                            "bar_index": i,
                            "time": bar_time,
                            "level_price": lv["price"],
                            "source": lv["source"],
                            "source_id": lv["id"],
                            "breach_pips": round(breach / PIP, 1),
                            "forex_day": row.get("forex_day", ""),
                            "tf": tf_label,
                        })
                    swept_levels.add(lv_key)
                    pass_through_consumed.extend(
                        _consume_pass_through_levels(
                            levels, swept_levels,
                            row["low"], row["high"],
                            lv["price"], "low", i, bar_time,
                            row.get("forex_day", ""), tf_label,
                        )
                    )

    return sweeps, continuations, swept_levels, pass_through_consumed


def _consume_dwelling_levels(
    bars: pd.DataFrame,
    levels: list,
    swept_levels: set,
    displacements: list,
    params: dict,
    tf_label: str,
) -> list:
    """Consume levels where price breaches and dwells beyond without reclaiming.

    After sweep/continuation detection, some levels are breached but fall through
    both paths (breach too small for continuation, reclaim too thin for sweep).
    This pass catches those by checking for consecutive closes beyond the level.

    A displacement override cancels consumption: if an opposite-direction
    displacement fires after the breach, the level stays alive (rejection signal).

    Returns list of CONSUMED records for audit trail.
    """
    dwell_cfg = params.get("dwell_consumption", {})
    dwell_counts = dwell_cfg.get("consecutive_closes", {})
    dwell_defaults = {"1m": 3, "5m": 3, "15m": 2}
    DWELL_BARS = dwell_counts.get(tf_label, dwell_defaults.get(tf_label, 2))

    min_reclaim_cfg = params.get("min_reclaim_pips", {}).get("per_tf", {})
    reclaim_defaults = {"1m": 0.5, "5m": 0.5, "15m": 1.0}
    MIN_RECLAIM_DWELL = min_reclaim_cfg.get(
        tf_label, reclaim_defaults.get(tf_label, 0.5)
    ) * PIP
    MIN_REJ_WICK = params.get("rejection_wick_pct", {}).get("locked", 0.40)

    disp_key = "atr1.5_br0.6"
    disp_by_idx = {}
    for d in displacements:
        q = d.get("qualifies", {}).get(disp_key, {})
        if q.get("and") or q.get("and_close") or q.get("override"):
            disp_by_idx[d["bar_index"]] = d

    MIN_BREACH = 0.5 * PIP
    n = len(bars)
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15}.get(tf_label, 5)
    consumed = []

    for lv in levels:
        lv_key = (lv["id"], lv["side"])
        if lv_key in swept_levels:
            continue

        vf = lv.get("valid_from", "")

        for i in range(n):
            if lv_key in swept_levels:
                break
            row = bars.iloc[i]
            if row.get("is_ghost", False):
                continue
            bar_time = bar_time_str(row["timestamp_ny"], tf_minutes)
            if vf and bar_time < vf:
                continue

            if lv["side"] == "high" and row["high"] > lv["price"]:
                breach = row["high"] - lv["price"]
                if breach < MIN_BREACH:
                    continue
                # Start condition: no qualifying sweep would fire for this breach.
                # A reclaim must pass MIN_RECLAIM + wick rejection to be valid.
                sweep_would_fire = False
                for j in range(i, min(i + DWELL_BARS + 2, n)):
                    cb = bars.iloc[j]
                    if cb["close"] < lv["price"]:
                        reclaim = lv["price"] - cb["close"]
                        if reclaim >= MIN_RECLAIM_DWELL:
                            rw = j - i + 1
                            if rw == 1:
                                cr = row["high"] - row["low"]
                                rej = (row["high"] - max(row["open"], row["close"])) / cr if cr > 0 else 0
                            else:
                                pa = row["high"] - lv["price"]
                                rb = lv["price"] - cb["close"]
                                rej = rb / (pa + rb) if (pa + rb) > 0 else 0
                            if rej >= MIN_REJ_WICK:
                                sweep_would_fire = True
                        break
                if sweep_would_fire:
                    continue
                # Check dwell: DWELL_BARS consecutive closes ABOVE level
                if i + DWELL_BARS > n:
                    continue
                dwell_ok = True
                for j in range(i, i + DWELL_BARS):
                    if bars.iloc[j]["close"] <= lv["price"]:
                        dwell_ok = False
                        break
                if not dwell_ok:
                    continue
                # Displacement override: opposite-direction displacement
                # after breach cancels consumption (level stays alive)
                opp_dir = "bearish"
                override = False
                for j in range(i, min(i + DWELL_BARS + 2, n)):
                    d = disp_by_idx.get(j)
                    if d and d["direction"] == opp_dir:
                        override = True
                        break
                if override:
                    continue
                swept_levels.add(lv_key)
                consumed.append({
                    "type": "CONSUMED",
                    "direction": "BEARISH",
                    "bar_index": i,
                    "time": bar_time,
                    "level_price": lv["price"],
                    "source": lv["source"],
                    "source_id": lv["id"],
                    "breach_pips": round(breach / PIP, 1),
                    "dwell_bars": DWELL_BARS,
                    "reason": "dwell_without_reclaim",
                    "forex_day": row.get("forex_day", ""),
                    "tf": tf_label,
                })

            elif lv["side"] == "low" and row["low"] < lv["price"]:
                breach = lv["price"] - row["low"]
                if breach < MIN_BREACH:
                    continue
                sweep_would_fire = False
                for j in range(i, min(i + DWELL_BARS + 2, n)):
                    cb = bars.iloc[j]
                    if cb["close"] > lv["price"]:
                        reclaim = cb["close"] - lv["price"]
                        if reclaim >= MIN_RECLAIM_DWELL:
                            rw = j - i + 1
                            if rw == 1:
                                cr = row["high"] - row["low"]
                                rej = (min(row["open"], row["close"]) - row["low"]) / cr if cr > 0 else 0
                            else:
                                pb = lv["price"] - row["low"]
                                ra = cb["close"] - lv["price"]
                                rej = ra / (pb + ra) if (pb + ra) > 0 else 0
                            if rej >= MIN_REJ_WICK:
                                sweep_would_fire = True
                        break
                if sweep_would_fire:
                    continue
                # Check dwell: DWELL_BARS consecutive closes BELOW level
                if i + DWELL_BARS > n:
                    continue
                dwell_ok = True
                for j in range(i, i + DWELL_BARS):
                    if bars.iloc[j]["close"] >= lv["price"]:
                        dwell_ok = False
                        break
                if not dwell_ok:
                    continue
                # Displacement override
                opp_dir = "bullish"
                override = False
                for j in range(i, min(i + DWELL_BARS + 2, n)):
                    d = disp_by_idx.get(j)
                    if d and d["direction"] == opp_dir:
                        override = True
                        break
                if override:
                    continue
                swept_levels.add(lv_key)
                consumed.append({
                    "type": "CONSUMED",
                    "direction": "BULLISH",
                    "bar_index": i,
                    "time": bar_time,
                    "level_price": lv["price"],
                    "source": lv["source"],
                    "source_id": lv["id"],
                    "breach_pips": round(breach / PIP, 1),
                    "dwell_bars": DWELL_BARS,
                    "reason": "dwell_without_reclaim",
                    "forex_day": row.get("forex_day", ""),
                    "tf": tf_label,
                })

    return consumed


def _qualify_sweeps(
    sweeps: list,
    displacements: list,
    params: dict,
) -> None:
    """Tag each sweep with qualified_sweep (displacement context). Tag only, not a gate."""
    lookback = params.get("qualified_sweep", {}).get("displacement_before_lookback", 10)
    forward = params.get("qualified_sweep", {}).get("displacement_after_forward", 5)
    disp_key = "atr1.5_br0.6"

    disp_by_idx = {}
    for d in displacements:
        q = d.get("qualifies", {}).get(disp_key, {})
        if q.get("and") or q.get("and_close") or q.get("override"):
            disp_by_idx[d["bar_index"]] = d

    for sw in sweeps:
        si = sw["bar_index"]
        sw_dir = sw["direction"]
        qualified = False
        qual_type = None

        opp_dir = "bearish" if sw_dir == "BULLISH" else "bullish"
        for j in range(max(0, si - lookback), si):
            d = disp_by_idx.get(j)
            if d and d["direction"] == opp_dir:
                qualified = True
                qual_type = "DISP_BEFORE"
                break

        if not qualified:
            same_dir = sw_dir.lower()
            for j in range(si, si + forward + 1):
                d = disp_by_idx.get(j)
                if d and d["direction"] == same_dir:
                    qualified = True
                    qual_type = "DISP_AFTER"
                    break

        sw["qualified_sweep"] = qualified
        sw["qualification_type"] = qual_type


class LiquiditySweepDetector(PrimitiveDetector):
    """Multi-source composite sweep detector with temporal gating."""

    primitive_name = "liquidity_sweep"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        return ["session_liquidity", "reference_levels", "htf_liquidity", "swing_points", "displacement"]

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        if upstream is None:
            raise ValueError(
                "LiquiditySweepDetector requires upstream results "
                "(session_liquidity, reference_levels, htf_liquidity, swing_points, displacement)"
            )

        tf_label = (context or {}).get("timeframe", "5m")
        tf_minutes = {"1m": 1, "5m": 5, "15m": 15}.get(tf_label, 5)
        bars_1m = (context or {}).get("bars_1m")  # Needed for session levels

        # Extract data from upstream detectors
        sess_result = upstream["session_liquidity"]
        ref_result = upstream["reference_levels"]
        htf_result = upstream["htf_liquidity"]
        swing_result = upstream["swing_points"]
        disp_result = upstream["displacement"]

        # Session levels: compute from 1m bars (like the pipeline does)
        # If bars_1m provided in context, use them; otherwise use the detection bars
        source_bars = bars_1m if bars_1m is not None else bars
        session_levels = _compute_session_levels(source_bars)
        session_boxes = _extract_session_boxes(sess_result)
        pdh_pdl = _extract_pdh_pdl(ref_result)
        pwh_pwl = _extract_pwh_pwl(ref_result)
        htf_pools = _extract_htf_pools(htf_result)
        swings = _extract_swings(swing_result)
        displacements = _extract_displacements(disp_result)

        # Build level pool
        promoted_swings, merged_non_swing, all_levels, raw_levels = _build_level_pool(
            session_levels, session_boxes, pdh_pdl, htf_pools, pwh_pwl, swings, params,
        )

        # Compute ATR
        atrs = compute_atr(bars, period=14)

        # Phase 1: Sweep + continuation detection (includes pass-through consumption)
        sweeps, continuations, swept_levels, pass_through = _detect_base_sweeps(
            bars, all_levels, atrs, params, tf_label,
        )

        # Phase 1b: Dwell consumption — catch levels breached but not
        # classified as sweep or continuation. Pass empty set so dwell
        # scans ALL levels independently. Prune phantoms in post-step.
        dwell_consumed = set()
        consumed = _consume_dwelling_levels(
            bars, all_levels, dwell_consumed, displacements, params, tf_label,
        )
        if consumed:
            dwell_events = {}
            for c in consumed:
                key = (c["source_id"], c["direction"])
                dwell_events[key] = c["bar_index"]
            before = len(sweeps)
            sweeps = [
                sw for sw in sweeps
                if (sw["source_id"], sw["direction"]) not in dwell_events
                or sw["bar_index"] <= dwell_events[(sw["source_id"], sw["direction"])]
            ]
            pruned = before - len(sweeps)
            if pruned:
                import logging
                logging.getLogger(__name__).info(
                    "Dwell pruned %d phantom sweep(s) on %s", pruned, tf_label,
                )

        # Phase 2: Tag sweeps with displacement qualification (tag, not gate)
        _qualify_sweeps(sweeps, displacements, params)

        # Build DetectionResult
        detections = []

        for sw in sweeps:
            det_dir = sw["direction"].lower()
            det = Detection(
                id=make_detection_id("sweep", tf_label, datetime.strptime(sw["time"], "%Y-%m-%dT%H:%M:%S"), det_dir),
                time=datetime.strptime(sw["time"], "%Y-%m-%dT%H:%M:%S"),
                direction=det_dir,
                type="sweep",
                price=sw["level_price"],
                properties=sw,
                tags={
                    "forex_day": sw.get("forex_day", ""),
                    "session": sw.get("session", ""),
                    "kill_zone": sw.get("kill_zone", ""),
                },
            )
            detections.append(det)

        for cont in continuations:
            det_dir = cont["direction"].lower()
            det = Detection(
                id=make_detection_id("sweep_cont", tf_label, datetime.strptime(cont["time"], "%Y-%m-%dT%H:%M:%S"), det_dir),
                time=datetime.strptime(cont["time"], "%Y-%m-%dT%H:%M:%S"),
                direction=det_dir,
                type="sweep_continuation",
                price=cont["level_price"],
                properties=cont,
                tags={"forex_day": cont.get("forex_day", "")},
            )
            detections.append(det)

        for cons in consumed:
            det_dir = cons["direction"].lower()
            det = Detection(
                id=make_detection_id("sweep_consumed", tf_label, datetime.strptime(cons["time"], "%Y-%m-%dT%H:%M:%S"), det_dir),
                time=datetime.strptime(cons["time"], "%Y-%m-%dT%H:%M:%S"),
                direction=det_dir,
                type="sweep_consumed",
                price=cons["level_price"],
                properties=cons,
                tags={"forex_day": cons.get("forex_day", "")},
            )
            detections.append(det)

        for pt in pass_through:
            det_dir = pt["direction"].lower()
            det = Detection(
                id=make_detection_id("sweep_pt_consumed", tf_label, datetime.strptime(pt["time"], "%Y-%m-%dT%H:%M:%S"), det_dir),
                time=datetime.strptime(pt["time"], "%Y-%m-%dT%H:%M:%S"),
                direction=det_dir,
                type="sweep_consumed",
                price=pt["level_price"],
                properties=pt,
                tags={"forex_day": pt.get("forex_day", "")},
            )
            detections.append(det)

        # Stats
        base_count = len(sweeps)
        qual_count = sum(1 for s in sweeps if s.get("qualified_sweep"))
        cont_count = len(continuations)
        consumed_count = len(consumed) + len(pass_through)
        se_created = sum(1 for lv in all_levels if lv.get("source") == "SWEEP_EVENT")
        se_swept = sum(1 for sw in sweeps if sw.get("source") == "SWEEP_EVENT")

        by_src = {}
        for sw in sweeps:
            by_src[sw["source"]] = by_src.get(sw["source"], 0) + 1

        pool_info = []
        for lv in all_levels:
            pool_info.append({
                "price": lv["price"],
                "side": lv["side"],
                "source": lv["source"],
                "id": lv["id"],
                "sources_merged": lv.get("sources_merged", [lv["source"]]),
            })

        return DetectionResult(
            primitive="liquidity_sweep",
            variant="a8ra_v1",
            timeframe=tf_label,
            detections=detections,
            metadata={
                "sweep_count": base_count,
                "qualified_count": qual_count,
                "continuation_count": cont_count,
                "consumed_count": consumed_count,
                "pass_through_consumed_count": len(pass_through),
                "sweep_event_levels_created": se_created,
                "sweep_event_levels_swept": se_swept,
                "source_distribution": by_src,
                "level_pool": pool_info,
            },
            params_used=params,
        )
