"""Walk-forward validation framework (Phase 2).

Provides:

1. WalkForwardRunner: Sliding window framework for train/test evaluation.
   - generate_windows(): Generate train/test windows with calendar-month boundaries.
   - run(): Execute cascade on each window, compute per-window metrics.
   - Per-window output: train_period, test_period, train_metric, test_metric,
     delta, delta_pct, regime_tags, passed.
   - Summary: windows_total, windows_passed, windows_failed, mean_test_metric,
     std_test_metric, mean_delta, worst_window, degradation_flag, verdict.

2. Verdict rules:
   - STABLE: all windows pass, no degradation
   - CONDITIONALLY_STABLE: some fail but majority pass
   - UNSTABLE: majority fail

3. Edge cases:
   - Windows with zero bars are skipped (no crash)
   - delta_pct returns null when train_metric == 0

Output conforms to Schema 4E.
"""

import logging
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

from ra.config.schema import RAConfig
from ra.engine.base import DetectionResult
from ra.evaluation.comparison import compute_stats
from ra.evaluation.runner import EvaluationRunner, _filter_bars_by_date

logger = logging.getLogger(__name__)


@dataclass
class WindowConfig:
    """Configuration for walk-forward window generation."""
    train_months: int = 3
    test_months: int = 1
    step_months: int = 1


@dataclass
class WindowPeriod:
    """A single train/test window definition."""
    train_start: str  # "YYYY-MM-DD"
    train_end: str     # "YYYY-MM-DD"
    test_start: str    # "YYYY-MM-DD"
    test_end: str      # "YYYY-MM-DD"


def generate_windows(
    start_date: str,
    end_date: str,
    train_months: int = 3,
    test_months: int = 1,
    step_months: int = 1,
) -> list[WindowPeriod]:
    """Generate sliding train/test windows with calendar-month boundaries.

    Windows are defined by calendar months:
    - First window: train starts at start_date's month, test follows immediately.
    - Each subsequent window shifts by step_months.
    - Windows stop when the test period would exceed end_date.

    Args:
        start_date: Overall start date (e.g., "2024-01-01"). Month boundary used.
        end_date: Overall end date (e.g., "2024-12-31"). Month boundary used.
        train_months: Number of months for training period.
        test_months: Number of months for test period.
        step_months: Number of months to step forward between windows.

    Returns:
        List of WindowPeriod objects with train/test date ranges.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    # Normalize to first of month for window boundaries
    current_month = date(start.year, start.month, 1)
    end_month_last = _last_day_of_month(end.year, end.month)

    windows: list[WindowPeriod] = []

    while True:
        train_start = current_month
        train_end_month = _add_months(train_start, train_months)
        train_end = train_end_month - timedelta(days=1)

        test_start = train_end_month
        test_end_month = _add_months(test_start, test_months)
        test_end = test_end_month - timedelta(days=1)

        # Stop if test period exceeds the end date
        if test_end > end_month_last:
            break

        windows.append(WindowPeriod(
            train_start=train_start.isoformat(),
            train_end=train_end.isoformat(),
            test_start=test_start.isoformat(),
            test_end=test_end.isoformat(),
        ))

        # Step forward
        current_month = _add_months(current_month, step_months)

    return windows


def _add_months(d: date, months: int) -> date:
    """Add calendar months to a date (always returns first of month).

    Args:
        d: Starting date (should be first of month).
        months: Number of months to add.

    Returns:
        First day of the resulting month.
    """
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


def _last_day_of_month(year: int, month: int) -> date:
    """Return the last day of the given month."""
    _, last_day = monthrange(year, month)
    return date(year, month, last_day)


class WalkForwardRunner:
    """Walk-forward validation framework.

    Runs cascade on sliding train/test windows and computes per-window
    metrics, summary statistics, and stability verdicts.

    Output conforms to Schema 4E.

    Usage:
        runner = WalkForwardRunner(config)
        result = runner.run(
            bars_by_tf=bars_by_tf,
            primitive="displacement",
            metric="detection_count",
            window_config=WindowConfig(train_months=3, test_months=1, step_months=1),
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
    """

    def __init__(
        self,
        config: RAConfig,
        variant: str = "a8ra_v1",
        pass_threshold_pct: float = 15.0,
    ) -> None:
        """Initialize the walk-forward runner.

        Args:
            config: Validated RAConfig instance.
            variant: Detector variant name.
            pass_threshold_pct: Percentage threshold for window pass/fail.
                Window passes when abs(delta_pct) <= pass_threshold_pct.
        """
        self._config = config
        self._variant = variant
        self._pass_threshold_pct = pass_threshold_pct

        logger.info(
            "WalkForwardRunner initialized (variant=%s, threshold=%.1f%%)",
            variant, pass_threshold_pct,
        )

    def run(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        primitive: str,
        metric: str = "detection_count",
        window_config: Optional[WindowConfig] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        pass_threshold_pct: Optional[float] = None,
    ) -> dict[str, Any]:
        """Run walk-forward validation over sliding windows.

        For each window:
        1. Filter bars to train period and run cascade → compute train_metric.
        2. Filter bars to test period and run cascade → compute test_metric.
        3. Compute delta, delta_pct, passed.

        Windows with zero bars in either train or test are skipped.

        Args:
            bars_by_tf: Full dataset (bars for all timeframes).
            primitive: Primitive name to evaluate (e.g., "displacement").
            metric: Metric name (e.g., "detection_count", "cascade_to_mss_rate").
            window_config: Window configuration. Defaults to 3/1/1 months.
            start_date: Start date for window generation. If None, inferred from data.
            end_date: End date for window generation. If None, inferred from data.
            pass_threshold_pct: Override instance-level threshold. Optional.

        Returns:
            Dict conforming to Schema 4E with windows[] and summary.
        """
        if window_config is None:
            window_config = WindowConfig()

        threshold = pass_threshold_pct if pass_threshold_pct is not None else self._pass_threshold_pct

        # Infer date range from data if not provided
        if start_date is None or end_date is None:
            inferred_start, inferred_end = self._infer_date_range(bars_by_tf)
            if start_date is None:
                start_date = inferred_start
            if end_date is None:
                end_date = inferred_end

        # Generate windows
        windows = generate_windows(
            start_date,
            end_date,
            train_months=window_config.train_months,
            test_months=window_config.test_months,
            step_months=window_config.step_months,
        )

        logger.info(
            "Walk-forward: %d windows for %s [%s to %s] "
            "(train=%d, test=%d, step=%d months)",
            len(windows), primitive, start_date, end_date,
            window_config.train_months, window_config.test_months,
            window_config.step_months,
        )

        # Process each window
        window_results: list[dict[str, Any]] = []
        window_index = 0

        for win in windows:
            result = self._process_window(
                bars_by_tf=bars_by_tf,
                window=win,
                primitive=primitive,
                metric=metric,
                window_index=window_index,
                threshold=threshold,
            )

            if result is not None:
                window_results.append(result)

            window_index += 1

        # Compute summary
        summary = self._compute_summary(window_results, threshold)

        return {
            "config": "current_locked",
            "primitive": primitive,
            "metric": metric,
            "window_config": {
                "train_months": window_config.train_months,
                "test_months": window_config.test_months,
                "step_months": window_config.step_months,
            },
            "windows": window_results,
            "summary": summary,
        }

    def _process_window(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        window: WindowPeriod,
        primitive: str,
        metric: str,
        window_index: int,
        threshold: float,
    ) -> Optional[dict[str, Any]]:
        """Process a single train/test window.

        Runs cascade on train and test periods independently.
        Returns None if either period has zero bars (skipped).

        Args:
            bars_by_tf: Full dataset.
            window: WindowPeriod defining train/test ranges.
            primitive: Target primitive name.
            metric: Metric name.
            window_index: Sequential window index.
            threshold: Pass threshold percentage.

        Returns:
            Window result dict or None if skipped.
        """
        # Filter bars for train period
        train_bars = _filter_bars_by_date(
            bars_by_tf, window.train_start, window.train_end
        )

        # Filter bars for test period
        test_bars = _filter_bars_by_date(
            bars_by_tf, window.test_start, window.test_end
        )

        # Check for zero bars — skip if either is empty
        train_bar_count = self._count_bars(train_bars)
        test_bar_count = self._count_bars(test_bars)

        if train_bar_count == 0 or test_bar_count == 0:
            logger.info(
                "Window %d skipped: train=%d bars, test=%d bars",
                window_index, train_bar_count, test_bar_count,
            )
            return None

        # Run cascade on train period
        eval_runner = EvaluationRunner(self._config, variant=self._variant)
        train_results = eval_runner.run_locked(train_bars)

        # Run cascade on test period (fresh engine for isolation)
        eval_runner_test = EvaluationRunner(self._config, variant=self._variant)
        test_results = eval_runner_test.run_locked(test_bars)

        # Compute metric for each period
        train_metric = self._compute_metric(
            train_results, primitive, metric
        )
        test_metric = self._compute_metric(
            test_results, primitive, metric
        )

        # Compute delta and delta_pct
        delta = test_metric - train_metric

        if train_metric == 0:
            delta_pct = None
        else:
            delta_pct = round((delta / train_metric) * 100.0, 2)

        # Determine passed
        if delta_pct is None:
            passed = True  # Can't compute degradation, treat as pass
        else:
            passed = abs(delta_pct) <= threshold

        return {
            "window_index": window_index,
            "train_period": {
                "start": window.train_start,
                "end": window.train_end,
            },
            "test_period": {
                "start": window.test_start,
                "end": window.test_end,
            },
            "train_metric": round(train_metric, 6),
            "test_metric": round(test_metric, 6),
            "delta": round(delta, 6),
            "delta_pct": delta_pct,
            "regime_tags": [],  # Empty when regime_slicing.enabled=false
            "passed": passed,
        }

    def _compute_metric(
        self,
        results: dict[str, dict[str, DetectionResult]],
        primitive: str,
        metric: str,
    ) -> float:
        """Compute the specified metric for a primitive from cascade results.

        Supported metrics:
        - "detection_count": total detections for the primitive across all TFs.
        - "cascade_to_mss_rate": MSS count / displacement count on primary TF.
        - "detections_per_day": mean detections per forex day.

        Args:
            results: Cascade results dict.
            primitive: Target primitive name.
            metric: Metric name.

        Returns:
            Float metric value.
        """
        if metric == "detection_count":
            return self._metric_detection_count(results, primitive)
        elif metric == "cascade_to_mss_rate":
            return self._metric_cascade_to_mss_rate(results)
        elif metric == "detections_per_day":
            return self._metric_detections_per_day(results, primitive)
        else:
            # Default: detection_count
            logger.warning(
                "Unknown metric '%s', falling back to detection_count", metric
            )
            return self._metric_detection_count(results, primitive)

    def _metric_detection_count(
        self,
        results: dict[str, dict[str, DetectionResult]],
        primitive: str,
    ) -> float:
        """Count total detections for a primitive across all timeframes."""
        total = 0
        prim_results = results.get(primitive, {})
        for tf, det_result in prim_results.items():
            total += len(det_result.detections)
        return float(total)

    def _metric_cascade_to_mss_rate(
        self,
        results: dict[str, dict[str, DetectionResult]],
    ) -> float:
        """Compute MSS/displacement rate on primary TF (5m)."""
        primary_tf = "5m"

        disp_result = results.get("displacement", {}).get(primary_tf)
        mss_result = results.get("mss", {}).get(primary_tf)

        disp_count = len(disp_result.detections) if disp_result else 0
        mss_count = len(mss_result.detections) if mss_result else 0

        if disp_count == 0:
            return 0.0

        return mss_count / disp_count

    def _metric_detections_per_day(
        self,
        results: dict[str, dict[str, DetectionResult]],
        primitive: str,
    ) -> float:
        """Compute mean detections per forex day."""
        stats = compute_stats(results)
        prim_stats = stats.get(primitive, {})

        # Average across all timeframes
        per_day_values = []
        for tf, tf_stats in prim_stats.items():
            per_day_values.append(tf_stats.get("detections_per_day", 0.0))

        if not per_day_values:
            return 0.0

        return sum(per_day_values) / len(per_day_values)

    def _compute_summary(
        self,
        window_results: list[dict[str, Any]],
        threshold: float,
    ) -> dict[str, Any]:
        """Compute walk-forward summary statistics.

        Verdicts:
        - STABLE: all windows pass, no degradation
        - CONDITIONALLY_STABLE: some fail but majority pass
        - UNSTABLE: majority fail

        Args:
            window_results: List of per-window result dicts.
            threshold: Pass threshold percentage.

        Returns:
            Summary dict per Schema 4E.
        """
        total = len(window_results)

        if total == 0:
            return {
                "windows_total": 0,
                "windows_passed": 0,
                "windows_failed": 0,
                "mean_test_metric": 0.0,
                "std_test_metric": 0.0,
                "mean_delta": 0.0,
                "worst_window": None,
                "degradation_flag": False,
                "pass_threshold_pct": threshold,
                "verdict": "STABLE",
            }

        passed_count = sum(1 for w in window_results if w["passed"])
        failed_count = total - passed_count

        # Test metric stats
        test_metrics = [w["test_metric"] for w in window_results]
        mean_test = sum(test_metrics) / total
        variance = sum((m - mean_test) ** 2 for m in test_metrics) / total
        std_test = variance ** 0.5

        # Mean delta
        deltas = [w["delta"] for w in window_results]
        mean_delta = sum(deltas) / total

        # Worst window (lowest test_metric)
        worst = min(window_results, key=lambda w: w["test_metric"])
        worst_window = {
            "window_index": worst["window_index"],
            "test_period": _format_period(worst["test_period"]),
            "test_metric": worst["test_metric"],
            "regime": "",  # Empty when regime_slicing disabled
        }

        # Degradation flag
        degradation_flag = failed_count > 0

        # Verdict
        if not degradation_flag:
            verdict = "STABLE"
        elif passed_count > failed_count:
            verdict = "CONDITIONALLY_STABLE"
        else:
            verdict = "UNSTABLE"

        return {
            "windows_total": total,
            "windows_passed": passed_count,
            "windows_failed": failed_count,
            "mean_test_metric": round(mean_test, 6),
            "std_test_metric": round(std_test, 6),
            "mean_delta": round(mean_delta, 6),
            "worst_window": worst_window,
            "degradation_flag": degradation_flag,
            "pass_threshold_pct": threshold,
            "verdict": verdict,
        }

    @staticmethod
    def _count_bars(bars_by_tf: dict[str, pd.DataFrame]) -> int:
        """Count total bars across all timeframes (uses 1m if available)."""
        # Prefer 1m count as the canonical bar count
        if "1m" in bars_by_tf:
            return len(bars_by_tf["1m"])
        # Fallback: sum of all TFs
        return sum(len(df) for df in bars_by_tf.values())

    @staticmethod
    def _infer_date_range(
        bars_by_tf: dict[str, pd.DataFrame],
    ) -> tuple[str, str]:
        """Infer date range from bars data.

        Uses timestamp_ny column to determine min/max dates.

        Returns:
            Tuple of (start_date, end_date) as "YYYY-MM-DD" strings.
        """
        min_ts = None
        max_ts = None

        for tf, bars in bars_by_tf.items():
            if bars.empty:
                continue

            if "timestamp_ny" in bars.columns:
                ts_col = "timestamp_ny"
            elif "timestamp" in bars.columns:
                ts_col = "timestamp"
            else:
                continue

            ts = pd.to_datetime(bars[ts_col])
            if min_ts is None or ts.min() < min_ts:
                min_ts = ts.min()
            if max_ts is None or ts.max() > max_ts:
                max_ts = ts.max()

        if min_ts is None or max_ts is None:
            raise ValueError("Cannot infer date range from empty bars data")

        # Handle timezone-aware timestamps
        start_date = min_ts.date().isoformat() if hasattr(min_ts, 'date') else str(min_ts)[:10]
        end_date = max_ts.date().isoformat() if hasattr(max_ts, 'date') else str(max_ts)[:10]

        return start_date, end_date


def _format_period(period: dict[str, str]) -> str:
    """Format a period dict to a human-readable string.

    Args:
        period: Dict with "start" and "end" keys.

    Returns:
        Formatted string like "Jan 2024" or "Jan-Mar 2024".
    """
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])

    month_names = [
        "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    if start.year == end.year and start.month == end.month:
        return f"{month_names[start.month]} {start.year}"
    elif start.year == end.year:
        return f"{month_names[start.month]}-{month_names[end.month]} {start.year}"
    else:
        return f"{month_names[start.month]} {start.year}-{month_names[end.month]} {end.year}"
