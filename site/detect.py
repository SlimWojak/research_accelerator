#!/usr/bin/env python3
"""CLI batch generator for Phase 3.5 validation mode.

Reads River parquet data, runs the cascade engine at locked params,
and outputs per-week slim detection JSON + candle JSON + session
boundaries + manifest.

Usage:
    python3 site/detect.py --start 2025-09-01 --end 2026-02-28 \
        --config configs/locked_baseline.yaml --output site/data/
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ra.config.loader import load_config, get_locked_params
from ra.data.river_adapter import RiverAdapter
from ra.data.tf_aggregator import aggregate
from ra.evaluation.runner import EvaluationRunner

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")


# ─── Locked threshold extraction & detection filtering ────────────────────


def _extract_locked_thresholds(config) -> dict:
    """Extract locked threshold values from config for detection filtering.

    Returns dict with keys: displacement, fvg, swing_points — each containing
    the locked values needed for filtering.
    """
    thresholds = {}

    # --- Displacement ---
    disp_params = config.primitives.displacement.params
    combo_mode = disp_params.combination_mode.locked  # "AND"
    atr_mult = disp_params.ltf.atr_multiplier["locked"]
    body_ratio = disp_params.ltf.body_ratio["locked"]
    thresholds["displacement"] = {
        "combination_mode": combo_mode,
        "atr_multiplier": float(atr_mult),
        "body_ratio": float(body_ratio),
    }

    # --- FVG ---
    fvg_floor = config.primitives.fvg.params.floor_threshold_pips.locked
    thresholds["fvg"] = {
        "floor_threshold_pips": float(fvg_floor),
    }

    # --- Swing Points ---
    sp_height = config.primitives.swing_points.params.height_filter_pips
    per_tf = sp_height["per_tf"]
    height_by_tf = {}
    for tf_key, tf_val in per_tf.items():
        if isinstance(tf_val, dict) and "locked" in tf_val:
            height_by_tf[tf_key] = float(tf_val["locked"])
        else:
            height_by_tf[tf_key] = float(tf_val)
    thresholds["swing_points"] = {
        "height_filter_pips": height_by_tf,
    }

    return thresholds


def _passes_locked_displacement(det, locked_atr: float, locked_body: float) -> bool:
    """Check if a displacement detection passes locked AND-mode thresholds.

    Checks the qualifies grid first (most reliable), then falls back to
    raw property values.  Also honours decisive overrides.
    """
    props = det.properties

    # 1. Check qualifies grid (computed by the displacement detector)
    qualifies = props.get("qualifies", {})
    key = f"atr{locked_atr}_br{locked_body}"
    if key in qualifies:
        q = qualifies[key]
        return q.get("and", False) or q.get("override", False)

    # 2. Fallback: raw property comparison (AND mode)
    atr = props.get("atr_multiple", 0)
    body = props.get("body_ratio", 0)
    if atr >= locked_atr and body >= locked_body:
        return True

    # 3. Decisive override: strong body + close location pass
    if body >= 0.75 and props.get("close_location_pass", False):
        return True

    return False


def _passes_locked_fvg(det, floor_pips: float) -> bool:
    """Check if an FVG detection meets the locked floor_threshold_pips."""
    return det.properties.get("gap_pips", 0) >= floor_pips


def _passes_locked_swing(det, height_by_tf: dict, tf: str) -> bool:
    """Check if a swing_points detection meets the locked height_filter_pips."""
    min_height = height_by_tf.get(tf)
    if min_height is None:
        return True  # no filter defined for this TF — keep
    return det.properties.get("height_pips", 0) >= min_height


def _filter_locked_detections(
    results: dict, thresholds: dict
) -> dict:
    """Filter raw engine results to only detections passing locked thresholds.

    Mutates nothing — returns a new results dict with the same structure
    (primitive -> tf -> DetectionResult) but with filtered detection lists.
    Logs per-primitive/tf raw → locked counts.
    """
    disp_th = thresholds.get("displacement", {})
    fvg_th = thresholds.get("fvg", {})
    swing_th = thresholds.get("swing_points", {})

    for prim_name, by_tf in results.items():
        for tf, det_result in by_tf.items():
            raw_count = len(det_result.detections)
            filtered = None

            if prim_name == "displacement":
                filtered = [
                    d for d in det_result.detections
                    if _passes_locked_displacement(
                        d,
                        disp_th.get("atr_multiplier", 1.5),
                        disp_th.get("body_ratio", 0.6),
                    )
                ]
            elif prim_name == "fvg":
                filtered = [
                    d for d in det_result.detections
                    if _passes_locked_fvg(
                        d, fvg_th.get("floor_threshold_pips", 0.5)
                    )
                ]
            elif prim_name == "swing_points":
                filtered = [
                    d for d in det_result.detections
                    if _passes_locked_swing(
                        d, swing_th.get("height_filter_pips", {}), tf
                    )
                ]

            if filtered is not None:
                dropped = raw_count - len(filtered)
                if dropped > 0:
                    print(f"  {prim_name}/{tf}: {raw_count} raw → "
                          f"{len(filtered)} locked (filtered {dropped})")
                det_result.detections = filtered

    return results


# Session band definitions (NY time) — matches site/session_boundaries.json format
SESSION_DEFS = [
    {
        "name": "asia",
        "start_hour": 19, "start_min": 0,
        "end_hour": 0, "end_min": 0,
        "label_fmt": "Asia 19:00\u201300:00",
        "color": "rgba(156,39,176,0.15)",
        "border": "rgba(156,39,176,0.5)",
        "crosses_midnight": True,
    },
    {
        "name": "lokz",
        "start_hour": 2, "start_min": 0,
        "end_hour": 5, "end_min": 0,
        "label_fmt": "LOKZ 02:00\u201305:00",
        "color": "rgba(41,98,255,0.10)",
        "border": "rgba(41,98,255,0.4)",
        "crosses_midnight": False,
    },
    {
        "name": "nyokz",
        "start_hour": 7, "start_min": 0,
        "end_hour": 10, "end_min": 0,
        "label_fmt": "NYOKZ 07:00\u201310:00",
        "color": "rgba(247,197,72,0.10)",
        "border": "rgba(247,197,72,0.4)",
        "crosses_midnight": False,
    },
    {
        "name": "ny_a",
        "start_hour": 8, "start_min": 0,
        "end_hour": 9, "end_min": 0,
        "label_fmt": "NY-A 08:00\u201309:00",
        "color": "rgba(239,83,80,0.06)",
        "border": "rgba(239,83,80,0.3)",
        "crosses_midnight": False,
    },
    {
        "name": "ny_b",
        "start_hour": 10, "start_min": 0,
        "end_hour": 11, "end_min": 0,
        "label_fmt": "NY-B 10:00\u201311:00",
        "color": "rgba(38,166,154,0.06)",
        "border": "rgba(38,166,154,0.3)",
        "crosses_midnight": False,
    },
]


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""

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
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def get_forex_weeks(start_date: str, end_date: str) -> list[dict]:
    """Compute forex weeks in the given date range.

    A forex week runs Monday through Friday. We group calendar dates
    into ISO weeks and return the Monday-Friday date range for each.

    Returns list of dicts with: week (ISO string), start (Monday date),
    end (Friday date), calendar_days (list of date strings Mon-Fri).
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    weeks = {}
    current = start
    while current <= end:
        iso = current.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"

        if week_key not in weeks:
            # Compute Monday of this ISO week
            monday = date.fromisocalendar(iso.year, iso.week, 1)
            friday = date.fromisocalendar(iso.year, iso.week, 5)
            weeks[week_key] = {
                "week": week_key,
                "start": monday.isoformat(),
                "end": friday.isoformat(),
                "calendar_days": [],
            }

        # Only include weekdays (Mon=1 through Fri=5)
        if current.isoweekday() <= 5:
            weeks[week_key]["calendar_days"].append(current.isoformat())

        current += timedelta(days=1)

    return list(weeks.values())


def slim_detection(det) -> dict:
    """Convert a Detection object to slim JSON format.

    Strips properties.qualifies, keeps useful fields.
    """
    props = {}
    for key, val in det.properties.items():
        if key == "qualifies":
            continue
        # Keep only useful properties for the UI
        if key in (
            "forex_day", "session", "tf", "body_ratio", "atr_multiple",
            "atr_value", "quality_grade", "displacement_type",
            "gap_pips", "height_pips", "range_pips", "body_pips",
            "bar_index", "N", "strength",
            "breach_pips", "reclaim_pips", "level_source", "level_price",
            "wick_pct", "sweep_size_atr", "swing_direction",
            "break_type", "confirmation_bars", "close_beyond",
            "ob_zone_high", "ob_zone_low", "trigger_type",
            "zone_high", "zone_low",
            "high", "low", "start_time", "end_time",
            "range_cap_pips", "classifications",
            "efficiency", "mid_crosses", "balance_score",
            "created_fvg", "ny_window_a", "ny_window_b",
        ):
            props[key] = val

    # Format time as ISO string
    t = det.time
    if hasattr(t, "isoformat"):
        time_str = t.isoformat()
    else:
        time_str = str(t)

    return {
        "id": det.id,
        "time": time_str,
        "direction": det.direction,
        "type": det.type,
        "price": det.price,
        "properties": props,
    }


def build_candle_json(bars_1m: pd.DataFrame, bars_5m: pd.DataFrame,
                      bars_15m: pd.DataFrame) -> dict:
    """Build candle JSON with 1m/5m/15m arrays."""
    def bars_to_list(df: pd.DataFrame) -> list[dict]:
        records = []
        for _, row in df.iterrows():
            ts = row["timestamp_ny"]
            if hasattr(ts, "isoformat"):
                time_str = ts.isoformat()
            else:
                time_str = str(ts)
            records.append({
                "time": time_str,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
        return records

    return {
        "1m": bars_to_list(bars_1m),
        "5m": bars_to_list(bars_5m),
        "15m": bars_to_list(bars_15m),
    }


def build_session_boundaries(bars_1m: pd.DataFrame) -> list[dict]:
    """Build session boundary entries from 1m bar data.

    For each forex day in the data, generate session boundaries for
    Asia, LOKZ, NYOKZ, NY-A, NY-B — same format as site/session_boundaries.json.
    """
    boundaries = []
    forex_days = sorted(bars_1m["forex_day"].unique())

    for fd in forex_days:
        fd_bars = bars_1m[bars_1m["forex_day"] == fd]
        if fd_bars.empty:
            continue

        for sess_def in SESSION_DEFS:
            sess_name = sess_def["name"]
            # Filter bars matching this session (or ny_window for ny_a/ny_b)
            if sess_name in ("ny_a", "ny_b"):
                window_key = sess_name.replace("ny_", "")
                mask = fd_bars["ny_window"] == window_key
            else:
                mask = fd_bars["session"] == sess_name

            sess_bars = fd_bars[mask]
            if sess_bars.empty:
                continue

            start_ts = sess_bars["timestamp_ny"].iloc[0]
            end_ts = sess_bars["timestamp_ny"].iloc[-1]

            # Compute session window times from the forex day
            fd_date = date.fromisoformat(fd)
            sh, sm = sess_def["start_hour"], sess_def["start_min"]
            eh, em = sess_def["end_hour"], sess_def["end_min"]

            if sess_def["crosses_midnight"]:
                # Asia: starts previous evening
                prev_day = fd_date - timedelta(days=1)
                start_time = f"{prev_day.isoformat()}T{sh:02d}:{sm:02d}:00"
                end_time = f"{fd}T{eh:02d}:{em:02d}:00"
            else:
                start_time = f"{fd}T{sh:02d}:{sm:02d}:00"
                end_time = f"{fd}T{eh:02d}:{em:02d}:00"

            boundaries.append({
                "forex_day": fd,
                "session": sess_name,
                "start_time": start_time,
                "end_time": end_time,
                "label": sess_def["label_fmt"],
                "color": sess_def["color"],
                "border": sess_def["border"],
            })

    return boundaries


def build_locked_params_snapshot(config) -> dict:
    """Build a snapshot of all locked parameters from config."""
    primitives = {}
    prim_names = [
        "fvg", "swing_points", "displacement", "session_liquidity",
        "asia_range", "mss", "order_block", "liquidity_sweep",
        "htf_liquidity", "ote", "reference_levels",
    ]
    for prim in prim_names:
        try:
            primitives[prim] = get_locked_params(config, prim)
        except Exception:
            pass

    return {
        "schema_version": config.schema_version,
        "instrument": config.instrument,
        "primitives": primitives,
    }


def process_week(week_info: dict, config, adapter: RiverAdapter,
                 runner: EvaluationRunner, output_dir: Path) -> dict:
    """Process a single forex week: load bars, run detection, write outputs.

    Returns manifest entry for this week.
    """
    week_id = week_info["week"]
    start_date = week_info["start"]
    end_date = week_info["end"]

    # Load 1m bars for this week
    bars_1m = adapter.load_bars("EURUSD", start_date, end_date)

    if bars_1m.empty:
        return None

    # Aggregate to 5m and 15m
    bars_5m = aggregate(bars_1m, "5m")
    bars_15m = aggregate(bars_1m, "15m")

    bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

    # Run cascade at locked params
    results = runner.run_locked(bars_by_tf)

    # Filter detections to only those passing locked thresholds
    locked_thresholds = _extract_locked_thresholds(config)
    results = _filter_locked_detections(results, locked_thresholds)

    # Build slim detections organized by primitive and timeframe
    detections_by_primitive = {}
    total_detection_count = 0

    for prim_name, by_tf in results.items():
        prim_dets = {}
        for tf, det_result in by_tf.items():
            slim_dets = [slim_detection(d) for d in det_result.detections]
            if slim_dets:
                prim_dets[tf] = slim_dets
                total_detection_count += len(slim_dets)
        if prim_dets:
            detections_by_primitive[prim_name] = prim_dets

    # Build detection JSON
    detection_data = {
        "week": week_id,
        "config": "current_locked",
        "generated_at": datetime.now().isoformat(),
        "detections_by_primitive": detections_by_primitive,
    }

    # Build candle JSON
    candle_data = build_candle_json(bars_1m, bars_5m, bars_15m)

    # Build session boundaries
    session_data = build_session_boundaries(bars_1m)

    # Get forex days from bar data
    forex_days = sorted(bars_1m["forex_day"].unique().tolist())

    # Write detection file
    det_dir = output_dir / "detections"
    det_dir.mkdir(parents=True, exist_ok=True)
    det_path = det_dir / f"{week_id}.json"
    with open(det_path, "w") as f:
        json.dump(detection_data, f, cls=NumpyEncoder, separators=(",", ":"))

    # Write candle file
    candle_dir = output_dir / "candles"
    candle_dir.mkdir(parents=True, exist_ok=True)
    candle_path = candle_dir / f"{week_id}.json"
    with open(candle_path, "w") as f:
        json.dump(candle_data, f, cls=NumpyEncoder, separators=(",", ":"))

    # Write session boundaries file
    session_dir = output_dir / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / f"{week_id}.json"
    with open(session_path, "w") as f:
        json.dump(session_data, f, cls=NumpyEncoder, separators=(",", ":"))

    return {
        "week": week_id,
        "start": start_date,
        "end": end_date,
        "forex_days": forex_days,
        "detection_count": total_detection_count,
        "bars_1m": len(bars_1m),
        "bars_5m": len(bars_5m),
        "bars_15m": len(bars_15m),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate per-week detection and candle data for validation mode."
    )
    parser.add_argument(
        "--start", required=True,
        help="Start date (YYYY-MM-DD), inclusive"
    )
    parser.add_argument(
        "--end", required=True,
        help="End date (YYYY-MM-DD), inclusive"
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to config YAML (e.g. configs/locked_baseline.yaml)"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory (e.g. site/data/)"
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    config = load_config(args.config)

    # Initialize River adapter and evaluation runner
    adapter = RiverAdapter()
    runner = EvaluationRunner(config)

    # Compute forex weeks
    weeks = get_forex_weeks(args.start, args.end)
    total_weeks = len(weeks)

    print(f"Generating validation data: {total_weeks} weeks "
          f"({args.start} to {args.end})")
    print()

    manifest = []
    total_start = time.time()

    for i, week_info in enumerate(weeks, 1):
        t0 = time.time()

        try:
            entry = process_week(week_info, config, adapter, runner, output_dir)
        except Exception as e:
            print(f"[{i}/{total_weeks}] {week_info['week']} — ERROR: {e}")
            logger.warning("Failed to process week %s: %s",
                           week_info["week"], e)
            continue

        if entry is None:
            print(f"[{i}/{total_weeks}] {week_info['week']} — skipped "
                  f"(no data)")
            continue

        elapsed = time.time() - t0
        det_count = entry["detection_count"]
        manifest.append(entry)

        print(f"[{i}/{total_weeks}] {entry['week']} — "
              f"{det_count:,} detections ({elapsed:.1f}s)")

    # Write manifest
    manifest_path = output_dir / "weeks.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, cls=NumpyEncoder, indent=2)

    # Write locked params snapshot
    params_dir = output_dir / "params"
    params_dir.mkdir(parents=True, exist_ok=True)
    params_path = params_dir / "locked.json"
    locked_snapshot = build_locked_params_snapshot(config)
    with open(params_path, "w") as f:
        json.dump(locked_snapshot, f, cls=NumpyEncoder, indent=2)

    total_elapsed = time.time() - total_start
    total_dets = sum(e["detection_count"] for e in manifest)

    print()
    print(f"Done: {len(manifest)} weeks, {total_dets:,} total detections "
          f"in {total_elapsed:.1f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
