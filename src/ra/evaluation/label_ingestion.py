"""Ground truth label ingestion module.

Loads ground truth labels from two sources:
1. Validate-mode disk JSON: site/data/labels/*.json (one file per week)
2. Compare-mode export JSON: ground_truth_labels.json (from compare.html Export)

Normalizes all labels to canonical 5-field format:
    {detection_id, primitive, timeframe, label, labelled_by}

Deduplication: when the same detection_id appears in both sources,
validate-mode takes precedence.

Handles empty/missing directories gracefully (returns empty list, no crash).
"""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Required fields for a label to be considered valid
_REQUIRED_RAW_FIELDS = {"detection_id", "primitive", "timeframe", "label"}

# Valid label values (after uppercasing)
_VALID_LABELS = {"CORRECT", "NOISE", "BORDERLINE"}


def normalize_label(raw: dict[str, Any], source: str) -> dict[str, str]:
    """Normalize a raw label dict to canonical 5-field format.

    Args:
        raw: Raw label dict from disk or export file.
        source: Source identifier — 'validate' or 'compare'.

    Returns:
        Canonical label dict with exactly 5 fields:
        {detection_id, primitive, timeframe, label, labelled_by}
    """
    return {
        "detection_id": raw["detection_id"],
        "primitive": raw["primitive"],
        "timeframe": raw["timeframe"],
        "label": raw["label"].upper(),
        "labelled_by": source,
    }


def _is_valid_raw_label(raw: Any) -> bool:
    """Check whether a raw label has all required fields."""
    if not isinstance(raw, dict):
        return False
    return _REQUIRED_RAW_FIELDS.issubset(raw.keys())


def load_validate_labels(labels_dir: Path | str | None) -> list[dict[str, str]]:
    """Load and normalize labels from validate-mode disk JSON directory.

    Reads all *.json files from the given directory. Each file should contain
    a JSON array of label objects (one file per week).

    Args:
        labels_dir: Path to labels directory (e.g., site/data/labels/).
                    Can be None, missing, or empty — returns empty list.

    Returns:
        List of normalized canonical label dicts with labelled_by='validate'.
    """
    if labels_dir is None:
        return []

    labels_dir = Path(labels_dir)
    if not labels_dir.exists() or not labels_dir.is_dir():
        logger.debug("Labels directory does not exist or is not a directory: %s", labels_dir)
        return []

    labels: list[dict[str, str]] = []

    for json_file in sorted(labels_dir.glob("*.json")):
        try:
            with open(json_file, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping malformed label file %s: %s", json_file.name, e)
            continue

        if not isinstance(data, list):
            logger.warning("Skipping non-array label file %s", json_file.name)
            continue

        for raw in data:
            if not _is_valid_raw_label(raw):
                logger.warning(
                    "Skipping label missing required fields in %s: %s",
                    json_file.name,
                    raw,
                )
                continue
            labels.append(normalize_label(raw, source="validate"))

    return labels


def load_compare_labels(compare_file: Path | str | None) -> list[dict[str, str]]:
    """Load and normalize labels from compare-mode export JSON file.

    Reads a single JSON file produced by compare.html's Export Labels button.
    The file should contain a JSON array of label objects.

    Args:
        compare_file: Path to the compare-mode export file
                      (e.g., ground_truth_labels.json).
                      Can be None or missing — returns empty list.

    Returns:
        List of normalized canonical label dicts with labelled_by='compare'.
    """
    if compare_file is None:
        return []

    compare_file = Path(compare_file)
    if not compare_file.exists():
        logger.debug("Compare labels file does not exist: %s", compare_file)
        return []

    try:
        with open(compare_file, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Skipping malformed compare labels file %s: %s", compare_file, e)
        return []

    if not isinstance(data, list):
        logger.warning("Compare labels file is not an array: %s", compare_file)
        return []

    labels: list[dict[str, str]] = []
    for raw in data:
        if not _is_valid_raw_label(raw):
            logger.warning("Skipping compare label missing required fields: %s", raw)
            continue
        labels.append(normalize_label(raw, source="compare"))

    return labels


def load_all_labels(
    validate_dir: Path | str | None = None,
    compare_file: Path | str | None = None,
) -> list[dict[str, str]]:
    """Load, normalize, and deduplicate labels from both sources.

    Loads labels from validate-mode disk directory and compare-mode export file,
    normalizes to canonical format, and deduplicates by detection_id.
    When the same detection_id appears in both sources, validate-mode takes
    precedence.

    Args:
        validate_dir: Path to validate-mode labels directory.
        compare_file: Path to compare-mode export JSON file.

    Returns:
        Deduplicated list of canonical label dicts.
    """
    validate_labels = load_validate_labels(validate_dir)
    compare_labels = load_compare_labels(compare_file)

    # Build deduplicated result — validate takes precedence
    seen: dict[str, dict[str, str]] = {}

    # Add validate labels first (they take precedence)
    for label in validate_labels:
        seen[label["detection_id"]] = label

    # Add compare labels only if detection_id not already present
    for label in compare_labels:
        if label["detection_id"] not in seen:
            seen[label["detection_id"]] = label

    return list(seen.values())


def compute_label_summary(labels: list[dict[str, str]]) -> dict[str, Any]:
    """Compute summary counts for a label dataset.

    Args:
        labels: List of canonical label dicts.

    Returns:
        Summary dict with:
        - total: Total label count
        - per_label: {CORRECT: n, NOISE: n, BORDERLINE: n}
        - per_primitive: {primitive_name: count, ...}
        - per_source: {validate: n, compare: n, ...}
    """
    total = len(labels)

    # Per-label counts (always include all three categories)
    label_counts = Counter(l["label"] for l in labels)
    per_label = {
        "CORRECT": label_counts.get("CORRECT", 0),
        "NOISE": label_counts.get("NOISE", 0),
        "BORDERLINE": label_counts.get("BORDERLINE", 0),
    }

    # Per-primitive counts
    per_primitive = dict(Counter(l["primitive"] for l in labels))

    # Per-source counts
    per_source = dict(Counter(l["labelled_by"] for l in labels))

    return {
        "total": total,
        "per_label": per_label,
        "per_primitive": per_primitive,
        "per_source": per_source,
    }
