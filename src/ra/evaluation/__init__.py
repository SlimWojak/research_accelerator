"""Evaluation runner, comparison statistics, cascade stats, and walk-forward."""

from ra.evaluation.runner import EvaluationRunner
from ra.evaluation.comparison import compute_stats, compare_pairwise, compare_multi
from ra.evaluation.cascade_stats import cascade_funnel, cascade_completion
from ra.evaluation.walk_forward import WalkForwardRunner, generate_windows, WindowConfig

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
]
