"""Comparison statistics for detection results (Phase 2).

Provides three main functions:

1. compute_stats(detection_results) — Per-primitive per-TF statistics:
   - detection_count
   - detections_per_day (mean over forex trading days)
   - detections_per_day_std (std over per-day counts)
   - by_session_distribution ({asia, lokz, nyokz, other} with count + pct)
   - by_direction ({bullish, bearish} with count + pct)

2. compare_pairwise(results_a, results_b) — Pairwise comparison:
   - agreement_rate, only_in_a, only_in_b
   - divergence_index (per-detection diff list)
   - by_session_agreement (per-session agreement rates)

3. compare_multi(configs_dict) — Multi-config: generates all C(n,2) pairs.

Session mapping uses 4 categories matching Phase 1 convention:
  asia, lokz, nyokz, other.
"""

import itertools
import logging
from collections import Counter, defaultdict
from typing import Any

from ra.engine.base import DetectionResult

logger = logging.getLogger(__name__)

# 4-category session mapping from Phase 1 raw sessions.
# Phase 1 detectors already tag with these 4 categories (asia, lokz, nyokz, other),
# but pre_london and pre_ny get mapped to "other" if they ever appear.
_SESSION_MAP = {
    "asia": "asia",
    "pre_london": "other",
    "lokz": "lokz",
    "pre_ny": "other",
    "nyokz": "nyokz",
    "other": "other",
}

_SESSION_CATEGORIES = ("asia", "lokz", "nyokz", "other")
_DIRECTION_CATEGORIES = ("bullish", "bearish")


def _safe_pct(count: int, total: int) -> float:
    """Compute percentage, returning 0 if total is 0."""
    if total == 0:
        return 0.0
    return round(count / total * 100.0, 1)


def compute_stats(
    detection_results: dict[str, dict[str, DetectionResult]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Compute per-primitive per-TF statistics from detection results.

    Args:
        detection_results: Nested dict results[primitive][timeframe] -> DetectionResult.

    Returns:
        Nested dict stats[primitive][timeframe] with:
            detection_count: int
            detections_per_day: float (mean over forex days)
            detections_per_day_std: float (std over per-day counts)
            by_session: {asia: {count, pct}, lokz: {count, pct}, ...}
            by_direction: {bullish: {count, pct}, bearish: {count, pct}}
    """
    stats: dict[str, dict[str, dict[str, Any]]] = {}

    for prim_name, tf_dict in detection_results.items():
        prim_stats: dict[str, dict[str, Any]] = {}

        for tf, det_result in tf_dict.items():
            detections = det_result.detections
            count = len(detections)

            # --- detections_per_day: mean and std ---
            mean_per_day, std_per_day = _compute_per_day_stats(detections)

            # --- by_session distribution ---
            by_session = _compute_session_distribution(detections, count)

            # --- by_direction distribution ---
            by_direction = _compute_direction_distribution(detections, count)

            prim_stats[tf] = {
                "detection_count": count,
                "detections_per_day": mean_per_day,
                "detections_per_day_std": std_per_day,
                "by_session": by_session,
                "by_direction": by_direction,
            }

        stats[prim_name] = prim_stats

    return stats


def _compute_per_day_stats(
    detections: list,
) -> tuple[float, float]:
    """Compute mean and std of detections per forex day.

    Uses the forex_day tag on each detection to determine day grouping.

    Returns:
        Tuple of (mean_per_day, std_per_day). Both 0 if no detections.
    """
    if not detections:
        return 0.0, 0.0

    # Group by forex_day
    day_counts: Counter = Counter()
    for d in detections:
        forex_day = d.tags.get("forex_day", "unknown")
        day_counts[forex_day] += 1

    if not day_counts:
        return 0.0, 0.0

    counts = list(day_counts.values())
    n_days = len(counts)
    mean_val = sum(counts) / n_days

    if n_days <= 1:
        return round(mean_val, 2), 0.0

    # Population std (not sample)
    variance = sum((c - mean_val) ** 2 for c in counts) / n_days
    std_val = variance ** 0.5

    return round(mean_val, 2), round(std_val, 2)


def _compute_session_distribution(
    detections: list, total: int
) -> dict[str, dict[str, Any]]:
    """Compute by_session distribution with count + pct per category.

    Uses 4-category mapping: asia, lokz, nyokz, other.
    Percentages sum to 100% (or all 0 if no detections).
    """
    session_counts: Counter = Counter()

    for d in detections:
        raw_session = d.tags.get("session", "other")
        mapped = _SESSION_MAP.get(raw_session, "other")
        session_counts[mapped] += 1

    result = {}
    for sess in _SESSION_CATEGORIES:
        count = session_counts.get(sess, 0)
        result[sess] = {
            "count": count,
            "pct": _safe_pct(count, total),
        }

    # Adjust rounding to ensure percentages sum to exactly 100%
    if total > 0:
        _fix_pct_rounding(result, total)

    return result


def _compute_direction_distribution(
    detections: list, total: int
) -> dict[str, dict[str, Any]]:
    """Compute by_direction distribution with count + pct.

    Categories: bullish, bearish.
    Percentages sum to 100% (or all 0 if no detections).
    """
    dir_counts: Counter = Counter()

    for d in detections:
        direction = d.direction
        if direction in _DIRECTION_CATEGORIES:
            dir_counts[direction] += 1
        else:
            # Directions like "high", "low", "neutral" go into a catch-all
            # but we still report bullish/bearish as the main categories
            pass

    # For primitives that don't use bullish/bearish (e.g., swing_points with
    # "high"/"low"), we include all unique directions found
    all_directions = set(d.direction for d in detections)
    result: dict[str, dict[str, Any]] = {}

    for direction in _DIRECTION_CATEGORIES:
        count = dir_counts.get(direction, 0)
        result[direction] = {
            "count": count,
            "pct": _safe_pct(count, total),
        }

    # If there are non-standard directions, add them too
    for direction in sorted(all_directions):
        if direction not in _DIRECTION_CATEGORIES:
            count = sum(1 for d in detections if d.direction == direction)
            result[direction] = {
                "count": count,
                "pct": _safe_pct(count, total),
            }

    # Fix rounding for the reported categories
    if total > 0 and result:
        _fix_pct_rounding(result, total)

    return result


def _fix_pct_rounding(
    dist: dict[str, dict[str, Any]], total: int
) -> None:
    """Adjust percentages so they sum to exactly 100.0.

    Distributes the rounding remainder to the largest category.
    Only modifies categories with count > 0.
    """
    current_sum = sum(v["pct"] for v in dist.values())
    if abs(current_sum - 100.0) < 0.01 or current_sum == 0:
        return

    diff = 100.0 - current_sum
    # Find the category with the largest count to absorb the difference
    max_key = max(dist, key=lambda k: dist[k]["count"])
    dist[max_key]["pct"] = round(dist[max_key]["pct"] + diff, 1)


def compare_pairwise(
    results_a: dict[str, dict[str, DetectionResult]],
    results_b: dict[str, dict[str, DetectionResult]],
) -> dict[str, Any]:
    """Compare two sets of cascade results pairwise.

    Args:
        results_a: First cascade result dict.
        results_b: Second cascade result dict.

    Returns:
        Dict conforming to Schema 4C with:
            per_primitive: per-primitive per-TF comparison stats
            divergence_index: per-detection diff list
    """
    comparison: dict[str, Any] = {
        "per_primitive": {},
        "divergence_index": [],
    }

    # Collect all primitives from both results
    all_primitives = set(results_a.keys()) | set(results_b.keys())

    for prim in sorted(all_primitives):
        prim_comp: dict[str, dict[str, Any]] = {}

        tfs_a = results_a.get(prim, {})
        tfs_b = results_b.get(prim, {})
        all_tfs = set(tfs_a.keys()) | set(tfs_b.keys())

        for tf in sorted(all_tfs):
            det_a = tfs_a.get(tf)
            det_b = tfs_b.get(tf)

            dets_a = det_a.detections if det_a else []
            dets_b = det_b.detections if det_b else []

            ids_a = {d.id for d in dets_a}
            ids_b = {d.id for d in dets_b}

            agreed = ids_a & ids_b
            only_a = ids_a - ids_b
            only_b = ids_b - ids_a
            total_unique = len(ids_a | ids_b)

            agreement_rate = (
                len(agreed) / total_unique if total_unique > 0 else 1.0
            )

            # Per-session agreement
            by_session_agreement = _compute_session_agreement(
                dets_a, dets_b, agreed, only_a, only_b
            )

            prim_comp[tf] = {
                "count_a": len(dets_a),
                "count_b": len(dets_b),
                "agreement_rate": round(agreement_rate, 4),
                "only_in_a": len(only_a),
                "only_in_b": len(only_b),
                "by_session_agreement": by_session_agreement,
            }

            # Build divergence index entries
            _build_divergence_entries(
                prim, tf, dets_a, dets_b,
                agreed, only_a, only_b,
                comparison["divergence_index"],
            )

        comparison["per_primitive"][prim] = prim_comp

    return comparison


def _compute_session_agreement(
    dets_a: list,
    dets_b: list,
    agreed_ids: set,
    only_a_ids: set,
    only_b_ids: set,
) -> dict[str, dict[str, float]]:
    """Compute per-session agreement rates.

    For each session category, compute:
        agreement = agreed_in_session / total_unique_in_session

    Returns dict with {session: {agreement: float}} for all 4 categories.
    """
    # Build detection lookup by ID
    dets_a_map = {d.id: d for d in dets_a}
    dets_b_map = {d.id: d for d in dets_b}

    # Classify each unique detection into a session
    session_agreed: Counter = Counter()
    session_total: Counter = Counter()

    for det_id in agreed_ids:
        d = dets_a_map.get(det_id) or dets_b_map.get(det_id)
        if d:
            raw = d.tags.get("session", "other")
            sess = _SESSION_MAP.get(raw, "other")
            session_agreed[sess] += 1
            session_total[sess] += 1

    for det_id in only_a_ids:
        d = dets_a_map.get(det_id)
        if d:
            raw = d.tags.get("session", "other")
            sess = _SESSION_MAP.get(raw, "other")
            session_total[sess] += 1

    for det_id in only_b_ids:
        d = dets_b_map.get(det_id)
        if d:
            raw = d.tags.get("session", "other")
            sess = _SESSION_MAP.get(raw, "other")
            session_total[sess] += 1

    result = {}
    for sess in _SESSION_CATEGORIES:
        total = session_total.get(sess, 0)
        agreed = session_agreed.get(sess, 0)
        rate = agreed / total if total > 0 else 1.0
        result[sess] = {"agreement": round(rate, 4)}

    return result


def _build_divergence_entries(
    primitive: str,
    tf: str,
    dets_a: list,
    dets_b: list,
    agreed_ids: set,
    only_a_ids: set,
    only_b_ids: set,
    divergence_index: list,
) -> None:
    """Build divergence index entries for a primitive/TF pair.

    Each detection gets an entry showing its presence in both configs.
    """
    dets_a_map = {d.id: d for d in dets_a}
    dets_b_map = {d.id: d for d in dets_b}

    # All unique detection IDs, sorted for determinism
    all_ids = sorted(agreed_ids | only_a_ids | only_b_ids)

    for det_id in all_ids:
        d_a = dets_a_map.get(det_id)
        d_b = dets_b_map.get(det_id)
        d = d_a or d_b

        entry = {
            "time": d.time.isoformat() if d else None,
            "primitive": primitive,
            "tf": tf,
            "in_a": det_id in (agreed_ids | only_a_ids),
            "in_b": det_id in (agreed_ids | only_b_ids),
            "detection_id_a": det_id if d_a else None,
            "detection_id_b": det_id if d_b else None,
        }
        divergence_index.append(entry)


def compare_multi(
    configs: dict[str, dict[str, dict[str, DetectionResult]]],
) -> list[dict[str, Any]]:
    """Compare all C(n,2) pairwise combinations of configs.

    Args:
        configs: Dict mapping config_name -> cascade results dict.

    Returns:
        List of pairwise comparison dicts, each containing:
            config_a, config_b, per_primitive, divergence_index.
    """
    config_names = sorted(configs.keys())
    results = []

    for name_a, name_b in itertools.combinations(config_names, 2):
        comparison = compare_pairwise(configs[name_a], configs[name_b])
        comparison["config_a"] = name_a
        comparison["config_b"] = name_b
        results.append(comparison)

    return results
