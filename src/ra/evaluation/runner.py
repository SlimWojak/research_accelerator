"""EvaluationRunner: wraps CascadeEngine for parameter exploration.

Provides high-level methods for:
- run_locked(): replay locked baseline params
- run_sweep(): single-primitive sweep using extract_sweep_combos()
- run_grid(): 2D grid sweep for two params
- run_comparison(): delegate pairwise comparison

Each result carries correct params_used provenance. Leverages
CascadeEngine.on_param_change() for cache-aware incremental re-runs.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from ra.config.schema import RAConfig
from ra.engine.base import DetectionResult
from ra.engine.cascade import CascadeEngine, build_default_registry
from ra.evaluation.param_extraction import (
    extract_params,
    extract_sweep_combos,
)

logger = logging.getLogger(__name__)

# All valid primitive names (matching param_extraction._VALID_PRIMITIVES)
_ALL_PRIMITIVES = [
    "fvg", "ifvg", "bpr", "swing_points", "displacement",
    "session_liquidity", "asia_range", "mss", "order_block",
    "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
    "equal_hl",
]


def _build_all_locked_params(config: RAConfig) -> dict[str, dict]:
    """Build locked params dict for all primitives from config."""
    params: dict[str, dict] = {}
    for prim in _ALL_PRIMITIVES:
        params[prim] = extract_params(config, prim, mode="locked")
    return params


def _filter_bars_by_date(
    bars_by_tf: dict[str, pd.DataFrame],
    start_date: Optional[str],
    end_date: Optional[str],
) -> dict[str, pd.DataFrame]:
    """Filter bars DataFrames to a date range.

    Uses timestamp_ny column for filtering (NY timezone dates).
    Returns a new dict with filtered copies of each DataFrame.

    Args:
        bars_by_tf: Original bars by timeframe.
        start_date: Start date string (inclusive), e.g., "2024-01-08".
        end_date: End date string (inclusive), e.g., "2024-01-10".

    Returns:
        New dict of timeframe -> filtered DataFrame.
    """
    if start_date is None and end_date is None:
        return bars_by_tf

    filtered = {}
    for tf, bars in bars_by_tf.items():
        df = bars.copy()

        if "timestamp_ny" in df.columns:
            ts_col = "timestamp_ny"
        elif "timestamp" in df.columns:
            ts_col = "timestamp"
        else:
            filtered[tf] = df
            continue

        ts = pd.to_datetime(df[ts_col])

        if start_date is not None:
            start_ts = pd.Timestamp(start_date)
            # If ts is tz-aware, localize the comparison
            if ts.dt.tz is not None:
                start_ts = start_ts.tz_localize(ts.dt.tz)
            mask_start = ts >= start_ts
        else:
            mask_start = pd.Series(True, index=df.index)

        if end_date is not None:
            # End of end_date (inclusive): use next day boundary
            end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
            if ts.dt.tz is not None:
                end_ts = end_ts.tz_localize(ts.dt.tz)
            mask_end = ts < end_ts
        else:
            mask_end = pd.Series(True, index=df.index)

        df_filtered = df[mask_start & mask_end].reset_index(drop=True)
        filtered[tf] = df_filtered

    return filtered


class EvaluationRunner:
    """High-level runner wrapping CascadeEngine for parameter exploration.

    Usage:
        runner = EvaluationRunner(config)
        results = runner.run_locked(bars_by_tf)
        sweep = runner.run_sweep(bars_by_tf, "fvg")
        grid = runner.run_grid(bars_by_tf, "displacement", "ltf.atr_multiplier", "ltf.body_ratio")
    """

    def __init__(
        self,
        config: RAConfig,
        variant: str = "a8ra_v1",
    ) -> None:
        """Initialize the evaluation runner.

        Args:
            config: Validated RAConfig instance.
            variant: Detector variant name (default "a8ra_v1").
        """
        self._config = config
        self._variant = variant
        self._registry = build_default_registry()
        self._dep_graph = {
            name: node.model_dump()
            for name, node in config.dependency_graph.items()
        }

        logger.info("EvaluationRunner initialized with variant '%s'", variant)

    def _build_engine(self) -> CascadeEngine:
        """Create a fresh CascadeEngine instance."""
        return CascadeEngine(
            self._registry, self._dep_graph, variant=self._variant
        )

    def run_locked(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict[str, dict[str, DetectionResult]]:
        """Run cascade with all locked params.

        Produces identical results to Phase 1 CascadeEngine output.

        Args:
            bars_by_tf: Mapping of timeframe -> bar DataFrame.
            start_date: Optional start date for data windowing.
            end_date: Optional end date for data windowing.

        Returns:
            Nested dict: results[primitive_name][timeframe] -> DetectionResult.
        """
        # Apply data windowing
        filtered_bars = _filter_bars_by_date(bars_by_tf, start_date, end_date)

        # Build locked params for all primitives
        params = _build_all_locked_params(self._config)

        # Run cascade
        engine = self._build_engine()
        results = engine.run(filtered_bars, params)

        return results

    def run_sweep(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        primitive: str,
        params: Optional[list[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Sweep one primitive's params using extract_sweep_combos().

        Leverages CascadeEngine.on_param_change() for cache-aware
        incremental re-runs. Only the changed primitive and its
        downstream are re-run; upstream serves from cache.

        Args:
            bars_by_tf: Mapping of timeframe -> bar DataFrame.
            primitive: Primitive name to sweep.
            params: Optional list of dot-separated param paths to sweep.
                If None, sweeps all params with sweep_range.
            start_date: Optional start date for data windowing.
            end_date: Optional end date for data windowing.

        Returns:
            List of dicts, each with:
                - "results": full cascade result dict
                - "params_used": dict of all primitive params for this step
                - "combo_index": index in the sweep
        """
        # Apply data windowing
        filtered_bars = _filter_bars_by_date(bars_by_tf, start_date, end_date)

        # Generate sweep combos for the target primitive
        combos = extract_sweep_combos(self._config, primitive, params=params)

        # Build base locked params
        base_params = _build_all_locked_params(self._config)

        # Create a single engine and reuse it across sweep steps
        engine = self._build_engine()

        sweep_results: list[dict[str, Any]] = []

        for i, combo in enumerate(combos):
            # Copy base params and override the swept primitive
            step_params = copy.deepcopy(base_params)
            step_params[primitive] = combo

            if i == 0:
                # First run: full cascade execution (populates cache)
                results = engine.run(filtered_bars, step_params)
            else:
                # Subsequent runs: invalidate changed primitive + downstream
                engine.on_param_change(primitive)
                results = engine.run(filtered_bars, step_params)

            sweep_results.append({
                "results": copy.deepcopy(results),
                "params_used": copy.deepcopy(step_params),
                "combo_index": i,
            })

            logger.info(
                "Sweep step %d/%d for '%s' complete",
                i + 1, len(combos), primitive,
            )

        return sweep_results

    def run_grid(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        primitive: str,
        x_param: str,
        y_param: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """2D grid sweep for two params of a primitive.

        Generates Cartesian product of the two params' sweep_range values,
        keeping all other params at locked baseline.

        Args:
            bars_by_tf: Mapping of timeframe -> bar DataFrame.
            primitive: Primitive name to sweep.
            x_param: Dot-separated path for x-axis param.
            y_param: Dot-separated path for y-axis param.
            start_date: Optional start date for data windowing.
            end_date: Optional end date for data windowing.

        Returns:
            List of dicts (same structure as run_sweep), ordered by
            Cartesian product: x_param varies first (outer), y_param second (inner).
        """
        # Delegate to run_sweep with both params
        return self.run_sweep(
            bars_by_tf,
            primitive,
            params=[x_param, y_param],
            start_date=start_date,
            end_date=end_date,
        )

    def run_comparison(
        self,
        results_a: dict[str, dict[str, DetectionResult]],
        results_b: dict[str, dict[str, DetectionResult]],
    ) -> dict[str, Any]:
        """Compare two sets of cascade results.

        Delegates to the comparison module (when implemented).
        For now, provides a basic structural comparison.

        Args:
            results_a: First cascade result dict.
            results_b: Second cascade result dict.

        Returns:
            Comparison result dict with per-primitive stats.
        """
        comparison: dict[str, Any] = {
            "per_primitive": {},
            "summary": {
                "total_a": 0,
                "total_b": 0,
            },
        }

        for prim in results_a:
            prim_comp: dict[str, Any] = {"per_tf": {}}

            for tf in results_a.get(prim, {}):
                det_a = results_a[prim].get(tf)
                det_b = results_b.get(prim, {}).get(tf)

                count_a = len(det_a.detections) if det_a else 0
                count_b = len(det_b.detections) if det_b else 0

                comparison["summary"]["total_a"] += count_a
                comparison["summary"]["total_b"] += count_b

                # Basic detection matching by ID
                ids_a = {d.id for d in det_a.detections} if det_a else set()
                ids_b = {d.id for d in det_b.detections} if det_b else set()

                agreed = ids_a & ids_b
                only_a = ids_a - ids_b
                only_b = ids_b - ids_a
                total_unique = len(ids_a | ids_b)

                agreement_rate = (
                    len(agreed) / total_unique if total_unique > 0 else 1.0
                )

                prim_comp["per_tf"][tf] = {
                    "count_a": count_a,
                    "count_b": count_b,
                    "agreement_rate": agreement_rate,
                    "only_in_a": len(only_a),
                    "only_in_b": len(only_b),
                }

            comparison["per_primitive"][prim] = prim_comp

        return comparison
