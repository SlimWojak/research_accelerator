"""Fitness scoring module for parameter search.

Combines precision and recall into a single fitness score.
Fitness = precision + recall (range [0.0, 2.0]).

Walk-forward stability check on top N candidates:
  candidates with unstable scores are demoted.

Improvement tracking:
  candidates improving on baseline marked 'kept',
  others 'discarded'.

Provenance recording:
  every iteration stored with config tested, score, delta from baseline,
  kept/discarded, iteration number.

Machine-readable JSON output and human-readable summary.

Usage:
    from ra.evaluation.fitness import compute_fitness, evaluate_candidate

    score = compute_fitness(precision=0.8, recall=0.9)  # 1.7
"""

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def compute_fitness(
    precision: Optional[float],
    recall: Optional[float],
) -> float:
    """Compute fitness score from precision and recall.

    Fitness = precision + recall.
    Returns 0.0 when either is None (e.g., zero detections or zero labels).

    Args:
        precision: Precision value or None.
        recall: Recall value or None.

    Returns:
        Fitness score in [0.0, 2.0].
    """
    p = precision if precision is not None else 0.0
    r = recall if recall is not None else 0.0
    return p + r


def evaluate_candidate(
    scoring_result: dict[str, Any],
    baseline_score: float,
) -> dict[str, Any]:
    """Evaluate a candidate's fitness and improvement over baseline.

    Args:
        scoring_result: Schema 4F scoring output from score_labels().
        baseline_score: Baseline fitness score to compare against.

    Returns:
        Dict with:
        - score: float fitness score
        - precision: float or None
        - recall: float or None
        - delta_from_baseline: float (score - baseline_score)
        - kept: bool (True if score > baseline_score)
    """
    agg = scoring_result.get("aggregate", {})
    precision = agg.get("precision")
    recall = agg.get("recall")

    score = compute_fitness(precision, recall)
    delta = score - baseline_score

    return {
        "score": score,
        "precision": precision,
        "recall": recall,
        "delta_from_baseline": round(delta, 6),
        "kept": score > baseline_score,
    }


def rank_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank candidates by fitness score descending.

    Assigns 1-indexed rank. Sorted by score descending.

    Args:
        candidates: List of candidate dicts (with 'score' field).

    Returns:
        Sorted list with 'rank' field added.
    """
    # Sort by score descending
    sorted_candidates = sorted(
        candidates, key=lambda c: c.get("score", 0.0), reverse=True,
    )

    # Assign ranks
    for i, c in enumerate(sorted_candidates):
        c["rank"] = i + 1

    return sorted_candidates


# ── Walk-forward stability check ─────────────────────────────────────────────


def walk_forward_stability_check(
    candidates: list[dict[str, Any]],
    wf_runner_fn: Callable[[dict[str, Any]], dict[str, Any]],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Run walk-forward stability check on top N candidates.

    Top N candidates (by current rank) undergo walk-forward validation
    using the provided runner function. Candidates with UNSTABLE verdicts
    are demoted below all non-UNSTABLE candidates.

    Args:
        candidates: Ranked list of candidate dicts (must have 'rank',
                    'score', 'config' fields). Expected to be pre-sorted
                    by rank ascending.
        wf_runner_fn: Callable that accepts a candidate config dict and
                      returns a walk-forward result dict with
                      {"summary": {"verdict": "STABLE"|"CONDITIONALLY_STABLE"|"UNSTABLE"}}.
        top_n: Number of top candidates to check. Default 3.

    Returns:
        Updated candidate list with walk_forward_verdict,
        walk_forward_demoted, walk_forward_result fields added to
        checked candidates. Re-ranked with UNSTABLE candidates demoted.
    """
    if not candidates:
        return []

    # Sort by current rank to identify top N
    sorted_by_rank = sorted(candidates, key=lambda c: c.get("rank", 999))

    # Identify top N to check
    to_check = sorted_by_rank[:top_n]
    unchecked = sorted_by_rank[top_n:]

    # Run walk-forward on each top candidate
    for candidate in to_check:
        config = candidate.get("config", {})
        try:
            wf_result = wf_runner_fn(config)
        except Exception as e:
            logger.warning(
                "Walk-forward failed for iteration %d: %s",
                candidate.get("iteration", 0), e,
            )
            wf_result = {"summary": {"verdict": "UNSTABLE"}}

        verdict = wf_result.get("summary", {}).get("verdict", "UNSTABLE")
        candidate["walk_forward_result"] = wf_result
        candidate["walk_forward_verdict"] = verdict
        candidate["walk_forward_demoted"] = verdict == "UNSTABLE"

    # Re-rank: stable/conditionally_stable first (by score desc),
    # then unstable (by score desc), then unchecked (by score desc)
    stable = [c for c in to_check if not c.get("walk_forward_demoted", False)]
    unstable = [c for c in to_check if c.get("walk_forward_demoted", False)]

    # Sort each group by score descending
    stable.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    unstable.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    unchecked.sort(key=lambda c: c.get("score", 0.0), reverse=True)

    # Combine: stable first, then unchecked, then unstable (demoted to end)
    reranked = stable + unchecked + unstable

    # Assign new ranks
    for i, c in enumerate(reranked):
        c["rank"] = i + 1

    return reranked


# ── Provenance recording ─────────────────────────────────────────────────────


def build_provenance(
    candidates: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build a complete provenance record from search results.

    Records every iteration with config tested, score, delta from baseline,
    kept/discarded flag, and iteration number. Also includes ranked
    candidates and summary statistics.

    Args:
        candidates: List of candidate dicts (with iteration, config, score,
                    delta_from_baseline, kept, rank fields).
        metadata: Run metadata dict with baseline_score,
                  iterations_requested, iterations_completed, etc.

    Returns:
        Provenance dict with:
        - schema_version: "1.0"
        - baseline_score: float
        - iterations_requested: int
        - iterations_completed: int
        - iterations: list of per-iteration records (sorted by iteration number)
        - ranked_candidates: list sorted by rank
        - summary: summary statistics dict
    """
    baseline_score = metadata.get("baseline_score", 0.0)
    iterations_requested = metadata.get("iterations_requested", 0)
    iterations_completed = metadata.get("iterations_completed", 0)

    # Build per-iteration records, sorted by iteration number
    iterations = []
    for c in sorted(candidates, key=lambda x: x.get("iteration", 0)):
        iteration_record: dict[str, Any] = {
            "iteration": c.get("iteration"),
            "config": c.get("config"),
            "score": c.get("score"),
            "delta_from_baseline": c.get("delta_from_baseline"),
            "kept": c.get("kept"),
        }
        # Include walk-forward fields if present
        if "walk_forward_verdict" in c:
            iteration_record["walk_forward_verdict"] = c["walk_forward_verdict"]
            iteration_record["walk_forward_demoted"] = c.get("walk_forward_demoted", False)
        iterations.append(iteration_record)

    # Build ranked candidates (sorted by rank)
    ranked = []
    for c in sorted(candidates, key=lambda x: x.get("rank", 999)):
        ranked_entry: dict[str, Any] = {
            "rank": c.get("rank"),
            "iteration": c.get("iteration"),
            "score": c.get("score"),
            "delta_from_baseline": c.get("delta_from_baseline"),
            "kept": c.get("kept"),
            "config": c.get("config"),
        }
        if "walk_forward_verdict" in c:
            ranked_entry["walk_forward_verdict"] = c["walk_forward_verdict"]
            ranked_entry["walk_forward_demoted"] = c.get("walk_forward_demoted", False)
        ranked.append(ranked_entry)

    # Build summary
    summary = _build_summary(candidates, baseline_score,
                              iterations_requested, iterations_completed)

    return {
        "schema_version": "1.0",
        "baseline_score": baseline_score,
        "iterations_requested": iterations_requested,
        "iterations_completed": iterations_completed,
        "iterations": iterations,
        "ranked_candidates": ranked,
        "summary": summary,
    }


def _build_summary(
    candidates: list[dict[str, Any]],
    baseline_score: float,
    iterations_requested: int,
    iterations_completed: int,
) -> dict[str, Any]:
    """Build summary statistics from candidates.

    Args:
        candidates: List of candidate dicts.
        baseline_score: Baseline fitness score.
        iterations_requested: Total iterations requested.
        iterations_completed: Total iterations completed.

    Returns:
        Summary dict with total_iterations, best_score, best_iteration,
        improvement, kept_count, discarded_count, top_3.
    """
    if not candidates:
        return {
            "total_iterations": iterations_completed,
            "best_score": baseline_score,
            "best_iteration": 0,
            "improvement": 0.0,
            "improvement_pct": 0.0,
            "kept_count": 0,
            "discarded_count": 0,
            "top_3": [],
        }

    best = max(candidates, key=lambda c: c.get("score", 0.0))
    best_score = best.get("score", 0.0)
    improvement = best_score - baseline_score
    improvement_pct = (
        (improvement / baseline_score * 100) if baseline_score > 0 else 0.0
    )

    kept_count = sum(1 for c in candidates if c.get("kept", False))
    discarded_count = len(candidates) - kept_count

    # Top 3 by rank
    by_rank = sorted(candidates, key=lambda c: c.get("rank", 999))
    top_3 = []
    for c in by_rank[:3]:
        entry: dict[str, Any] = {
            "rank": c.get("rank"),
            "iteration": c.get("iteration"),
            "score": c.get("score"),
            "delta_from_baseline": c.get("delta_from_baseline"),
            "kept": c.get("kept"),
        }
        if "walk_forward_verdict" in c:
            entry["walk_forward_verdict"] = c["walk_forward_verdict"]
        top_3.append(entry)

    return {
        "total_iterations": iterations_completed,
        "best_score": best_score,
        "best_iteration": best.get("iteration", 0),
        "improvement": round(improvement, 6),
        "improvement_pct": round(improvement_pct, 2),
        "kept_count": kept_count,
        "discarded_count": discarded_count,
        "top_3": top_3,
    }


# ── JSON output ──────────────────────────────────────────────────────────────


def format_provenance_json(provenance: dict[str, Any]) -> str:
    """Format provenance record as machine-readable JSON.

    Args:
        provenance: Provenance dict from build_provenance().

    Returns:
        Pretty-printed JSON string.
    """
    return json.dumps(provenance, indent=2, default=_json_default, ensure_ascii=False)


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for non-standard types."""
    try:
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
    except ImportError:
        pass

    if hasattr(obj, "isoformat"):
        return obj.isoformat()

    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Human-readable summary ────────────────────────────────────────────────────


def format_summary(provenance: dict[str, Any]) -> str:
    """Format provenance as a human-readable summary string.

    Includes: total iterations, best score, improvement from baseline,
    top 3 candidates.

    Args:
        provenance: Provenance dict from build_provenance().

    Returns:
        Multi-line human-readable summary string.
    """
    summary = provenance.get("summary", {})
    baseline = provenance.get("baseline_score", 0.0)

    total = summary.get("total_iterations", 0)
    best_score = summary.get("best_score", 0.0)
    best_iteration = summary.get("best_iteration", 0)
    improvement = summary.get("improvement", 0.0)
    improvement_pct = summary.get("improvement_pct", 0.0)
    kept = summary.get("kept_count", 0)
    discarded = summary.get("discarded_count", 0)
    top_3 = summary.get("top_3", [])

    lines = [
        "=" * 60,
        "  Search Summary",
        "=" * 60,
        f"  Total iterations:  {total}",
        f"  Baseline score:    {baseline:.4f}",
        f"  Best score:        {best_score:.4f} (iteration {best_iteration})",
        f"  Improvement:       {improvement:+.4f} ({improvement_pct:+.1f}%)",
        f"  Kept / Discarded:  {kept} / {discarded}",
        "",
        "  Top 3 candidates:",
    ]

    if not top_3:
        lines.append("    (none)")
    else:
        for entry in top_3:
            rank = entry.get("rank", "?")
            score = entry.get("score", 0.0)
            iteration = entry.get("iteration", "?")
            delta = entry.get("delta_from_baseline", 0.0)
            kept_flag = "kept" if entry.get("kept") else "discarded"
            wf = entry.get("walk_forward_verdict", "")
            wf_str = f" [{wf}]" if wf else ""
            lines.append(
                f"    #{rank}: score={score:.4f} "
                f"(iter {iteration}, delta={delta:+.4f}, "
                f"{kept_flag}{wf_str})"
            )

    lines.append("=" * 60)
    return "\n".join(lines)
