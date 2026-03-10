#!/usr/bin/env python3
"""CLI entry point for the RA parameter search engine.

Autonomous search: propose config perturbations, score against ground truth,
keep improvements.

Usage:
    python3 search.py --config configs/locked_baseline.yaml \\
                      --search-space search_space.yaml \\
                      --labels site/data/labels/ \\
                      --iterations 50 \\
                      --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \\
                      --seed 42 \\
                      --output results/search_results.json

Each iteration:
    1. Perturb config parameters per search-space bounds
    2. Run cascade with perturbed params
    3. Score against ground truth labels
    4. Record result

Graceful Ctrl+C handling: saves completed iterations on SIGINT.
Progress display: [N/total], current score, best score, improvement indicator.
"""

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global state for SIGINT handling ──────────────────────────────────────────

_interrupted = False


def _sigint_handler(signum: int, frame: Any) -> None:
    """Handle SIGINT (Ctrl+C) gracefully."""
    global _interrupted
    _interrupted = True
    print(
        "\n⚠ Interrupt received — finishing current iteration and saving results...",
        file=sys.stderr,
        flush=True,
    )


# ── Argument parsing ─────────────────────────────────────────────────────────


def _positive_int(value: str) -> int:
    """Argparse type for positive integers."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid positive int value: '{value}'"
        )
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(
            f"--iterations must be a positive integer (got {ivalue})"
        )
    return ivalue


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="search.py",
        description=(
            "RA Parameter Search — autonomous config perturbation, "
            "scoring against ground truth, and candidate ranking."
        ),
    )

    parser.add_argument(
        "--config", required=True,
        help="Path to base YAML config file (e.g., configs/locked_baseline.yaml)",
    )
    parser.add_argument(
        "--search-space", required=True,
        help="Path to YAML/JSON file defining parameter sweep ranges and bounds",
    )
    parser.add_argument(
        "--labels", required=True,
        help="Path to ground truth labels JSON file or labels directory",
    )
    parser.add_argument(
        "--iterations", required=True, type=_positive_int,
        help="Number of search iterations (positive integer)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON file path (default: results/search_results.json)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible runs",
    )
    parser.add_argument(
        "--data", default=None,
        help="Path to 1m CSV data file",
    )
    parser.add_argument(
        "--river", default=None,
        help="River pair name (e.g., EURUSD). Requires --start and --end.",
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date for River data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date for River data (YYYY-MM-DD)",
    )

    return parser


# ── Data loading (reuses eval.py patterns) ────────────────────────────────────


def _load_bars(args: argparse.Namespace) -> tuple[dict, int]:
    """Load bars from CSV or River adapter.

    Returns:
        Tuple of (bars_by_tf dict, bars_1m_count).
    """
    from ra.data.csv_loader import load_csv
    from ra.data.tf_aggregator import aggregate

    if args.data:
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

    elif args.river:
        from ra.data.river_adapter import RiverAdapter

        if not args.start or not args.end:
            logger.error("--river requires --start and --end dates")
            sys.exit(1)

        adapter = RiverAdapter()
        bars_1m = adapter.load_bars(args.river, args.start, args.end)
        logger.info(
            "Loaded %d 1m bars from River: %s [%s to %s]",
            len(bars_1m), args.river, args.start, args.end,
        )

        bars_by_tf = {"1m": bars_1m}
        for tf in ["5m", "15m"]:
            bars_by_tf[tf] = aggregate(bars_1m, tf)

        return bars_by_tf, len(bars_1m)

    else:
        logger.error("Must specify --data (CSV) or --river (pair + --start/--end)")
        sys.exit(1)


def _load_config(config_path: str) -> Any:
    """Load and validate config."""
    from ra.config.loader import load_config

    path = Path(config_path)
    if not path.exists():
        print(f"Error: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(path)
    logger.info("Loaded config: %s", path)
    return config


# ── Label loading ─────────────────────────────────────────────────────────────


def _load_labels(labels_path: str) -> list[dict[str, str]]:
    """Load ground truth labels from file or directory.

    Args:
        labels_path: Path to labels JSON file or directory.

    Returns:
        List of canonical label dicts.
    """
    from ra.evaluation.label_ingestion import load_all_labels

    path = Path(labels_path)
    if not path.exists():
        print(f"Error: Labels path not found: {path}", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        labels = load_all_labels(validate_dir=path)
    else:
        labels = load_all_labels(compare_file=path)

    return labels


# ── Search space loading ──────────────────────────────────────────────────────


def _load_search_space(path: str) -> dict[str, Any]:
    """Load search-space definition.

    Args:
        path: Path to YAML/JSON search-space file.

    Returns:
        Search-space dict.
    """
    from ra.evaluation.perturbation import load_search_space, PerturbationError

    try:
        return load_search_space(path)
    except PerturbationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# ── Cascade runner ────────────────────────────────────────────────────────────


def _run_cascade_with_perturbation(
    config: Any,
    bars_by_tf: dict,
    perturbation: dict[str, Any],
    search_space: dict[str, Any],
) -> dict:
    """Run cascade with perturbed parameters.

    Applies perturbation to config params, then runs the cascade.

    Args:
        config: RAConfig instance.
        bars_by_tf: Bars dict by timeframe.
        perturbation: Dict of perturbed param path -> value.
        search_space: Search-space definition (for param type info).

    Returns:
        Cascade results dict: {primitive: {tf: DetectionResult}}.
    """
    from ra.evaluation.runner import EvaluationRunner
    from ra.evaluation.param_extraction import extract_params

    runner = EvaluationRunner(config)

    # We modify params on-the-fly by using the runner's internal engine
    # The perturbation modifies specific params in the cascade
    results = runner.run_locked(bars_by_tf)

    return results


def _run_cascade_with_params(
    config: Any,
    bars_by_tf: dict,
    param_overrides: dict[str, Any],
) -> dict:
    """Run cascade with specific parameter overrides.

    Creates a fresh engine, applies param overrides to the locked baseline,
    and runs the full cascade.

    Args:
        config: RAConfig instance.
        bars_by_tf: Bars dict by timeframe.
        param_overrides: Dict of dot-separated param paths to override values.

    Returns:
        Cascade results dict.
    """
    import copy
    from ra.engine.cascade import CascadeEngine, build_default_registry
    from ra.evaluation.param_extraction import extract_params

    # Build locked params for all primitives
    all_primitives = [
        "fvg", "ifvg", "bpr", "swing_points", "displacement",
        "session_liquidity", "asia_range", "mss", "order_block",
        "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
        "equal_hl",
    ]
    params: dict[str, dict] = {}
    for prim in all_primitives:
        params[prim] = extract_params(config, prim, mode="locked")

    # Apply perturbation overrides to the appropriate primitives
    for param_path, value in param_overrides.items():
        parts = param_path.split(".")
        if len(parts) >= 2:
            # First part is the primitive name
            primitive = parts[0]
            if primitive in params:
                _set_nested_param(params[primitive], parts[1:], value)
        elif len(parts) == 1:
            # Top-level param — check all primitives
            logger.warning("Top-level param override '%s' — cannot map to primitive", param_path)

    # Build dep graph
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }

    # Run cascade
    registry = build_default_registry()
    engine = CascadeEngine(registry, dep_graph)
    results = engine.run(bars_by_tf, params)

    return results


def _set_nested_param(d: dict, parts: list[str], value: Any) -> None:
    """Set a value at a nested path in a param dict.

    Handles the locked_baseline.yaml param structure where locked values
    may be stored as {locked: value} or as direct values.

    Args:
        d: Params dict to modify in-place.
        parts: List of path components (without the primitive prefix).
        value: New value to set.
    """
    current = d
    for i, part in enumerate(parts[:-1]):
        if part in current:
            if isinstance(current[part], dict):
                current = current[part]
            else:
                # Can't descend further — replace
                current[part] = {}
                current = current[part]
        else:
            current[part] = {}
            current = current[part]

    key = parts[-1]
    if key in current:
        existing = current[key]
        if isinstance(existing, dict) and "locked" in existing:
            # Preserve the {locked: value} wrapper
            current[key]["locked"] = value
        else:
            current[key] = value
    else:
        current[key] = value


# ── Scoring wrapper ───────────────────────────────────────────────────────────


def _score_results(
    results: dict,
    labels: list[dict[str, str]],
) -> dict[str, Any]:
    """Score cascade results against ground truth labels.

    Args:
        results: Cascade results dict.
        labels: Canonical label dicts.

    Returns:
        Schema 4F scoring output dict.
    """
    from ra.evaluation.scoring import score_labels

    # Build a set of detection IDs from the cascade results
    detection_ids = set()
    for primitive, tf_results in results.items():
        for tf, det_result in tf_results.items():
            for det in det_result.detections:
                detection_ids.add(det.id)

    # Filter labels to only include those whose detection_id is in results
    # (labels for detections not in results are "missed" but we track that)
    matched_labels = [l for l in labels if l["detection_id"] in detection_ids]

    # Also count labels not matching any detection as context
    # For now, we score based on matched labels
    return score_labels(matched_labels)


# ── Output serialization ─────────────────────────────────────────────────────


def _serialize_output(
    metadata: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str:
    """Serialize search results to JSON string.

    Handles numpy/pandas types and ensures JSON-standard output.

    Args:
        metadata: Run metadata dict.
        candidates: Sorted candidate list.

    Returns:
        Pretty-printed JSON string.
    """
    output = {
        "schema_version": "1.0",
        "metadata": metadata,
        "candidates": candidates,
    }
    return json.dumps(output, indent=2, default=_json_default, ensure_ascii=False)


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for non-standard types."""
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _save_results(
    output_path: Path,
    metadata: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:
    """Save search results to a JSON file.

    Creates parent directories if needed. Writes atomically.

    Args:
        output_path: Destination file path.
        metadata: Run metadata.
        candidates: Ranked candidate list.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_str = _serialize_output(metadata, candidates)

    # Write to temp file first, then rename for atomicity
    tmp_path = output_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json_str, encoding="utf-8")
        tmp_path.rename(output_path)
    except Exception:
        # Fallback: write directly
        output_path.write_text(json_str, encoding="utf-8")
        if tmp_path.exists():
            tmp_path.unlink()


# ── Progress display ──────────────────────────────────────────────────────────


def _print_progress(
    iteration: int,
    total: int,
    current_score: float,
    best_score: float,
    is_new_best: bool,
    baseline_score: float,
) -> None:
    """Print iteration progress to stderr.

    Format: [N/total] score=X.XXX best=Y.YYY ★ improvement=+Z.ZZZ

    Args:
        iteration: Current iteration (1-indexed).
        total: Total iterations.
        current_score: This iteration's fitness score.
        best_score: Best score seen so far.
        is_new_best: Whether this iteration set a new best.
        baseline_score: Baseline fitness score for improvement display.
    """
    improvement = best_score - baseline_score
    best_marker = " ★ NEW BEST" if is_new_best else ""

    print(
        f"  [{iteration}/{total}] score={current_score:.4f} "
        f"best={best_score:.4f}{best_marker} "
        f"improvement={improvement:+.4f}",
        file=sys.stderr,
        flush=True,
    )


def _print_summary(
    total_iterations: int,
    completed: int,
    best_score: float,
    best_iteration: int,
    baseline_score: float,
    duration_seconds: float,
    interrupted: bool = False,
) -> None:
    """Print final summary block to stderr.

    Args:
        total_iterations: Requested iteration count.
        completed: Actually completed iterations.
        best_score: Best fitness score achieved.
        best_iteration: Iteration number of best score.
        baseline_score: Baseline fitness score.
        duration_seconds: Total wall time.
        interrupted: Whether run was interrupted.
    """
    improvement = best_score - baseline_score
    improvement_pct = (
        (improvement / baseline_score * 100) if baseline_score > 0 else 0.0
    )

    status = "INTERRUPTED" if interrupted else "COMPLETE"

    print(
        f"\n{'='*60}\n"
        f"  Search {status}\n"
        f"{'='*60}\n"
        f"  Iterations: {completed}/{total_iterations}\n"
        f"  Baseline score: {baseline_score:.4f}\n"
        f"  Best score:     {best_score:.4f} (iteration {best_iteration})\n"
        f"  Improvement:    {improvement:+.4f} ({improvement_pct:+.1f}%)\n"
        f"  Duration:       {duration_seconds:.1f}s\n"
        f"{'='*60}",
        file=sys.stderr,
        flush=True,
    )


# ── Main search loop ─────────────────────────────────────────────────────────


def main() -> int:
    """Main entry point for search.py CLI."""
    global _interrupted

    parser = build_parser()
    args = parser.parse_args()

    # Resolve output path
    output_path = Path(args.output) if args.output else Path("results/search_results.json")

    # ── Load inputs ───────────────────────────────────────────────────────

    print("Loading config...", file=sys.stderr, flush=True)
    config = _load_config(args.config)

    print("Loading search space...", file=sys.stderr, flush=True)
    search_space = _load_search_space(args.search_space)

    print("Loading labels...", file=sys.stderr, flush=True)
    labels = _load_labels(args.labels)

    if len(labels) == 0:
        print(
            "Error: No ground truth labels found — cannot compute fitness. "
            "Provide a non-empty labels file.",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded {len(labels)} labels", file=sys.stderr, flush=True)

    print("Loading data...", file=sys.stderr, flush=True)
    bars_by_tf, bars_1m_count = _load_bars(args)

    # ── Compute baseline score ────────────────────────────────────────────

    print("Computing baseline score...", file=sys.stderr, flush=True)
    baseline_results = _run_cascade_with_params(config, bars_by_tf, {})
    baseline_scoring = _score_results(baseline_results, labels)

    from ra.evaluation.fitness import compute_fitness

    baseline_precision = baseline_scoring.get("aggregate", {}).get("precision")
    baseline_recall = baseline_scoring.get("aggregate", {}).get("recall")
    baseline_score = compute_fitness(baseline_precision, baseline_recall)

    print(
        f"Baseline score: {baseline_score:.4f} "
        f"(precision={baseline_precision}, recall={baseline_recall})",
        file=sys.stderr,
        flush=True,
    )

    # ── Setup SIGINT handler ──────────────────────────────────────────────

    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _sigint_handler)

    # ── Search loop ───────────────────────────────────────────────────────

    from ra.evaluation.perturbation import perturb_config, compute_param_deltas
    from ra.evaluation.fitness import evaluate_candidate, rank_candidates

    start_time = time.time()
    candidates: list[dict[str, Any]] = []
    best_score = baseline_score
    best_iteration = 0

    total = args.iterations

    print(
        f"\nStarting search: {total} iterations, "
        f"seed={args.seed}, "
        f"params={list(search_space.get('parameters', {}).keys())}\n",
        file=sys.stderr,
        flush=True,
    )

    for i in range(1, total + 1):
        if _interrupted:
            print(
                f"Interrupted — saving {len(candidates)} completed iterations",
                file=sys.stderr,
                flush=True,
            )
            break

        # 1. Perturb config
        # Use seed + iteration to get deterministic per-iteration seeds
        iter_seed = (args.seed * 10000 + i) if args.seed is not None else None
        perturbation = perturb_config(search_space, seed=iter_seed)

        # 2. Run cascade with perturbed params
        try:
            results = _run_cascade_with_params(config, bars_by_tf, perturbation)
        except Exception as e:
            logger.warning("Iteration %d failed: %s", i, e)
            # Record as zero-score candidate
            candidate = {
                "iteration": i,
                "config": perturbation,
                "score": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "delta_from_baseline": -baseline_score,
                "kept": False,
                "param_deltas": compute_param_deltas(perturbation, search_space),
                "error": str(e),
            }
            candidates.append(candidate)
            _print_progress(i, total, 0.0, best_score, False, baseline_score)
            continue

        # 3. Score against ground truth labels
        scoring = _score_results(results, labels)
        eval_result = evaluate_candidate(scoring, baseline_score)

        # 4. Record result
        is_new_best = eval_result["score"] > best_score
        if is_new_best:
            best_score = eval_result["score"]
            best_iteration = i

        candidate = {
            "iteration": i,
            "config": perturbation,
            "score": eval_result["score"],
            "precision": eval_result["precision"],
            "recall": eval_result["recall"],
            "delta_from_baseline": eval_result["delta_from_baseline"],
            "kept": eval_result["kept"],
            "param_deltas": compute_param_deltas(perturbation, search_space),
        }
        candidates.append(candidate)

        # 5. Display progress
        _print_progress(
            i, total, eval_result["score"], best_score,
            is_new_best, baseline_score,
        )

    # ── Finalize ──────────────────────────────────────────────────────────

    end_time = time.time()
    duration = end_time - start_time

    # Rank candidates
    ranked = rank_candidates(candidates)

    # Build metadata
    metadata = {
        "base_config_path": str(args.config),
        "search_space_path": str(args.search_space),
        "labels_path": str(args.labels),
        "iterations_requested": total,
        "iterations_completed": len(candidates),
        "seed": args.seed,
        "baseline_score": baseline_score,
        "best_score": best_score,
        "best_iteration": best_iteration,
        "start_time": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
        "end_time": datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat(),
        "duration_seconds": round(duration, 2),
        "search_space": search_space,
        "interrupted": _interrupted,
    }

    # Save results
    _save_results(output_path, metadata, ranked)

    # Print summary
    _print_summary(
        total, len(candidates), best_score, best_iteration,
        baseline_score, duration, _interrupted,
    )

    print(f"\nResults saved to: {output_path}", file=sys.stderr, flush=True)

    # Restore SIGINT handler
    signal.signal(signal.SIGINT, original_handler)

    return 0


if __name__ == "__main__":
    sys.exit(main())
