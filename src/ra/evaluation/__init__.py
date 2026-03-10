"""Evaluation runner, comparison statistics, cascade stats, walk-forward, and label ingestion."""

from ra.evaluation.runner import EvaluationRunner
from ra.evaluation.comparison import compute_stats, compare_pairwise, compare_multi
from ra.evaluation.cascade_stats import cascade_funnel, cascade_completion
from ra.evaluation.walk_forward import WalkForwardRunner, generate_windows, WindowConfig
from ra.evaluation.label_ingestion import (
    load_validate_labels,
    load_compare_labels,
    load_all_labels,
    normalize_label,
    compute_label_summary,
)
from ra.evaluation.scoring import (
    compute_precision,
    compute_recall,
    compute_f1,
    score_labels,
    session_from_detection_id,
)

__all__ = [
    "EvaluationRunner",
    "compute_stats",
    "compare_pairwise",
    "compare_multi",
    "cascade_funnel",
    "cascade_completion",
    "WalkForwardRunner",
    "generate_windows",
    "WindowConfig",
    "load_validate_labels",
    "load_compare_labels",
    "load_all_labels",
    "normalize_label",
    "compute_label_summary",
    "compute_precision",
    "compute_recall",
    "compute_f1",
    "score_labels",
    "session_from_detection_id",
]
