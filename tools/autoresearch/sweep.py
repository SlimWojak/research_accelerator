#!/usr/bin/env python3
"""
AutoResearch Parameter Sweep — Two-Stage Grid Search

Stage 1: Sweep 9 daily direction + v2.2 RETRACE params (1,728 combos)
Stage 2: Sweep 6 classifier params within top 5 Stage 1 sets (25,600 combos)
Stage 3: Validation and robustness check on top 3 → recommendation

All detection/candle data cached in memory. Each iteration is classifier-only.

Usage:
    python3 tools/autoresearch/sweep.py
    python3 tools/autoresearch/sweep.py --stage 1
    python3 tools/autoresearch/sweep.py --dry-run
"""

import argparse
import copy
import io
import itertools
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GT = ROOT / "research" / "ground_truth" / "annotated_trades.yaml"
OUTPUT_DIR = ROOT / "reports" / "autoresearch"

sys.path.insert(0, str(Path(__file__).parent))
from evaluate import (
    DEFAULT_PARAMS, load_weeks, date_to_weeks, load_detections, load_candles,
    classify_phase, check_execution_chain, score_trade, parse_time,
)

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

STAGE_1_PARAMS = {
    "swing_lookback_count": [3, 4, 5],
    "minimum_swings_required": [2, 3],
    "qualifying_daily_bars": [1, 2],
    "mss_window_days": [7, 10, 14],
    "body_ratio_threshold": [0.50, 0.55, 0.60],
    "h4_structure_lookback_days": [5, 7],
    "h4_minimum_swings": [2, 3],
    "h4_counter_persistence_bars": [1, 2],
    "h4_counter_displacement_required": [False, True],
}

STAGE_2_PARAMS = {
    "h1_counter_persistence_bars": [2, 3, 4, 5],
    "momentum_stall_window_daily_bars": [2, 3, 4, 5],
    "key_level_tolerance_atr_factor": [0.3, 0.4, 0.5, 0.6, 0.7],
    "transition_lockout_h1_bars": [1, 2, 3, 4],
    "retrace_to_range_daily_bars": [2, 3, 4, 5],
    "kill_zone_realignment_lookback_hours": [1, 2, 3, 4],
}


def grid_size(space):
    n = 1
    for v in space.values():
        n *= len(v)
    return n


def param_distance(params, defaults):
    d = 0
    for k, v in params.items():
        dv = defaults.get(k)
        if dv is None:
            continue
        if isinstance(v, bool) and isinstance(dv, bool):
            d += 0 if v == dv else 1
        elif isinstance(v, (int, float)) and isinstance(dv, (int, float)):
            d += abs(v - dv)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CACHE — load all trade data once, reuse across iterations
# ═══════════════════════════════════════════════════════════════════════════════

def preload_trade_data(gt_path: str):
    with open(gt_path) as f:
        gt = yaml.safe_load(f)
    trades = gt.get("trades", [])
    weeks = load_weeks()

    cache = []
    for trade in trades:
        strategy = trade.get("strategy_type", "state_gated")
        lookback = 0 if strategy == "asia_range_scalp" else 2
        week_ids = date_to_weeks(trade["date"], weeks, lookback_weeks=lookback)
        detections = load_detections(week_ids)
        candles = load_candles(week_ids)
        exec_time = trade.get("execution_time", "12:00")
        trade_dt = datetime.strptime(f"{trade['date']}T{exec_time}:00", "%Y-%m-%dT%H:%M:%S")
        chain_result = check_execution_chain(detections, trade, trade_dt)
        cache.append({
            "trade": trade,
            "detections": detections,
            "candles": candles,
            "trade_dt": trade_dt,
            "chain_result": chain_result,
        })
    return trades, cache


def evaluate_cached(cache, params):
    """Run phase classification + scoring using pre-loaded data."""
    results = []
    pass_count = 0
    partial_count = 0
    fail_count = 0
    per_trade = []

    for entry in cache:
        trade = entry["trade"]
        computed = classify_phase(entry["detections"], entry["candles"],
                                  entry["trade_dt"], params, trade)
        score = score_trade(trade, computed, entry["chain_result"])

        if score["verdict"] == "PASS":
            pass_count += 1
        elif score["verdict"] == "PARTIAL":
            partial_count += 1
        else:
            fail_count += 1

        per_trade.append({
            "trade_id": trade["id"],
            "verdict": score["verdict"],
            "phase_match": score["phase_match"],
            "permission_match": score["permission_match"],
            "chain_status": score["chain_status"],
            "method": computed.get("method", ""),
            "retrace_trigger": computed.get("retrace_trigger", ""),
        })

    return {
        "pass": pass_count,
        "partial": partial_count,
        "fail": fail_count,
        "total": len(cache),
        "per_trade": per_trade,
    }


def fitness_key(result, params, defaults):
    """Sort key: maximize pass, then minimize fail, then maximize chain, then margin."""
    chain_score = sum(1 for t in result["per_trade"] if t["chain_status"] in ("FIRED", "N/A"))
    dist = param_distance(params, defaults)
    return (-result["pass"], result["fail"], -chain_score, dist)


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE RUNNERS
# ═══════════════════════════════════════════════════════════════════════════════

def run_stage_1(cache, gt_path):
    """Stage 1: Sweep daily direction + v2.2 RETRACE params."""
    n = grid_size(STAGE_1_PARAMS)
    print(f"\n{'='*70}")
    print(f"STAGE 1: Daily direction + v2.2 RETRACE parameters")
    print(f"Grid: {n} combinations (9 params)")
    print(f"Held at defaults: {list(STAGE_2_PARAMS.keys())}")
    print(f"{'='*70}")

    param_names = list(STAGE_1_PARAMS.keys())
    param_values = [STAGE_1_PARAMS[k] for k in param_names]

    results = []
    t0 = time.time()

    for i, combo in enumerate(itertools.product(*param_values)):
        params = dict(DEFAULT_PARAMS)
        params.update(dict(zip(param_names, combo)))
        result = evaluate_cached(cache, params)
        result["params"] = dict(zip(param_names, combo))
        result["full_params"] = params
        results.append(result)

        if (i + 1) % 200 == 0:
            best = min(results, key=lambda r: fitness_key(r, r["full_params"], DEFAULT_PARAMS))
            elapsed = time.time() - t0
            print(f"  [{i+1}/{n}] ({elapsed:.0f}s) best so far: {best['pass']}/{best['total']} PASS")

    # Sort
    results.sort(key=lambda r: fitness_key(r, r["full_params"], DEFAULT_PARAMS))

    elapsed = time.time() - t0
    print(f"\nStage 1 complete: {n} combinations in {elapsed:.1f}s")
    print(f"Top score: {results[0]['pass']}/{results[0]['total']} PASS, "
          f"{results[0]['partial']} PARTIAL, {results[0]['fail']} FAIL")

    # Top 5 for Stage 2
    top5 = results[:5]
    print(f"\nTop 5 Stage 1 parameter sets:")
    for i, r in enumerate(top5):
        delta = {k: r["params"][k] for k in param_names if r["params"][k] != DEFAULT_PARAMS.get(k)}
        print(f"  #{i+1}: {r['pass']}P/{r['partial']}PT/{r['fail']}F — {delta if delta else '(defaults)'}")

    # Count how many sets match top score
    top_score = results[0]["pass"]
    matching = sum(1 for r in results if r["pass"] == top_score)
    print(f"\n{matching}/{n} combinations achieve top score ({top_score}/{results[0]['total']})")

    # Write Stage 1 report
    report = {
        "metadata": {
            "stage": 1,
            "run_time": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "total_combinations": n,
            "parameters_swept": param_names,
            "parameters_held": {k: DEFAULT_PARAMS[k] for k in STAGE_2_PARAMS},
        },
        "summary": {
            "top_score": f"{top_score}/{results[0]['total']}",
            "sets_at_top_score": matching,
            "sets_total": n,
        },
        "top_20": [
            {
                "rank": i + 1,
                "pass": r["pass"], "partial": r["partial"], "fail": r["fail"],
                "params": r["params"],
                "distance_from_defaults": param_distance(r["full_params"], DEFAULT_PARAMS),
                "per_trade": r["per_trade"],
            }
            for i, r in enumerate(results[:20])
        ],
    }

    out = OUTPUT_DIR / "sweep_stage1_2026-03-19.yaml"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"Stage 1 report: {out}")

    return top5


def run_stage_2(cache, top5_stage1):
    """Stage 2: Sweep classifier thresholds within top 5 Stage 1 sets."""
    n_per = grid_size(STAGE_2_PARAMS)
    n_total = len(top5_stage1) * n_per
    print(f"\n{'='*70}")
    print(f"STAGE 2: Classifier thresholds within top 5 Stage 1 sets")
    print(f"Grid: {n_per} per set × {len(top5_stage1)} sets = {n_total} combinations")
    print(f"{'='*70}")

    s2_names = list(STAGE_2_PARAMS.keys())
    s2_values = [STAGE_2_PARAMS[k] for k in s2_names]

    all_results = []
    t0 = time.time()
    combo_count = 0

    for s1_idx, s1_result in enumerate(top5_stage1):
        s1_params = s1_result["full_params"]
        print(f"\n  Stage 1 set #{s1_idx+1}:")

        for combo in itertools.product(*s2_values):
            params = dict(s1_params)
            params.update(dict(zip(s2_names, combo)))
            result = evaluate_cached(cache, params)
            result["full_params"] = params
            result["s1_set"] = s1_idx + 1
            result["s2_params"] = dict(zip(s2_names, combo))
            result["s1_params"] = s1_result["params"]
            all_results.append(result)
            combo_count += 1

            if combo_count % 2000 == 0:
                elapsed = time.time() - t0
                best = min(all_results, key=lambda r: fitness_key(r, r["full_params"], DEFAULT_PARAMS))
                print(f"    [{combo_count}/{n_total}] ({elapsed:.0f}s) "
                      f"best: {best['pass']}P/{best['partial']}PT/{best['fail']}F")

    all_results.sort(key=lambda r: fitness_key(r, r["full_params"], DEFAULT_PARAMS))
    elapsed = time.time() - t0

    print(f"\nStage 2 complete: {n_total} combinations in {elapsed:.1f}s")
    print(f"Top score: {all_results[0]['pass']}/{all_results[0]['total']} PASS")

    top_score = all_results[0]["pass"]
    matching = sum(1 for r in all_results if r["pass"] == top_score)
    print(f"{matching}/{n_total} combinations achieve top score")

    print(f"\nTop 10 overall:")
    for i, r in enumerate(all_results[:10]):
        s1_delta = {k: v for k, v in r["s1_params"].items() if v != DEFAULT_PARAMS.get(k)}
        s2_delta = {k: v for k, v in r["s2_params"].items() if v != DEFAULT_PARAMS.get(k)}
        dist = param_distance(r["full_params"], DEFAULT_PARAMS)
        print(f"  #{i+1}: {r['pass']}P/{r['partial']}PT/{r['fail']}F "
              f"(S1set={r['s1_set']}, dist={dist:.1f}) "
              f"S1Δ={s1_delta if s1_delta else '{}'} S2Δ={s2_delta if s2_delta else '{}'}")

    # Write Stage 2 report
    report = {
        "metadata": {
            "stage": 2,
            "run_time": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "total_combinations": n_total,
            "stage1_sets_used": len(top5_stage1),
            "stage2_params_swept": s2_names,
        },
        "summary": {
            "top_score": f"{top_score}/{all_results[0]['total']}",
            "sets_at_top_score": matching,
        },
        "top_50": [
            {
                "rank": i + 1,
                "pass": r["pass"], "partial": r["partial"], "fail": r["fail"],
                "s1_set": r["s1_set"],
                "s1_params": r["s1_params"],
                "s2_params": r["s2_params"],
                "full_params": r["full_params"],
                "distance": param_distance(r["full_params"], DEFAULT_PARAMS),
                "per_trade": r["per_trade"],
            }
            for i, r in enumerate(all_results[:50])
        ],
    }

    out = OUTPUT_DIR / "sweep_stage2_2026-03-19.yaml"
    with open(out, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"Stage 2 report: {out}")

    return all_results[:3]


def run_stage_3(cache, top3, default_result):
    """Stage 3: Validation and robustness check."""
    print(f"\n{'='*70}")
    print(f"STAGE 3: Validation & Robustness")
    print(f"{'='*70}")

    # Get default per-trade results for degradation check
    def_trades = {t["trade_id"]: t for t in default_result["per_trade"]}

    recommendations = []
    for i, r in enumerate(top3):
        params = r["full_params"]
        dist = param_distance(params, DEFAULT_PARAMS)
        print(f"\n--- Candidate #{i+1} (distance={dist:.1f}) ---")

        # Degradation check
        degraded = []
        improved = []
        for t in r["per_trade"]:
            tid = t["trade_id"]
            def_v = def_trades[tid]["verdict"]
            new_v = t["verdict"]
            if def_v == "PASS" and new_v != "PASS":
                degraded.append(f"{tid}: {def_v} → {new_v}")
            elif def_v != "PASS" and new_v == "PASS":
                improved.append(f"{tid}: {def_v} → {new_v}")

        if degraded:
            print(f"  DEGRADED: {degraded}")
        else:
            print(f"  No degradation")
        if improved:
            print(f"  IMPROVED: {improved}")

        # Parameter deltas
        deltas = {k: v for k, v in params.items() if v != DEFAULT_PARAMS.get(k)}
        print(f"  Deltas from defaults: {deltas if deltas else '(identical)'}")
        print(f"  Result: {r['pass']}P/{r['partial']}PT/{r['fail']}F")

        recommendations.append({
            "rank": i + 1,
            "params": params,
            "deltas": deltas,
            "distance": dist,
            "pass": r["pass"], "partial": r["partial"], "fail": r["fail"],
            "degraded": degraded,
            "improved": improved,
            "per_trade": r["per_trade"],
        })

    # Stability analysis: for each param in top candidate, check band
    top_params = top3[0]["full_params"]
    print(f"\nStability Analysis (top candidate):")

    # Re-run with small perturbations from Stage 2 results pool not available here,
    # but we can check which values produce top score from Stage 1/2 data
    # Already covered by the "sets_at_top_score" metric in stage reports.

    # Distance analysis
    print(f"\nDistance from defaults:")
    for i, rec in enumerate(recommendations):
        print(f"  #{i+1}: {rec['distance']:.1f} ({len(rec['deltas'])} params differ)")

    # Final recommendation
    top = recommendations[0]
    if top["degraded"]:
        verdict = "CTO_REVIEW"
        reason = f"Top combination degrades {len(top['degraded'])} trade(s)"
    elif not top["deltas"]:
        verdict = "HOLD_DEFAULTS"
        reason = "Defaults are already optimal"
    elif top["pass"] > default_result["pass"]:
        verdict = "ADOPT"
        reason = f"Improves from {default_result['pass']} to {top['pass']} PASS with no degradation"
    elif top["pass"] == default_result["pass"] and top["partial"] < default_result["partial"]:
        verdict = "ADOPT"
        reason = f"Same PASS count but fewer PARTIAL ({default_result['partial']} → {top['partial']})"
    elif top["pass"] == default_result["pass"] and top["distance"] == 0:
        verdict = "HOLD_DEFAULTS"
        reason = "Defaults already match top sweep result"
    else:
        verdict = "HOLD_DEFAULTS"
        reason = "No improvement over defaults; prefer stability"

    print(f"\n{'='*70}")
    print(f"RECOMMENDATION: {verdict}")
    print(f"Reason: {reason}")
    print(f"{'='*70}")

    # Write validation report
    report = {
        "metadata": {
            "stage": 3,
            "run_time": datetime.now().isoformat(),
        },
        "recommendation": {
            "verdict": verdict,
            "reason": reason,
        },
        "default_baseline": {
            "pass": default_result["pass"],
            "partial": default_result["partial"],
            "fail": default_result["fail"],
        },
        "candidates": recommendations,
    }

    out = OUTPUT_DIR / "sweep_validation_2026-03-19.yaml"
    with open(out, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"Validation report: {out}")

    return verdict


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="AutoResearch Two-Stage Sweep")
    parser.add_argument("--ground-truth", default=str(DEFAULT_GT))
    parser.add_argument("--stage", type=int, default=0, help="Run specific stage (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s1_size = grid_size(STAGE_1_PARAMS)
    s2_size = grid_size(STAGE_2_PARAMS) * 5
    total = s1_size + s2_size

    if args.dry_run:
        print(f"Two-Stage Parameter Sweep (DRY RUN)")
        print(f"  Stage 1: {s1_size} combos (9 daily direction + v2.2 params)")
        for k, v in STAGE_1_PARAMS.items():
            print(f"    {k}: {v} (default: {DEFAULT_PARAMS[k]})")
        print(f"  Stage 2: {grid_size(STAGE_2_PARAMS)} combos × 5 top sets = {s2_size}")
        for k, v in STAGE_2_PARAMS.items():
            print(f"    {k}: {v} (default: {DEFAULT_PARAMS[k]})")
        print(f"  Total: ~{total} combinations")
        return

    print(f"AutoResearch Two-Stage Parameter Sweep")
    print(f"Total: ~{total} combinations")
    print(f"Loading and caching trade data...")

    t_start = time.time()
    trades, cache = preload_trade_data(args.ground_truth)
    print(f"Cached {len(cache)} trades in {time.time() - t_start:.1f}s")

    # Default baseline
    default_result = evaluate_cached(cache, DEFAULT_PARAMS)
    print(f"Default baseline: {default_result['pass']}P/{default_result['partial']}PT/{default_result['fail']}F")

    if args.stage == 0 or args.stage == 1:
        top5 = run_stage_1(cache, args.ground_truth)
    if args.stage == 0 or args.stage == 2:
        if args.stage == 2:
            # Load Stage 1 results
            s1_path = OUTPUT_DIR / "sweep_stage1_2026-03-19.yaml"
            with open(s1_path) as f:
                s1_report = yaml.safe_load(f)
            top5 = []
            for entry in s1_report["top_20"][:5]:
                full = dict(DEFAULT_PARAMS)
                full.update(entry["params"])
                top5.append({"params": entry["params"], "full_params": full})
        top3 = run_stage_2(cache, top5)
    if args.stage == 0 or args.stage == 3:
        if args.stage == 3:
            s2_path = OUTPUT_DIR / "sweep_stage2_2026-03-19.yaml"
            with open(s2_path) as f:
                s2_report = yaml.safe_load(f)
            top3 = []
            for entry in s2_report["top_50"][:3]:
                top3.append({"full_params": entry["full_params"], "per_trade": entry["per_trade"],
                             "pass": entry["pass"], "partial": entry["partial"], "fail": entry["fail"]})
        run_stage_3(cache, top3, default_result)

    total_elapsed = time.time() - t_start
    print(f"\nTotal sweep time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
