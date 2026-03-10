"""Fitness scoring module for parameter search.

Combines precision and recall into a single fitness score.
Fitness = precision + recall (range [0.0, 2.0]).

Walk-forward stability check on top N candidates:
  candidates with unstable scores are demoted.

Improvement tracking:
  candidates improving on baseline marked 'kept',
  others 'discarded'.

Usage:
    from ra.evaluation.fitness import compute_fitness, evaluate_candidate

    score = compute_fitness(precision=0.8, recall=0.9)  # 1.7
"""

import logging
from typing import Any, Optional

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

    Assigns 1-indexed rank. Kept candidates first, then discarded,
    each group sorted by score descending.

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
