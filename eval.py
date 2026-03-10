#!/usr/bin/env python3
"""CLI entry point for the RA Phase 2 evaluation engine.

Subcommands:
    sweep          Run parameter sweep (single or 2D grid)
    compare        Compare two configs (locked baseline vs candidate)
    walk-forward   Run walk-forward validation

Usage:
    python3 eval.py sweep --config configs/locked_baseline.yaml \\
                          --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \\
                          --primitive displacement --x-param ltf.close_gate \\
                          --metric detection_count --output results/

    python3 eval.py compare --config configs/locked_baseline.yaml \\
                            --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \\
                            --output results/

    python3 eval.py walk-forward --config configs/locked_baseline.yaml \\
                                 --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \\
                                 --train-months 1 --test-months 1 --step-months 1 \\
                                 --output results/
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_bars(args) -> tuple[dict, int]:
    """Load bars from CSV or River adapter.

    Returns:
        Tuple of (bars_by_tf dict, bars_1m_count).
    """
    from ra.data.csv_loader import load_csv
    from ra.data.tf_aggregator import aggregate

    if hasattr(args, "data") and args.data:
        data_path = Path(args.data)
        if not data_path.exists():
            logger.error("Data file not found: %s", data_path)
            sys.exit(1)

        bars_1m = load_csv(data_path)
        logger.info("Loaded %d 1m bars from CSV: %s", len(bars_1m), data_path)

        bars_by_tf = {"1m": bars_1m}
        for tf in ["5m", "15m"]:
            bars_by_tf[tf] = aggregate(bars_1m, tf)
            logger.info("Aggregated to %s: %d bars", tf, len(bars_by_tf[tf]))

        return bars_by_tf, len(bars_1m)

    elif hasattr(args, "river") and args.river:
        from ra.data.river_adapter import RiverAdapter

        pair = args.river
        start_date = args.start if hasattr(args, "start") and args.start else None
        end_date = args.end if hasattr(args, "end") and args.end else None

        if not start_date or not end_date:
            logger.error("--river requires --start and --end dates")
            sys.exit(1)

        adapter = RiverAdapter()
        bars_1m = adapter.load_bars(pair, start_date, end_date)
        logger.info("Loaded %d 1m bars from River: %s [%s to %s]",
                     len(bars_1m), pair, start_date, end_date)

        bars_by_tf = {"1m": bars_1m}
        for tf in ["5m", "15m"]:
            bars_by_tf[tf] = aggregate(bars_1m, tf)
            logger.info("Aggregated to %s: %d bars", tf, len(bars_by_tf[tf]))

        return bars_by_tf, len(bars_1m)

    else:
        logger.error("Must specify --data (CSV) or --river (pair + --start/--end)")
        sys.exit(1)


def _load_config(config_path: str):
    """Load and validate config."""
    from ra.config.loader import load_config

    path = Path(config_path)
    if not path.exists():
        logger.error("Config file not found: %s", path)
        sys.exit(1)

    config = load_config(path)
    logger.info("Loaded config: %s", path)
    return config


def _get_dep_graph(config) -> dict[str, list[str]]:
    """Extract dependency graph from config."""
    return {
        name: node.upstream
        for name, node in config.dependency_graph.items()
    }


def cmd_sweep(args) -> int:
    """Execute parameter sweep subcommand."""
    import copy

    from ra.config.loader import load_config
    from ra.evaluation.runner import EvaluationRunner
    from ra.evaluation.param_extraction import extract_params, extract_sweep_combos
    from ra.output.json_export import (
        serialize_grid_sweep,
        serialize_evaluation_run,
        write_json,
    )

    config = _load_config(args.config)
    bars_by_tf, bars_1m_count = _load_bars(args)
    dep_graph = _get_dep_graph(config)

    primitive = args.primitive
    x_param = args.x_param
    y_param = getattr(args, "y_param", None)
    metric = args.metric or "detection_count"
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = EvaluationRunner(config)

    # Get sweep values for x-axis
    x_sweep_params = extract_params(config, primitive, mode="sweep")
    x_values = _resolve_sweep_values(x_sweep_params, x_param)

    if not x_values:
        logger.error("No sweep_range found for %s.%s", primitive, x_param)
        return 1

    if y_param:
        y_values = _resolve_sweep_values(x_sweep_params, y_param)
        if not y_values:
            logger.error("No sweep_range found for %s.%s", primitive, y_param)
            return 1
    else:
        y_values = None

    # Run the sweep
    logger.info("Starting sweep: %s.%s%s (%d combinations)",
                primitive, x_param,
                f" × {y_param}" if y_param else "",
                len(x_values) * (len(y_values) if y_values else 1))

    if y_param:
        # 2D grid sweep
        sweep_results = runner.run_grid(
            bars_by_tf, primitive, x_param, y_param,
        )
        grid, combo_metrics = _build_2d_grid(
            sweep_results, primitive, metric, x_values, y_values,
        )
        axes = {
            "x": {"param": x_param, "values": x_values},
            "y": {"param": y_param, "values": y_values},
        }
    else:
        # 1D sweep
        sweep_results = runner.run_sweep(
            bars_by_tf, primitive, params=[x_param],
        )
        grid, combo_metrics = _build_1d_grid(
            sweep_results, primitive, metric, x_values,
        )
        axes = {
            "x": {"param": x_param, "values": x_values},
            "y": {"param": "_single", "values": [0]},
        }

    # Print progress
    for i, val in enumerate(combo_metrics):
        _print_progress(i + 1, len(combo_metrics), f"{primitive} sweep")

    # Get current lock position
    locked_params = extract_params(config, primitive, mode="locked")
    current_lock = _get_current_lock(locked_params, x_param, y_param, grid, x_values, y_values)

    # Build grid sweep output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sweep_id = f"sweep_{primitive}_{x_param.replace('.', '_')}_{timestamp}"

    grid_data = {
        "sweep_id": sweep_id,
        "primitive": primitive,
        "variant": "a8ra_v1",
        "dataset": str(args.data) if args.data else f"river_{args.river}",
        "metric": metric,
        "axes": axes,
        "grid": grid,
        "current_lock": current_lock,
        "plateau": None,
        "cliff_edges": [],
    }

    output = serialize_grid_sweep(grid_data)
    out_path = output_dir / f"sweep_{primitive}_{x_param.replace('.', '_')}.json"
    write_json(output, out_path)

    logger.info("Sweep complete. Output: %s", out_path)
    return 0


def _resolve_sweep_values(sweep_params: dict, param_path: str) -> list:
    """Resolve sweep values for a dot-separated parameter path.

    Handles nested structures like 'ltf.atr_multiplier'.
    """
    parts = param_path.split(".")
    current = sweep_params

    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return []
        else:
            return []

    # If we got a list, it's the sweep values directly
    if isinstance(current, list):
        return current

    # If it's a dict with per_tf values, return all unique values
    if isinstance(current, dict):
        values = set()
        for v in current.values():
            if isinstance(v, list):
                values.update(v)
            elif isinstance(v, (int, float)):
                values.add(v)
        return sorted(values)

    return []


def _build_1d_grid(
    sweep_results: list,
    primitive: str,
    metric: str,
    x_values: list,
) -> tuple[list[list], list]:
    """Build a 1D grid (N×1) from sweep results."""
    metrics = []
    for step in sweep_results:
        val = _compute_metric_from_results(step["results"], primitive, metric)
        metrics.append(val)
        _print_progress(len(metrics), len(sweep_results), f"{primitive} sweep")

    # Pad or truncate to match x_values length
    while len(metrics) < len(x_values):
        metrics.append(None)
    metrics = metrics[:len(x_values)]

    return [metrics], metrics


def _build_2d_grid(
    sweep_results: list,
    primitive: str,
    metric: str,
    x_values: list,
    y_values: list,
) -> tuple[list[list], list]:
    """Build a 2D grid (x_len × y_len) from sweep results."""
    all_metrics = []
    for step in sweep_results:
        val = _compute_metric_from_results(step["results"], primitive, metric)
        all_metrics.append(val)
        _print_progress(len(all_metrics), len(sweep_results), f"{primitive} grid sweep")

    # Arrange into 2D grid: grid[i][j] = metric at x_values[i], y_values[j]
    grid = []
    idx = 0
    for _x in x_values:
        row = []
        for _y in y_values:
            if idx < len(all_metrics):
                row.append(all_metrics[idx])
            else:
                row.append(None)
            idx += 1
        grid.append(row)

    return grid, all_metrics


def _compute_metric_from_results(
    results: dict, primitive: str, metric: str
) -> float:
    """Compute a metric value from cascade results."""
    if metric == "detection_count":
        prim_results = results.get(primitive, {})
        total = 0
        for tf, det_result in prim_results.items():
            total += len(det_result.detections)
        return float(total)
    elif metric == "cascade_to_mss_rate":
        disp = results.get("displacement", {}).get("5m")
        mss = results.get("mss", {}).get("5m")
        disp_count = len(disp.detections) if disp else 0
        mss_count = len(mss.detections) if mss else 0
        return mss_count / disp_count if disp_count > 0 else 0.0
    else:
        # Default: detection_count
        prim_results = results.get(primitive, {})
        total = 0
        for tf, det_result in prim_results.items():
            total += len(det_result.detections)
        return float(total)


def _get_current_lock(
    locked_params: dict,
    x_param: str,
    y_param: str | None,
    grid: list,
    x_values: list,
    y_values: list | None,
) -> dict | None:
    """Get the current locked position in the grid.

    Grid encoding: grid[i][j] = metric at axes.x.values[i], axes.y.values[j]
    For 1D grids: grid has 1 row, grid[0][i] = metric at x_values[i]
    """
    x_val = _resolve_locked_value(locked_params, x_param)
    y_val = _resolve_locked_value(locked_params, y_param) if y_param else 0

    if x_val is None:
        return None

    # Find closest x index
    x_idx = _find_closest_index(x_values, x_val)

    metric_value = None
    if y_param and y_values:
        # 2D grid: grid[x_idx][y_idx]
        y_idx = _find_closest_index(y_values, y_val) if y_val is not None else 0
        if x_idx < len(grid):
            row = grid[x_idx]
            if y_idx < len(row):
                metric_value = row[y_idx]
    else:
        # 1D grid: grid[0][x_idx]  (single row, x maps to columns)
        if len(grid) > 0 and x_idx < len(grid[0]):
            metric_value = grid[0][x_idx]

    return {
        "x": x_val,
        "y": y_val,
        "metric_value": metric_value,
    }


def _resolve_locked_value(params: dict, param_path: str) -> float | None:
    """Resolve a locked value for a dot-separated parameter path."""
    if param_path is None:
        return None
    parts = param_path.split(".")
    current = params
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    if isinstance(current, (int, float)):
        return current
    if isinstance(current, dict) and "locked" in current:
        return current["locked"]
    return None


def _find_closest_index(values: list, target) -> int:
    """Find the index of the closest value in a sorted list."""
    if not values:
        return 0
    min_diff = float("inf")
    best_idx = 0
    for i, v in enumerate(values):
        diff = abs(v - target)
        if diff < min_diff:
            min_diff = diff
            best_idx = i
    return best_idx


def _print_progress(current: int, total: int, label: str) -> None:
    """Print progress to stderr."""
    if total <= 1:
        return
    pct = current / total * 100
    print(f"\r  [{label}] {current}/{total} ({pct:.0f}%)", end="", file=sys.stderr, flush=True)
    if current == total:
        print("", file=sys.stderr)


def cmd_compare(args) -> int:
    """Execute comparison subcommand."""
    from ra.evaluation.runner import EvaluationRunner
    from ra.evaluation.comparison import compare_pairwise, compute_stats
    from ra.evaluation.cascade_stats import cascade_funnel
    from ra.output.json_export import (
        serialize_evaluation_run,
        write_json,
    )

    config = _load_config(args.config)
    bars_by_tf, bars_1m_count = _load_bars(args)
    dep_graph = _get_dep_graph(config)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve variant_by_primitive from config and CLI flags
    variant_by_primitive = None
    if hasattr(config, "cascade") and config.cascade and config.cascade.variant_by_primitive:
        variant_by_primitive = dict(config.cascade.variant_by_primitive)

    variant_a = getattr(args, "variant_a", "a8ra_v1")
    variant_b = getattr(args, "variant_b", "a8ra_v1")

    runner = EvaluationRunner(
        config, variant_by_primitive=variant_by_primitive,
    )

    # Run locked baseline
    logger.info("Running locked baseline (variant_a=%s)...", variant_a)
    locked_results = runner.run_locked(bars_by_tf)

    # Build Schema 4A with single config
    # Infer date range from bars
    date_range = _infer_date_range(bars_by_tf)

    output = serialize_evaluation_run(
        results_by_config={"current_locked": locked_results},
        dataset_name=str(args.data) if hasattr(args, "data") and args.data else "river",
        bars_1m_count=bars_1m_count,
        date_range=date_range,
        dep_graph=dep_graph,
    )

    out_path = output_dir / "evaluation_run.json"
    write_json(output, out_path)

    logger.info("Comparison complete. Output: %s", out_path)
    return 0


def _infer_date_range(bars_by_tf: dict) -> tuple[str, str]:
    """Infer date range from bars data."""
    import pandas as pd

    for tf, bars in bars_by_tf.items():
        if bars.empty:
            continue
        if "timestamp_ny" in bars.columns:
            ts = pd.to_datetime(bars["timestamp_ny"])
        elif "timestamp" in bars.columns:
            ts = pd.to_datetime(bars["timestamp"])
        else:
            continue
        start = ts.min()
        end = ts.max()
        start_str = start.date().isoformat() if hasattr(start, 'date') else str(start)[:10]
        end_str = end.date().isoformat() if hasattr(end, 'date') else str(end)[:10]
        return (start_str, end_str)
    return ("unknown", "unknown")


def cmd_walk_forward(args) -> int:
    """Execute walk-forward validation subcommand."""
    from ra.evaluation.walk_forward import WalkForwardRunner, WindowConfig
    from ra.output.json_export import serialize_walk_forward, write_json

    config = _load_config(args.config)
    bars_by_tf, bars_1m_count = _load_bars(args)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    primitive = args.primitive or "displacement"
    metric = args.metric or "detection_count"
    train_months = args.train_months or 3
    test_months = args.test_months or 1
    step_months = args.step_months or 1

    window_config = WindowConfig(
        train_months=train_months,
        test_months=test_months,
        step_months=step_months,
    )

    runner = WalkForwardRunner(config)
    start_date = getattr(args, "start", None)
    end_date = getattr(args, "end", None)

    logger.info("Running walk-forward: %s %s (train=%d, test=%d, step=%d)",
                primitive, metric, train_months, test_months, step_months)

    result = runner.run(
        bars_by_tf=bars_by_tf,
        primitive=primitive,
        metric=metric,
        window_config=window_config,
        start_date=start_date,
        end_date=end_date,
    )

    output = serialize_walk_forward(result)
    out_path = output_dir / f"walk_forward_{primitive}.json"
    write_json(output, out_path)

    logger.info("Walk-forward complete: %d windows, verdict=%s",
                len(result["windows"]), result["summary"]["verdict"])
    logger.info("Output: %s", out_path)
    return 0


def main() -> int:
    """Main entry point for eval.py CLI."""
    parser = argparse.ArgumentParser(
        prog="eval.py",
        description="RA Phase 2 Evaluation Engine — parameter sweep, comparison, walk-forward.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # ─── sweep subcommand ─────────────────────────────────────────────

    sweep_parser = subparsers.add_parser(
        "sweep",
        help="Run parameter sweep (1D line or 2D grid)",
    )
    sweep_parser.add_argument(
        "--config", required=True,
        help="Path to YAML config file",
    )
    sweep_parser.add_argument(
        "--data", default=None,
        help="Path to 1m CSV data file",
    )
    sweep_parser.add_argument(
        "--river", default=None,
        help="River pair name (e.g., EURUSD). Requires --start and --end.",
    )
    sweep_parser.add_argument(
        "--start", default=None,
        help="Start date for River data (YYYY-MM-DD)",
    )
    sweep_parser.add_argument(
        "--end", default=None,
        help="End date for River data (YYYY-MM-DD)",
    )
    sweep_parser.add_argument(
        "--primitive", required=True,
        help="Primitive name to sweep (e.g., displacement, fvg)",
    )
    sweep_parser.add_argument(
        "--x-param", required=True,
        help="Dot-separated param path for x-axis (e.g., ltf.atr_multiplier)",
    )
    sweep_parser.add_argument(
        "--y-param", default=None,
        help="Dot-separated param path for y-axis (optional, for 2D grid)",
    )
    sweep_parser.add_argument(
        "--metric", default="detection_count",
        help="Metric to compute (detection_count, cascade_to_mss_rate)",
    )
    sweep_parser.add_argument(
        "--output", required=True,
        help="Output directory for JSON results",
    )

    # ─── compare subcommand ───────────────────────────────────────────

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare configs (locked baseline vs candidate)",
    )
    compare_parser.add_argument(
        "--config", required=True,
        help="Path to YAML config file",
    )
    compare_parser.add_argument(
        "--data", default=None,
        help="Path to 1m CSV data file",
    )
    compare_parser.add_argument(
        "--river", default=None,
        help="River pair name. Requires --start and --end.",
    )
    compare_parser.add_argument(
        "--start", default=None,
        help="Start date (YYYY-MM-DD)",
    )
    compare_parser.add_argument(
        "--end", default=None,
        help="End date (YYYY-MM-DD)",
    )
    compare_parser.add_argument(
        "--output", required=True,
        help="Output directory for JSON results",
    )
    compare_parser.add_argument(
        "--variant-a", default="a8ra_v1",
        help="Variant name for config A (default: a8ra_v1)",
    )
    compare_parser.add_argument(
        "--variant-b", default="a8ra_v1",
        help="Variant name for config B (default: a8ra_v1)",
    )

    # ─── walk-forward subcommand ──────────────────────────────────────

    wf_parser = subparsers.add_parser(
        "walk-forward",
        help="Run walk-forward validation",
    )
    wf_parser.add_argument(
        "--config", required=True,
        help="Path to YAML config file",
    )
    wf_parser.add_argument(
        "--data", default=None,
        help="Path to 1m CSV data file",
    )
    wf_parser.add_argument(
        "--river", default=None,
        help="River pair name. Requires --start and --end.",
    )
    wf_parser.add_argument(
        "--start", default=None,
        help="Start date (YYYY-MM-DD)",
    )
    wf_parser.add_argument(
        "--end", default=None,
        help="End date (YYYY-MM-DD)",
    )
    wf_parser.add_argument(
        "--primitive", default="displacement",
        help="Primitive to evaluate (default: displacement)",
    )
    wf_parser.add_argument(
        "--metric", default="detection_count",
        help="Metric to compute (default: detection_count)",
    )
    wf_parser.add_argument(
        "--train-months", type=int, default=3,
        help="Training window in months (default: 3)",
    )
    wf_parser.add_argument(
        "--test-months", type=int, default=1,
        help="Test window in months (default: 1)",
    )
    wf_parser.add_argument(
        "--step-months", type=int, default=1,
        help="Step size in months (default: 1)",
    )
    wf_parser.add_argument(
        "--output", required=True,
        help="Output directory for JSON results",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "sweep":
        return cmd_sweep(args)
    elif args.command == "compare":
        return cmd_compare(args)
    elif args.command == "walk-forward":
        return cmd_walk_forward(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
