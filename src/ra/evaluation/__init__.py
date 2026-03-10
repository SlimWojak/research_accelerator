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
from ra.evaluation.perturbation import (
    perturb_config,
    load_search_space,
    apply_perturbation_to_config,
    compute_param_deltas,
)
from ra.evaluation.fitness import (
    compute_fitness,
    evaluate_candidate,
    rank_candidates,
    walk_forward_stability_check,
    build_provenance,
    format_provenance_json,
    format_summary,
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
    "perturb_config",
    "load_search_space",
    "apply_perturbation_to_config",
    "compute_param_deltas",
    "compute_fitness",
    "evaluate_candidate",
    "rank_candidates",
    "walk_forward_stability_check",
    "build_provenance",
    "format_provenance_json",
    "format_summary",
]
