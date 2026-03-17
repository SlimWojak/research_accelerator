#!/usr/bin/env python3
"""
AutoResearch Parameter Sweep
Grid search over classifier thresholds to find combinations that maximise
score against ground truth.

ONLY tunes classifier engineering thresholds. NOT L1.5 visual params.

Usage:
    python3 tools/autoresearch/sweep.py
    python3 tools/autoresearch/sweep.py --ground-truth path/to/trades.yaml
    python3 tools/autoresearch/sweep.py --dry-run

Current status: plumbing built. Do NOT run sweep until ground truth has 10+ trades.
With 4 trades, exhaustive grid is trivially satisfiable and results are meaningless.
"""

import argparse
import itertools
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GT = ROOT / "research" / "ground_truth" / "annotated_trades.yaml"
OUTPUT_DIR = ROOT / "reports" / "autoresearch"

# Import evaluate from same directory
sys.path.insert(0, str(Path(__file__).parent))
from evaluate import DEFAULT_PARAMS, evaluate


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETER SEARCH SPACE
# Only classifier engineering thresholds. NOT L1.5 visual params.
# ═══════════════════════════════════════════════════════════════════════════════

SEARCH_SPACE = {
    "h1_counter_persistence_bars": [2, 3, 4, 5],
    "momentum_stall_window_daily_bars": [2, 3, 4, 5],
    "key_level_tolerance_atr_factor": [0.3, 0.4, 0.5, 0.6, 0.7],
    "transition_lockout_h1_bars": [1, 2, 3, 4],
    "retrace_to_range_daily_bars": [2, 3, 4, 5],
    "kill_zone_realignment_lookback_hours": [1, 2, 3, 4],
}


def count_combinations():
    total = 1
    for values in SEARCH_SPACE.values():
        total *= len(values)
    return total


def run_sweep(gt_path: str, dry_run: bool = False):
    total_combos = count_combinations()
    print(f"AutoResearch Parameter Sweep")
    print(f"Search space: {total_combos} combinations")
    print(f"Parameters: {list(SEARCH_SPACE.keys())}")
    print("=" * 70)

    if dry_run:
        print(f"\nDRY RUN — would evaluate {total_combos} parameter combinations.")
        print("Each combination runs against all trades in ground truth.")
        for param, values in SEARCH_SPACE.items():
            print(f"  {param}: {values} (default: {DEFAULT_PARAMS[param]})")
        return

    # Check ground truth size
    with open(gt_path) as f:
        gt = yaml.safe_load(f)
    n_trades = len(gt.get("trades", []))
    if n_trades < 10:
        print(f"\nWARNING: Only {n_trades} trades in ground truth.")
        print("Sweep results with <10 trades are likely trivially satisfiable.")
        print("Recommend growing ground truth to 10+ trades before sweeping.")
        print("Proceeding anyway for validation purposes...\n")

    # Generate all combinations
    param_names = list(SEARCH_SPACE.keys())
    param_values = [SEARCH_SPACE[k] for k in param_names]

    results = []
    best_score = -1
    best_params = None

    for i, combo in enumerate(itertools.product(*param_values)):
        params = dict(zip(param_names, combo))

        # Suppress evaluate output during sweep
        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            report = evaluate(gt_path, params)

        summary = report["summary"]
        score = summary["pass"]
        total = summary["total_trades"]
        pct = (score / total * 100) if total else 0

        results.append({
            "rank": 0,
            "params": params,
            "pass": score,
            "partial": summary["partial"],
            "fail": summary["fail"],
            "total": total,
            "score_pct": pct,
        })

        if score > best_score:
            best_score = score
            best_params = params

        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{total_combos} ({(i + 1) / total_combos * 100:.1f}%)")

    # Sort by score (descending), then by closeness to defaults (prefer minimal change)
    def sort_key(r):
        distance = sum(
            abs(r["params"][k] - DEFAULT_PARAMS[k])
            for k in param_names
            if isinstance(DEFAULT_PARAMS[k], (int, float))
        )
        return (-r["score_pct"], distance)

    results.sort(key=sort_key)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    # Report
    print(f"\n{'=' * 70}")
    print(f"SWEEP COMPLETE: {total_combos} combinations evaluated")
    print(f"Best score: {best_score}/{n_trades} ({best_score / n_trades * 100:.0f}%)")
    print(f"Best params: {best_params}")
    print(f"\nTop 10 combinations:")
    for r in results[:10]:
        delta = {
            k: r["params"][k] for k in param_names
            if r["params"][k] != DEFAULT_PARAMS[k]
        }
        delta_str = str(delta) if delta else "(defaults)"
        print(f"  #{r['rank']}: {r['pass']}/{r['total']} ({r['score_pct']:.0f}%) — {delta_str}")

    # Threshold sensitivity analysis
    print(f"\nThreshold Sensitivity:")
    for param in param_names:
        passing = {}
        for r in results:
            val = r["params"][param]
            if val not in passing:
                passing[val] = {"pass": 0, "total": 0}
            passing[val]["pass"] += r["pass"]
            passing[val]["total"] += r["total"]
        print(f"  {param}:")
        for val in SEARCH_SPACE[param]:
            if val in passing:
                avg = passing[val]["pass"] / (passing[val]["total"] / n_trades) if passing[val]["total"] else 0
                print(f"    {val}: avg {avg:.1f}/{n_trades} PASS")

    # Write results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"sweep_{ts}.yaml"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sweep_report = {
        "metadata": {
            "run_time": datetime.now().isoformat(),
            "ground_truth_file": str(gt_path),
            "total_combinations": total_combos,
            "search_space": {k: list(v) for k, v in SEARCH_SPACE.items()},
            "defaults": DEFAULT_PARAMS,
        },
        "summary": {
            "best_score": f"{best_score}/{n_trades}",
            "best_params": best_params,
            "total_perfect": sum(1 for r in results if r["score_pct"] == 100),
        },
        "top_20": results[:20],
    }

    with open(output_path, "w") as f:
        yaml.dump(sweep_report, f, default_flow_style=False, sort_keys=False, width=120)

    print(f"\nSweep report written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="AutoResearch Parameter Sweep")
    parser.add_argument("--ground-truth", default=str(DEFAULT_GT),
                        help="Path to ground truth YAML")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show search space without running")
    args = parser.parse_args()

    run_sweep(args.ground_truth, args.dry_run)


if __name__ == "__main__":
    main()
