"""Ground truth scoring pipeline.

Computes precision, recall, and F1 per primitive from labelled detections.

Precision = correct / (correct + noise), BORDERLINE excluded from denominator.
Recall = correct / (correct + missed), where missed defaults to 0 when only
labelled detections exist.
F1 = 2*(P*R)/(P+R). Returns null when P or R is null.

Per-session breakdown (asia, lokz, nyokz, other).
Per-variant breakdown when labels span multiple variants.

Output follows Schema 4F:
    {schema_version, scored_at, label_source, per_primitive, aggregate}
"""

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Session classification based on NY hour (4-category mapping).
# Pre-London (0-2) and Pre-NY (5-7) map to "other" to match
# Phase 1 convention used in comparison.py.
_SESSION_CATEGORIES = ("asia", "lokz", "nyokz", "other")

# Regex to extract timestamp from detection_id format:
# {primitive}_{tf}_{timestamp_ny}_{direction}
# e.g., displacement_5m_2024-01-08T09:35:00_bear
_DETECTION_ID_TS_PATTERN = re.compile(
    r"^[a-z_]+_\d+[mhHdD]_(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})_"
)

# Valid label values that affect scoring
_SCORING_LABELS = {"CORRECT", "NOISE", "MISSED"}


def _classify_session_from_hour(hour: int) -> str:
    """Classify NY hour into 4-category session name.

    Matches the session definitions in data/session_tagger.py but uses
    the 4-category mapping from comparison.py:
    - Asia: 19:00 - 00:00 (h >= 19)
    - LOKZ: 02:00 - 05:00 (2 <= h < 5)
    - NYOKZ: 07:00 - 10:00 (7 <= h < 10)
    - Other: everything else (pre_london, pre_ny, daytime)
    """
    if hour >= 19:
        return "asia"
    if 2 <= hour < 5:
        return "lokz"
    if 7 <= hour < 10:
        return "nyokz"
    return "other"


def session_from_detection_id(detection_id: str) -> str:
    """Extract session from a detection ID by parsing its embedded timestamp.

    Detection ID format: {primitive}_{tf}_{timestamp_ny}_{direction}
    The timestamp is in NY timezone. The hour determines the session.

    Args:
        detection_id: Detection ID string.

    Returns:
        Session name: one of 'asia', 'lokz', 'nyokz', 'other'.
    """
    match = _DETECTION_ID_TS_PATTERN.match(detection_id)
    if not match:
        logger.warning("Cannot parse timestamp from detection_id: %s", detection_id)
        return "other"

    ts_str = match.group(1)
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        return _classify_session_from_hour(dt.hour)
    except ValueError:
        logger.warning("Invalid timestamp in detection_id: %s", detection_id)
        return "other"


def compute_precision(correct: int, noise: int) -> Optional[float]:
    """Compute precision from label counts.

    Precision = correct / (correct + noise).
    BORDERLINE is excluded from the denominator.

    Args:
        correct: Number of CORRECT labels.
        noise: Number of NOISE labels.

    Returns:
        Precision as float in [0.0, 1.0], or None when denominator is 0.
    """
    denom = correct + noise
    if denom == 0:
        return None
    return correct / denom


def compute_recall(correct: int, missed: int) -> Optional[float]:
    """Compute recall from label counts.

    Recall = correct / (correct + missed).
    When only labelled detections exist (no MISSED entries), missed=0 → recall=1.0.

    Args:
        correct: Number of CORRECT labels.
        missed: Number of MISSED labels (ground truth positives not detected).

    Returns:
        Recall as float in [0.0, 1.0], or None when no ground truth positives exist.
    """
    denom = correct + missed
    if denom == 0:
        return None
    return correct / denom


def compute_f1(
    precision: Optional[float], recall: Optional[float]
) -> Optional[float]:
    """Compute F1 score from precision and recall.

    F1 = 2 * (P * R) / (P + R).
    Returns None when either P or R is None.
    Returns 0.0 when both P and R are 0.0 (avoids division by zero).

    Args:
        precision: Precision value or None.
        recall: Recall value or None.

    Returns:
        F1 as float in [0.0, 1.0], or None.
    """
    if precision is None or recall is None:
        return None
    if precision == 0.0 and recall == 0.0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _count_labels(
    labels: list[dict[str, str]],
) -> tuple[int, int, int, int]:
    """Count CORRECT, NOISE, BORDERLINE, and MISSED labels.

    Args:
        labels: List of canonical label dicts.

    Returns:
        Tuple of (correct, noise, borderline, missed) counts.
    """
    correct = 0
    noise = 0
    borderline = 0
    missed = 0
    for label in labels:
        lbl = label["label"]
        if lbl == "CORRECT":
            correct += 1
        elif lbl == "NOISE":
            noise += 1
        elif lbl == "BORDERLINE":
            borderline += 1
        elif lbl == "MISSED":
            missed += 1
    return correct, noise, borderline, missed


def _score_label_group(
    labels: list[dict[str, str]],
) -> dict[str, Any]:
    """Compute precision, recall, F1 for a group of labels.

    Args:
        labels: List of canonical label dicts for the group.

    Returns:
        Dict with precision, recall, f1, label_count,
        correct, noise, borderline, missed.
    """
    correct, noise, borderline, missed = _count_labels(labels)
    precision = compute_precision(correct, noise)
    recall = compute_recall(correct, missed)
    f1 = compute_f1(precision, recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "label_count": len(labels),
        "correct": correct,
        "noise": noise,
        "borderline": borderline,
        "missed": missed,
    }


def _score_session_group(
    labels: list[dict[str, str]],
) -> dict[str, Any]:
    """Compute precision, recall, F1, label_count for a session group.

    Args:
        labels: List of canonical label dicts for the session.

    Returns:
        Dict with precision, recall, f1, label_count.
    """
    correct, noise, borderline, missed = _count_labels(labels)
    precision = compute_precision(correct, noise)
    recall = compute_recall(correct, missed)
    f1 = compute_f1(precision, recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "label_count": len(labels),
    }


def _empty_session_scores() -> dict[str, Any]:
    """Return null scores for a session with no labels."""
    return {
        "precision": None,
        "recall": None,
        "f1": None,
        "label_count": 0,
    }


def score_labels(
    labels: list[dict[str, str]],
    variant_map: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Score labelled detections: precision, recall, F1 per primitive.

    Computes aggregate and per-primitive scores from canonical labels.
    Optionally breaks down by session (from detection ID timestamp)
    and by variant (from variant_map).

    Args:
        labels: List of canonical label dicts from label_ingestion.
                Each dict has: detection_id, primitive, timeframe, label, labelled_by.
        variant_map: Optional mapping of detection_id -> variant name.
                     When provided, per-variant breakdown is computed.

    Returns:
        Schema 4F dict with:
        - schema_version: "1.0"
        - scored_at: ISO 8601 timestamp
        - label_source: {validate_count, compare_count, total}
        - per_primitive: {primitive_name: {precision, recall, f1, label_count,
                          correct, noise, borderline, per_session, per_variant}}
        - aggregate: {precision, recall, f1, total_labels}
    """
    scored_at = datetime.now(timezone.utc).isoformat()

    # Label source counts
    validate_count = sum(1 for l in labels if l.get("labelled_by") == "validate")
    compare_count = sum(1 for l in labels if l.get("labelled_by") == "compare")

    # Group labels by primitive
    by_primitive: dict[str, list[dict[str, str]]] = defaultdict(list)
    for label in labels:
        by_primitive[label["primitive"]].append(label)

    # Compute per-primitive scores
    per_primitive: dict[str, dict[str, Any]] = {}
    for primitive in sorted(by_primitive.keys()):
        prim_labels = by_primitive[primitive]
        scores = _score_label_group(prim_labels)

        # Per-session breakdown
        by_session: dict[str, list[dict[str, str]]] = defaultdict(list)
        for label in prim_labels:
            session = session_from_detection_id(label["detection_id"])
            by_session[session].append(label)

        per_session = {}
        for sess in _SESSION_CATEGORIES:
            if sess in by_session:
                per_session[sess] = _score_session_group(by_session[sess])
            else:
                per_session[sess] = _empty_session_scores()

        scores["per_session"] = per_session

        # Per-variant breakdown
        per_variant: dict[str, dict[str, Any]] = {}
        if variant_map:
            by_variant: dict[str, list[dict[str, str]]] = defaultdict(list)
            for label in prim_labels:
                variant = variant_map.get(label["detection_id"])
                if variant is not None:
                    by_variant[variant].append(label)

            for variant_name in sorted(by_variant.keys()):
                variant_labels = by_variant[variant_name]
                variant_scores = _score_session_group(variant_labels)
                per_variant[variant_name] = variant_scores

        scores["per_variant"] = per_variant

        per_primitive[primitive] = scores

    # Compute aggregate scores across all primitives
    total_correct, total_noise, total_borderline, total_missed = _count_labels(labels)
    agg_precision = compute_precision(total_correct, total_noise)
    agg_recall = compute_recall(total_correct, total_missed)
    agg_f1 = compute_f1(agg_precision, agg_recall)

    return {
        "schema_version": "1.0",
        "scored_at": scored_at,
        "label_source": {
            "validate_count": validate_count,
            "compare_count": compare_count,
            "total": len(labels),
        },
        "per_primitive": per_primitive,
        "aggregate": {
            "precision": agg_precision,
            "recall": agg_recall,
            "f1": agg_f1,
            "total_labels": len(labels),
        },
    }
