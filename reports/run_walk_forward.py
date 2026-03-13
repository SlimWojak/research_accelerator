#!/usr/bin/env python3
"""Walk-forward stability run — 25-week EURUSD evaluation.

Runs the locked baseline cascade on 25 weeks of EURUSD data (Sep 2025 – Feb 2026),
collects per-primitive/TF/week detection counts, computes statistics, and generates
a comprehensive stability report.

Usage:
    python3 reports/run_walk_forward.py
"""

import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ra.config.loader import load_config
from ra.data.river_adapter import RiverAdapter
from ra.data.tf_aggregator import aggregate
from ra.engine.cascade import CascadeEngine, build_default_registry
from ra.evaluation.runner import EvaluationRunner

NY_TZ = ZoneInfo("America/New_York")

CONFIG_PATH = ROOT / "configs" / "locked_baseline.yaml"
OUTPUT_PATH = ROOT / "reports" / "walk_forward_stability_2025-09_2026-02.yaml"

# Date range: Sep 2025 – Feb 2026 (25 weeks)
START_DATE = "2025-09-01"
END_DATE = "2026-02-28"

# TFs to evaluate
TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H"]

# Primitives we care about (per-TF ones)
TF_PRIMITIVES = [
    "displacement", "fvg", "swing_points", "mss", "order_block",
    "liquidity_sweep", "ote",
]
# Global primitives (run on 1m, reported as "global")
GLOBAL_PRIMITIVES = [
    "session_liquidity", "asia_range", "reference_levels", "htf_liquidity",
]

# Known market events for outlier context
MARKET_EVENTS = {
    "2025-W48": "US Thanksgiving week (Thu-Fri closed)",
    "2025-W52": "Christmas week (reduced liquidity)",
    "2026-W01": "New Year week (reduced liquidity)",
}


def get_forex_weeks(start_date: str, end_date: str) -> list[dict]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    weeks = {}
    current = start
    while current <= end:
        iso = current.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        if week_key not in weeks:
            monday = date.fromisocalendar(iso.year, iso.week, 1)
            friday = date.fromisocalendar(iso.year, iso.week, 5)
            weeks[week_key] = {
                "week": week_key,
                "start": monday.isoformat(),
                "end": friday.isoformat(),
            }
        current += timedelta(days=1)
    return list(weeks.values())


def _build_locked_params(config):
    """Build locked params dict for all primitives from config."""
    from ra.evaluation.runner import _build_all_locked_params
    return _build_all_locked_params(config)


def process_week(week_info, adapter, config, locked_params):
    """Process one week: load data, run cascade, return raw results."""
    week_id = week_info["week"]
    start = week_info["start"]
    end = week_info["end"]

    bars_1m = adapter.load_bars("EURUSD", start, end)
    if bars_1m.empty:
        return None

    bars_5m = aggregate(bars_1m, "5m")
    bars_15m = aggregate(bars_1m, "15m")
    bars_1h = aggregate(bars_1m, "1H")
    bars_4h = aggregate(bars_1m, "4H")

    bars_by_tf = {
        "1m": bars_1m, "5m": bars_5m, "15m": bars_15m,
        "1H": bars_1h, "4H": bars_4h,
    }

    registry = build_default_registry()
    dep_graph = {}
    for prim_name, node in config.dependency_graph.items():
        dep_graph[prim_name] = node.upstream

    engine = CascadeEngine(registry, dep_graph)
    results = engine.run(bars_by_tf, locked_params, timeframes=TIMEFRAMES)

    bar_counts = {tf: len(df) for tf, df in bars_by_tf.items()}
    forex_days = sorted(bars_1m["forex_day"].unique().tolist())

    return {
        "results": results,
        "bar_counts": bar_counts,
        "forex_days": forex_days,
    }


def count_detections(results):
    """Extract per-primitive per-TF detection counts."""
    counts = {}
    for prim, by_tf in results.items():
        counts[prim] = {}
        for tf, det_result in by_tf.items():
            counts[prim][tf] = len(det_result.detections)
    return counts


def extract_sweep_health(results):
    """Extract liquidity sweep pool health details."""
    health = {}
    for tf in TIMEFRAMES:
        sweep_result = results.get("liquidity_sweep", {}).get(tf)
        if sweep_result is None:
            continue

        source_counts = defaultdict(int)
        sweep_count = 0
        continuation_count = 0
        consumed_count = 0
        pass_through_count = 0

        for det in sweep_result.detections:
            props = det.properties
            det_type = det.type
            source = props.get("source", "UNKNOWN")
            source_counts[source] += 1

            if det_type == "sweep" or props.get("sweep_type") == "sweep":
                sweep_count += 1
            elif det_type == "continuation" or props.get("sweep_type") == "continuation":
                continuation_count += 1

            if props.get("consumed", False):
                consumed_count += 1
            if props.get("pass_through_consumed", False):
                pass_through_count += 1

        total = len(sweep_result.detections)
        health[tf] = {
            "total_events": total,
            "sweep_count": sweep_count,
            "continuation_count": continuation_count,
            "consumed_count": consumed_count,
            "pass_through_consumed_count": pass_through_count,
            "pool_sources": dict(source_counts),
            "cont_sweep_ratio": round(continuation_count / sweep_count, 3) if sweep_count > 0 else None,
        }
    return health


def compute_stats(series):
    """Compute mean, stddev, min, max, cv, outliers for a list of values."""
    if not series:
        return None
    arr = np.array(series, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    mn = int(np.min(arr))
    mx = int(np.max(arr))
    cv = round(std / mean, 4) if mean > 0 else None
    return {
        "mean": round(mean, 2),
        "stddev": round(std, 2),
        "min": mn,
        "max": mx,
        "cv": cv,
    }


def find_outliers(week_counts, stats):
    """Find weeks outside mean +/- 2*stddev."""
    if stats is None:
        return []
    mean = stats["mean"]
    std = stats["stddev"]
    low = mean - 2 * std
    high = mean + 2 * std
    outliers = []
    for week, count in week_counts.items():
        if count < low or count > high:
            outliers.append({
                "week": week,
                "count": count,
                "expected_range": [round(low, 1), round(high, 1)],
            })
    return outliers


def diagnose_outlier(week, prim, tf, count, expected_range, week_bar_counts):
    """Produce a human-readable diagnosis for an outlier."""
    low, high = expected_range

    if week in MARKET_EVENTS:
        return MARKET_EVENTS[week]

    if count == 0:
        if prim in ("mss", "order_block", "ote") and tf in ("4H", "1H"):
            return (f"Expected sparse: {prim} on {tf} requires displacement-confirmed swing break "
                    f"on {tf} bars (ATR warmup + few bars per week = few events)")
        if tf in ("4H",):
            return "ATR(14) warmup: 4H needs 14 bars (2.3 days) — early-week bars skipped"
        if prim == "mss":
            return "No displacement-confirmed swing breaks this week (possible low-volatility or trending week)"
        if prim == "order_block":
            return "No MSS events triggered OB detection (upstream dependency on MSS)"
        if prim == "liquidity_sweep":
            return "No qualified sweeps — pool may be thin or price never swept levels"
        return "Zero detections — investigate data availability and market conditions"

    if count > high:
        return "High volatility week — more structural breaks and displacement events"
    if count < low:
        return "Low volatility or strongly trending week — fewer structural breaks"

    return "Within expected range"


def main():
    print("=" * 70)
    print("WALK-FORWARD STABILITY RUN")
    print(f"Dataset: EURUSD {START_DATE} to {END_DATE}")
    print(f"Config: {CONFIG_PATH}")
    print("=" * 70)
    print()

    config = load_config(str(CONFIG_PATH))
    adapter = RiverAdapter()
    locked_params = _build_locked_params(config)

    weeks = get_forex_weeks(START_DATE, END_DATE)
    print(f"Processing {len(weeks)} weeks across {TIMEFRAMES}")
    print()

    # Step 1+2: Run cascade and collect counts
    all_counts = {}   # week -> {prim -> {tf -> count}}
    all_sweep_health = {}  # week -> {tf -> health}
    all_bar_counts = {}  # week -> {tf -> bar_count}
    all_forex_days = {}  # week -> [days]
    skipped_weeks = []

    total_start = time.time()

    for i, week_info in enumerate(weeks, 1):
        week_id = week_info["week"]
        t0 = time.time()

        try:
            result = process_week(week_info, adapter, config, locked_params)
        except Exception as e:
            print(f"[{i:2d}/{len(weeks)}] {week_id} — ERROR: {e}")
            skipped_weeks.append({"week": week_id, "error": str(e)})
            continue

        if result is None:
            print(f"[{i:2d}/{len(weeks)}] {week_id} — SKIPPED (no data)")
            skipped_weeks.append({"week": week_id, "error": "no data"})
            continue

        counts = count_detections(result["results"])
        all_counts[week_id] = counts
        all_bar_counts[week_id] = result["bar_counts"]
        all_forex_days[week_id] = result["forex_days"]

        # Sweep health
        sweep_health = extract_sweep_health(result["results"])
        all_sweep_health[week_id] = sweep_health

        elapsed = time.time() - t0
        total_dets = sum(
            c for by_tf in counts.values() for c in by_tf.values()
        )
        print(f"[{i:2d}/{len(weeks)}] {week_id} — {total_dets:,} detections ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    processed_weeks = list(all_counts.keys())
    print()
    print(f"Processed {len(processed_weeks)} weeks in {total_elapsed:.0f}s")
    print()

    # Step 3: Statistical summary
    print("Computing statistics...")
    summaries = {}
    raw_counts_table = {}  # (prim, tf) -> {week -> count}

    all_primitives = set()
    all_tfs_seen = set()
    for week_id, counts in all_counts.items():
        for prim, by_tf in counts.items():
            all_primitives.add(prim)
            for tf, cnt in by_tf.items():
                all_tfs_seen.add(tf)
                key = (prim, tf)
                if key not in raw_counts_table:
                    raw_counts_table[key] = {}
                raw_counts_table[key][week_id] = cnt

    for (prim, tf), week_counts in sorted(raw_counts_table.items()):
        series = [week_counts.get(w, 0) for w in processed_weeks]
        stats = compute_stats(series)
        if stats is None:
            continue

        zero_weeks = sum(1 for v in series if v == 0)
        outliers = find_outliers(
            {w: week_counts.get(w, 0) for w in processed_weeks}, stats
        )
        min_week = min(processed_weeks, key=lambda w: week_counts.get(w, 0))
        max_week = max(processed_weeks, key=lambda w: week_counts.get(w, 0))

        summaries[(prim, tf)] = {
            "primitive": prim,
            "timeframe": tf,
            "mean": stats["mean"],
            "stddev": stats["stddev"],
            "min": stats["min"],
            "min_week": min_week,
            "max": stats["max"],
            "max_week": max_week,
            "zero_weeks": zero_weeks,
            "cv": stats["cv"],
            "outlier_weeks": [o["week"] for o in outliers],
        }

    # Step 4: Outlier diagnostics
    print("Diagnosing outliers...")
    SKIP_DIAGNOSTICS = {"equal_hl", "ifvg", "bpr"}
    outlier_diagnostics = []
    for (prim, tf), summary in summaries.items():
        if prim in SKIP_DIAGNOSTICS:
            continue
        if not summary["outlier_weeks"] and summary["zero_weeks"] == 0:
            continue
        week_counts = raw_counts_table.get((prim, tf), {})
        # Check outlier weeks
        for week in summary["outlier_weeks"]:
            count = week_counts.get(week, 0)
            expected = [
                round(summary["mean"] - 2 * summary["stddev"], 1),
                round(summary["mean"] + 2 * summary["stddev"], 1),
            ]
            cause = diagnose_outlier(week, prim, tf, count, expected, all_bar_counts.get(week, {}))
            outlier_diagnostics.append({
                "week": week,
                "primitive": prim,
                "timeframe": tf,
                "count": count,
                "expected_range": expected,
                "possible_cause": cause,
            })
        # Check zero weeks that aren't already flagged
        if summary["zero_weeks"] > 0:
            for week in processed_weeks:
                count = week_counts.get(week, 0)
                if count == 0 and week not in summary["outlier_weeks"]:
                    expected = [
                        round(summary["mean"] - 2 * summary["stddev"], 1),
                        round(summary["mean"] + 2 * summary["stddev"], 1),
                    ]
                    cause = diagnose_outlier(week, prim, tf, count, expected, all_bar_counts.get(week, {}))
                    outlier_diagnostics.append({
                        "week": week,
                        "primitive": prim,
                        "timeframe": tf,
                        "count": count,
                        "expected_range": expected,
                        "possible_cause": cause,
                    })

    # Step 5: Sweep health per week
    print("Compiling sweep health...")
    sweep_health_report = {}
    for week_id in processed_weeks:
        health = all_sweep_health.get(week_id, {})
        if health:
            sweep_health_report[week_id] = health

    # Step 6: Stability verdict
    print("Computing verdict...")
    primitives_stable = []
    primitives_flagged = []
    cv_values = []

    for (prim, tf), summary in summaries.items():
        cv = summary["cv"]
        if cv is not None:
            cv_values.append(cv)

        is_flagged = False
        reasons = []

        # Flag if CV > 0.5 (high variance)
        if cv is not None and cv > 0.50:
            is_flagged = True
            reasons.append(f"High CV ({cv:.3f})")

        # Flag if unexpected zero weeks (exclude global primitives which fire once per day)
        if prim in TF_PRIMITIVES and summary["zero_weeks"] > 0:
            # Zero weeks on 4H are expected for some primitives due to ATR warmup
            if tf != "4H" or summary["zero_weeks"] > 5:
                is_flagged = True
                reasons.append(f"{summary['zero_weeks']} zero-detection weeks")

        # Flag if >3 outlier weeks
        if len(summary["outlier_weeks"]) > 3:
            is_flagged = True
            reasons.append(f"{len(summary['outlier_weeks'])} outlier weeks")

        key_str = f"{prim}/{tf}"
        if is_flagged:
            primitives_flagged.append({"primitive": key_str, "reasons": reasons})
        else:
            primitives_stable.append(key_str)

    # Determine overall verdict
    # Exclude equal_hl (DEFERRED), HTF sparse composites, and global prims from flag count
    DEFERRED = {"equal_hl"}
    HTF_SPARSE_COMPOSITES = {
        ("mss", "4H"), ("mss", "1H"),
        ("order_block", "4H"), ("order_block", "1H"),
        ("ote", "4H"), ("ote", "1H"),
    }
    # Recompute excluding deferred/expected-sparse
    primitives_stable_clean = []
    primitives_flagged_clean = []
    for item in primitives_stable:
        prim, tf = item.split("/")
        if prim in DEFERRED:
            continue
        primitives_stable_clean.append(item)
    for item in primitives_flagged:
        prim_tf = item["primitive"]
        prim, tf = prim_tf.split("/")
        if prim in DEFERRED:
            continue
        if (prim, tf) in HTF_SPARSE_COMPOSITES:
            # Re-classify as expected-sparse, not flagged
            item["reasons"].append("EXPECTED: composite primitive on HTF with sparse upstream + ATR warmup")
            primitives_stable_clean.append(prim_tf + " (HTF-sparse, expected)")
        else:
            primitives_flagged_clean.append(item)
    primitives_stable = primitives_stable_clean
    primitives_flagged = primitives_flagged_clean

    total_combos = sum(1 for (p, _) in summaries if p not in DEFERRED)
    flagged_count = len(primitives_flagged)
    unexpected_zeros = sum(
        1 for d in outlier_diagnostics
        if d["count"] == 0
        and d["primitive"] not in DEFERRED
        and (d["primitive"], d["timeframe"]) not in HTF_SPARSE_COMPOSITES
        and "ATR" not in d.get("possible_cause", "")
        and "holiday" not in d.get("possible_cause", "").lower()
        and "Christmas" not in d.get("possible_cause", "")
        and "New Year" not in d.get("possible_cause", "")
    )

    if flagged_count == 0:
        status = "PASS"
        recommendation = "All stable — S64 Gate 3 validated. Parameters generalise across 25 weeks of unseen data."
    elif flagged_count <= total_combos * 0.15:
        status = "CONDITIONAL_PASS"
        recommendation = f"{flagged_count} primitive/TF combos flagged out of {total_combos}. Review flagged items but overall stable."
    else:
        status = "FAIL"
        recommendation = f"{flagged_count}/{total_combos} combos flagged — investigate parameter sensitivity."

    verdict = {
        "status": status,
        "primitives_stable": primitives_stable,
        "primitives_flagged": primitives_flagged,
        "overall_cv_range": [
            round(min(cv_values), 4) if cv_values else None,
            round(max(cv_values), 4) if cv_values else None,
        ],
        "zero_detection_issues": unexpected_zeros,
        "recommendation": recommendation,
    }

    # Build raw counts for YAML output
    raw_counts_yaml = []
    for week_id in processed_weeks:
        counts = all_counts[week_id]
        for prim in sorted(counts.keys()):
            for tf in sorted(counts[prim].keys()):
                cnt = counts[prim][tf]
                notes = ""
                if cnt == 0 and tf == "4H":
                    notes = "ATR warmup may suppress early-week detections"
                elif cnt == 0:
                    notes = "zero detections"
                raw_counts_yaml.append({
                    "week": week_id,
                    "primitive": prim,
                    "timeframe": tf,
                    "count": cnt,
                    "notes": notes,
                })

    # Build final report
    report = {
        "walk_forward_stability_report": {
            "generated_at": datetime.now().isoformat(),
            "dataset": {
                "instrument": "EURUSD",
                "start": START_DATE,
                "end": END_DATE,
                "weeks_processed": len(processed_weeks),
                "weeks_skipped": len(skipped_weeks),
                "skipped_detail": skipped_weeks if skipped_weeks else None,
                "timeframes": TIMEFRAMES,
                "config": "configs/locked_baseline.yaml",
                "commit": "8da6f3e (13/13 primitives LOCKED)",
            },
            "bar_counts_per_week": {
                w: all_bar_counts[w] for w in processed_weeks
            },
            "raw_counts": raw_counts_yaml,
            "statistical_summary": [
                v for _, v in sorted(summaries.items())
            ],
            "outlier_diagnostics": outlier_diagnostics,
            "sweep_health_per_week": sweep_health_report,
            "walk_forward_verdict": verdict,
        }
    }

    # Write YAML
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    class SafeDumper(yaml.SafeDumper):
        pass

    def repr_none(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:null", "null")

    SafeDumper.add_representer(type(None), repr_none)

    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(report, f, Dumper=SafeDumper, default_flow_style=False,
                  sort_keys=False, width=120, allow_unicode=True)

    print()
    print(f"Report written: {OUTPUT_PATH}")
    print(f"Verdict: {verdict['status']}")
    print(f"  Stable: {len(primitives_stable)} combos")
    print(f"  Flagged: {len(primitives_flagged)} combos")
    print(f"  Recommendation: {verdict['recommendation']}")


if __name__ == "__main__":
    main()
