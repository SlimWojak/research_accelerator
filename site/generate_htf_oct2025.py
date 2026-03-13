#!/usr/bin/env python3
"""Generate Oct 2025 HTF detection data and merge with existing Jan 2024 data.

Loads Oct 2025 1m bars from River, aggregates to 1H/4H, runs the cascade
engine, converts detections to calibration page format, and merges into
existing JSON files (preserving Jan 2024 data).
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline"))

from ra.config.loader import load_config, get_locked_params
from ra.data.river_adapter import RiverAdapter
from ra.data.tf_aggregator import aggregate
from ra.evaluation.runner import EvaluationRunner, _build_all_locked_params
from ra.engine.cascade import CascadeEngine, build_default_registry

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

SITE_DIR = ROOT / "site"

# Constants matching preprocess_data_v2.py
DISP_ATR_MULTS = [1.0, 1.25, 1.5, 2.0]
DISP_BODY_RATIOS = [0.55, 0.60, 0.65, 0.70]
OB_STALENESS_BARS = [5, 10, 15, 20, 30]

FVG_THRESHOLDS_1H = [3.0, 5.0, 7.0, 10.0, 15.0, 20.0]
FVG_THRESHOLDS_4H = [5.0, 10.0, 15.0, 20.0, 30.0, 50.0]

SWING_HEIGHT_THRESHOLDS_1H = [5.0, 7.0, 10.0, 15.0, 20.0, 30.0]
SWING_HEIGHT_THRESHOLDS_4H = [10.0, 15.0, 20.0, 30.0, 50.0, 70.0]

EQUAL_HL_TOLERANCES_1H = [3.0, 5.0, 7.0, 10.0, 15.0]
EQUAL_HL_TOLERANCES_4H = [5.0, 10.0, 15.0, 20.0, 30.0]

TF_CONFIGS = {
    "1H": {
        "fvg_thresholds": FVG_THRESHOLDS_1H,
        "swing_height_thresholds": SWING_HEIGHT_THRESHOLDS_1H,
        "equal_tolerances": EQUAL_HL_TOLERANCES_1H,
    },
    "4H": {
        "fvg_thresholds": FVG_THRESHOLDS_4H,
        "swing_height_thresholds": SWING_HEIGHT_THRESHOLDS_4H,
        "equal_tolerances": EQUAL_HL_TOLERANCES_4H,
    },
}

PIP = 0.0001  # EURUSD pip size


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy/pandas types."""

    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.isoformat()
        return super().default(obj)


def _ts_to_str(ts):
    """Convert a timestamp to ISO string."""
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


# ─── Conversion: Detection objects → calibration page dicts ───────────


def convert_displacement(det) -> dict:
    """Convert a displacement Detection to calibration page dict."""
    # For displacement, properties IS the full disp dict already
    d = dict(det.properties)
    # Ensure time fields are strings
    if "time" in d and hasattr(d["time"], "isoformat"):
        d["time"] = d["time"].isoformat()
    if "time_end" in d and hasattr(d["time_end"], "isoformat"):
        d["time_end"] = d["time_end"].isoformat()
    return d


def convert_fvg(det) -> dict:
    """Convert an FVG Detection to calibration page dict."""
    d = dict(det.properties)
    # Add type (direction), forex_day, session from tags
    d["type"] = det.direction
    d["forex_day"] = det.tags.get("forex_day", "")
    d["session"] = det.tags.get("session", "")
    # Ensure time fields are strings
    for key in ("anchor_time", "detect_time", "ce_touched_time", "boundary_closed_time"):
        if key in d and d[key] is not None and hasattr(d[key], "isoformat"):
            d[key] = d[key].isoformat()
    return d


def convert_swing(det) -> dict:
    """Convert a swing_points Detection to calibration page dict."""
    d = {
        "type": det.direction,  # "high" or "low"
        "bar_index": det.properties.get("bar_index"),
        "time": _ts_to_str(det.properties.get("time", det.time)),
        "price": det.price,
        "strength": det.properties.get("strength"),
        "forex_day": det.tags.get("forex_day", ""),
        "session": det.tags.get("session", ""),
        "tf": det.properties.get("tf", ""),
        "height_pips": det.properties.get("height_pips", 0),
    }
    return d


def convert_mss(det) -> dict:
    """Convert an MSS Detection to calibration page dict."""
    d = dict(det.properties)
    # Ensure time fields are strings
    if "time" in d and hasattr(d["time"], "isoformat"):
        d["time"] = d["time"].isoformat()
    return d


def convert_ob(det) -> dict:
    """Convert an order_block Detection to calibration page dict."""
    d = dict(det.properties)
    # Ensure time fields are strings
    for key in ("ob_time", "disp_time"):
        if key in d and hasattr(d[key], "isoformat"):
            d[key] = d[key].isoformat()
    # Ensure retest times are strings
    if "retests" in d:
        for r in d["retests"]:
            if "time" in r and hasattr(r["time"], "isoformat"):
                r["time"] = r["time"].isoformat()
    return d


# ─── Stats computation ────────────────────────────────────────


def compute_disp_stats(displacements, forex_days):
    """Compute displacement stats per forex_day, matching preprocess format."""
    stats = {}
    for day in forex_days:
        day_disps = [d for d in displacements if d["forex_day"] == day]
        stats[day] = {}
        for atr_m in DISP_ATR_MULTS:
            for br in DISP_BODY_RATIOS:
                key = f"atr{atr_m}_br{br}"
                and_count = sum(
                    1 for d in day_disps
                    if d.get("qualifies", {}).get(key, {}).get("and", False)
                )
                or_count = sum(
                    1 for d in day_disps
                    if d.get("qualifies", {}).get(key, {}).get("or", False)
                )
                stats[day][key] = {"and": and_count, "or": or_count}
    return stats


def compute_fvg_stats(fvgs, forex_days, thresholds):
    """Compute FVG stats per forex_day and threshold."""
    stats = {}
    for day in forex_days:
        day_fvgs = [f for f in fvgs if f["forex_day"] == day]
        stats[day] = {}
        for t in thresholds:
            filtered = [f for f in day_fvgs if f["gap_pips"] >= t]
            stats[day][str(t)] = {
                "count": len(filtered),
                "bullish": sum(1 for f in filtered if f["type"] == "bullish"),
                "bearish": sum(1 for f in filtered if f["type"] == "bearish"),
                "vi_confluent": sum(1 for f in filtered if f.get("vi_confluent")),
                "median_gap": (
                    round(
                        sorted(f["gap_pips"] for f in filtered)[len(filtered) // 2], 2
                    )
                    if filtered
                    else 0
                ),
            }
    return stats


def compute_swing_stats(swings, forex_days, height_thresholds):
    """Compute swing stats per forex_day and height threshold."""
    stats = {}
    for day in forex_days:
        day_swings = [s for s in swings if s["forex_day"] == day]
        stats[day] = {}
        for t in height_thresholds:
            filtered = [s for s in day_swings if s["height_pips"] >= t]
            stats[day][str(t)] = {
                "count": len(filtered),
                "highs": sum(1 for s in filtered if s["type"] == "high"),
                "lows": sum(1 for s in filtered if s["type"] == "low"),
                "avg_strength": (
                    round(
                        sum(s["strength"] for s in filtered) / len(filtered), 1
                    )
                    if filtered
                    else 0
                ),
            }
    return stats


# ─── Equal highs/lows detection (from swings) ────────────────


def detect_equal_levels(swings, swing_type="high", tolerances=None):
    """Detect equal high/low pairs at various tolerances.

    Simplified version of preprocess_data_v2.detect_equal_levels.
    """
    if tolerances is None:
        tolerances = [3.0, 5.0, 7.0, 10.0, 15.0]
    max_tol = max(tolerances)
    typed = [s for s in swings if s["type"] == swing_type]
    pairs = []

    for i in range(len(typed)):
        for j in range(i + 1, len(typed)):
            diff = abs(typed[i]["price"] - typed[j]["price"]) / PIP
            if diff <= max_tol:
                # Determine role based on price action context
                role = "INTERNAL_STOP_POOL"

                pair = {
                    "type": swing_type,
                    "swing1_time": typed[i]["time"],
                    "swing2_time": typed[j]["time"],
                    "price1": typed[i]["price"],
                    "price2": typed[j]["price"],
                    "pip_diff": round(diff, 1),
                    "avg_price": (typed[i]["price"] + typed[j]["price"]) / 2,
                    "touches": 2,
                    "window": typed[i].get("session", ""),
                    "forex_day": typed[i].get("forex_day", ""),
                    "role": role,
                }
                pairs.append(pair)

    return pairs


# ─── Session levels computation ───────────────────────────────


def compute_session_levels(bars_1m, forex_days):
    """Compute session H/L levels per forex_day."""
    levels = []
    for day in forex_days:
        day_mask = bars_1m["forex_day"] == day
        day_bars = bars_1m[day_mask]
        if day_bars.empty:
            continue

        for sess_name in ["asia", "lokz", "nyokz"]:
            sess_bars = day_bars[day_bars["session"] == sess_name]
            if sess_bars.empty:
                continue
            h = float(sess_bars["high"].max())
            l = float(sess_bars["low"].min())
            first_time = _ts_to_str(sess_bars.iloc[0]["timestamp_ny"])
            levels.append({
                "type": f"{sess_name}_H",
                "price": h,
                "forex_day": day,
                "session": sess_name,
                "time": first_time,
            })
            levels.append({
                "type": f"{sess_name}_L",
                "price": l,
                "forex_day": day,
                "session": sess_name,
                "time": first_time,
            })

    return levels


# ─── Merge logic ──────────────────────────────────────────────


def load_json(path):
    """Load JSON file, return parsed dict."""
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    """Save data as JSON."""
    with open(path, "w") as f:
        json.dump(data, f, cls=NumpyEncoder)
    print(f"  Wrote {path}")


def merge_displacement(tf, new_disps, new_forex_days):
    """Merge Oct 2025 displacement detections into existing file."""
    path = SITE_DIR / f"displacement_data_{tf}.json"
    existing = load_json(path)

    # Append new displacements
    existing["displacements"].extend(new_disps)

    # Merge stats
    new_stats = compute_disp_stats(new_disps, new_forex_days)
    existing["stats"].update(new_stats)

    save_json(path, existing)
    print(f"    displacement_{tf}: +{len(new_disps)} → {len(existing['displacements'])} total")


def merge_fvg(tf, new_fvgs, new_forex_days):
    """Merge Oct 2025 FVG detections into existing file."""
    path = SITE_DIR / f"fvg_data_{tf}.json"
    existing = load_json(path)

    existing["fvgs"].extend(new_fvgs)

    thresholds = TF_CONFIGS[tf]["fvg_thresholds"]
    new_stats = compute_fvg_stats(new_fvgs, new_forex_days, thresholds)
    existing["stats"].update(new_stats)

    save_json(path, existing)
    print(f"    fvg_{tf}: +{len(new_fvgs)} → {len(existing['fvgs'])} total")


def merge_swing(tf, new_swings, new_eqh, new_eql, new_levels, new_forex_days):
    """Merge Oct 2025 swing detections into existing file."""
    path = SITE_DIR / f"swing_data_{tf}.json"
    existing = load_json(path)

    existing["swings"].extend(new_swings)
    existing["equal_highs"].extend(new_eqh)
    existing["equal_lows"].extend(new_eql)
    existing["session_levels"].extend(new_levels)

    thresholds = TF_CONFIGS[tf]["swing_height_thresholds"]
    new_stats = compute_swing_stats(new_swings, new_forex_days, thresholds)
    existing["stats"].update(new_stats)

    save_json(path, existing)
    print(f"    swing_{tf}: +{len(new_swings)} swings → {len(existing['swings'])} total")


def merge_mss(tf, new_events):
    """Merge Oct 2025 MSS events into existing file."""
    path = SITE_DIR / f"mss_data_{tf}.json"
    existing = load_json(path)

    existing["mss_events"].extend(new_events)

    save_json(path, existing)
    print(f"    mss_{tf}: +{len(new_events)} → {len(existing['mss_events'])} total")


def merge_ob(tf, new_obs):
    """Merge Oct 2025 order blocks into existing file."""
    path = SITE_DIR / f"ob_data_{tf}.json"
    existing = load_json(path)

    existing["order_blocks"].extend(new_obs)

    save_json(path, existing)
    print(f"    ob_{tf}: +{len(new_obs)} → {len(existing['order_blocks'])} total")


# ─── Main ─────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("Generating Oct 2025 HTF detections and merging with Jan 2024")
    print("=" * 60)

    # Step 1: Load Oct 2025 data
    print("\n1. Loading Oct 2025 1m bars from River...")
    adapter = RiverAdapter()
    bars_1m = adapter.load_bars("EURUSD", "2025-09-29", "2025-10-03")
    # Filter to weekdays only
    bars_1m = bars_1m[bars_1m["forex_day"] <= "2025-10-03"]
    print(f"   Loaded {len(bars_1m)} bars")

    forex_days = sorted(bars_1m["forex_day"].unique().tolist())
    print(f"   Forex days: {forex_days}")

    # Step 2: Aggregate
    print("\n2. Aggregating to all timeframes...")
    bars_5m = aggregate(bars_1m, "5m")
    bars_15m = aggregate(bars_1m, "15m")
    bars_1h = aggregate(bars_1m, "1H")
    bars_4h = aggregate(bars_1m, "4H")
    bars_1d = aggregate(bars_1m, "1D")
    print(f"   1H: {len(bars_1h)} bars, 4H: {len(bars_4h)} bars")

    bars_by_tf = {
        "1m": bars_1m,
        "5m": bars_5m,
        "15m": bars_15m,
        "1H": bars_1h,
        "4H": bars_4h,
        "1D": bars_1d,
    }

    # Step 3: Run cascade engine with HTF timeframes
    print("\n3. Running cascade engine (including 1H, 4H)...")
    config = load_config(str(ROOT / "configs" / "locked_baseline.yaml"))

    # Build engine directly to pass custom timeframes
    registry = build_default_registry()
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }
    engine = CascadeEngine(registry, dep_graph)
    params = _build_all_locked_params(config)

    results = engine.run(
        bars_by_tf,
        params,
        timeframes=["1m", "5m", "15m", "1H", "4H"],
    )

    # Show detection counts
    for prim_name in ["displacement", "fvg", "swing_points", "mss", "order_block"]:
        if prim_name in results:
            for tf in ["1H", "4H"]:
                if tf in results[prim_name]:
                    count = len(results[prim_name][tf].detections)
                    print(f"   {prim_name}/{tf}: {count} detections")

    # Step 4: Convert and merge for each TF
    for tf in ["1H", "4H"]:
        print(f"\n4. Processing {tf}...")

        # --- Displacement ---
        disp_dets = results.get("displacement", {}).get(tf)
        if disp_dets:
            new_disps = [convert_displacement(d) for d in disp_dets.detections]
        else:
            new_disps = []
        merge_displacement(tf, new_disps, forex_days)

        # --- FVG ---
        fvg_dets = results.get("fvg", {}).get(tf)
        if fvg_dets:
            new_fvgs = [convert_fvg(d) for d in fvg_dets.detections]
        else:
            new_fvgs = []
        merge_fvg(tf, new_fvgs, forex_days)

        # --- Swing Points ---
        swing_dets = results.get("swing_points", {}).get(tf)
        if swing_dets:
            new_swings = [convert_swing(d) for d in swing_dets.detections]
        else:
            new_swings = []

        # Equal highs/lows from swings
        tolerances = TF_CONFIGS[tf]["equal_tolerances"]
        new_eqh = detect_equal_levels(new_swings, "high", tolerances)
        new_eql = detect_equal_levels(new_swings, "low", tolerances)

        # Session levels from 1m bars
        new_levels = compute_session_levels(bars_1m, forex_days)

        merge_swing(tf, new_swings, new_eqh, new_eql, new_levels, forex_days)

        # --- MSS ---
        mss_dets = results.get("mss", {}).get(tf)
        if mss_dets:
            new_mss = [convert_mss(d) for d in mss_dets.detections]
        else:
            new_mss = []
        merge_mss(tf, new_mss)

        # --- Order Block ---
        ob_dets = results.get("order_block", {}).get(tf)
        if ob_dets:
            new_obs = [convert_ob(d) for d in ob_dets.detections]
        else:
            new_obs = []
        merge_ob(tf, new_obs)

    print("\n" + "=" * 60)
    print("Done! Oct 2025 HTF detections merged into existing files.")
    print("=" * 60)


if __name__ == "__main__":
    main()
