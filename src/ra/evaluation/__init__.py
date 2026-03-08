"""Evaluation runner, comparison statistics, and cascade stats."""

from ra.evaluation.runner import EvaluationRunner
from ra.evaluation.comparison import compute_stats, compare_pairwise, compare_multi
from ra.evaluation.cascade_stats import cascade_funnel, cascade_completion

__all__ = [
    "EvaluationRunner",
    "compute_stats",
    "compare_pairwise",
    "compare_multi",
    "cascade_funnel",
    "cascade_completion",
]
