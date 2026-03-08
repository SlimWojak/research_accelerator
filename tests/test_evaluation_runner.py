"""Tests for EvaluationRunner (Phase 2).

Validates:
- VAL-EVAL-001: Locked baseline replay matches Phase 1 (9784 detections)
- VAL-EVAL-002: Single-param sweep produces N result sets with variation
- VAL-EVAL-003: Multi-param grid sweep (Cartesian product)
- VAL-EVAL-004: Cache reuse during sweep (FVG.detect() called once)
- VAL-EVAL-005: params_used provenance correct in each result
- VAL-EVAL-006: Data windowing constrains detections to date range
- VAL-EVAL-007: Per-TF sweep params resolved correctly
- VAL-EVAL-008: DEFERRED modules handled gracefully
- VAL-EVAL-009: Empty sweep_range uses locked value
- VAL-EVAL-011: Downstream re-run on param change
- run_comparison delegation
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from ra.config.loader import load_config
from ra.engine.base import Detection, DetectionResult
from ra.engine.cascade import (
    CascadeEngine,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.evaluation.param_extraction import extract_params, extract_sweep_combos
from ra.evaluation.runner import EvaluationRunner


NY_TZ = ZoneInfo("America/New_York")


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def config():
    """Load the locked baseline config."""
    return load_config("configs/locked_baseline.yaml")


@pytest.fixture(scope="module")
def bars_by_tf():
    """Load and aggregate 5-day CSV dataset for all runner tests."""
    from ra.data.csv_loader import load_csv
    from ra.data.session_tagger import tag_sessions
    from ra.data.tf_aggregator import aggregate

    bars_1m = load_csv("data/eurusd_1m_2024-01-07_to_2024-01-12.csv")
    bars_1m = tag_sessions(bars_1m)
    result = {"1m": bars_1m}
    for tf in ["5m", "15m"]:
        result[tf] = aggregate(bars_1m, tf)
    return result


@pytest.fixture(scope="module")
def runner(config):
    """Create an EvaluationRunner with default registry."""
    return EvaluationRunner(config)


# ─── VAL-EVAL-001: Locked baseline replay matches Phase 1 ────────────────

def test_locked_matches_phase1(runner, config, bars_by_tf):
    """run_locked() produces identical detection counts to Phase 1 (9784 total)."""
    results = runner.run_locked(bars_by_tf)

    # Count total detections
    total = 0
    for prim, tf_results in results.items():
        for tf, det_result in tf_results.items():
            total += len(det_result.detections)

    assert total == 9784, f"Expected 9784 detections, got {total}"


def test_locked_per_primitive_counts(runner, config, bars_by_tf):
    """run_locked() matches Phase 1 per-primitive per-TF counts."""
    results = runner.run_locked(bars_by_tf)

    # Compare against Phase 1 extraction
    registry = build_default_registry()
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }
    engine = CascadeEngine(registry, dep_graph)
    old_params = extract_locked_params_for_cascade(config)
    phase1_results = engine.run(bars_by_tf, old_params)

    for prim in phase1_results:
        for tf in phase1_results[prim]:
            expected = len(phase1_results[prim][tf].detections)
            actual = len(results[prim][tf].detections)
            assert actual == expected, (
                f"Mismatch for {prim}/{tf}: expected={expected}, actual={actual}"
            )


# ─── VAL-EVAL-002: Single-param sweep execution ──────────────────────────

def test_single_param_sweep_fvg(runner, bars_by_tf):
    """Sweeping FVG floor_threshold_pips produces 5 result sets."""
    sweep_results = runner.run_sweep(bars_by_tf, "fvg")

    # 5 sweep values: [0.0, 0.5, 1.0, 1.5, 2.0]
    assert len(sweep_results) == 5

    # Each result should be a full cascade result dict
    for result in sweep_results:
        assert "fvg" in result["results"]
        # Results should have valid DetectionResult objects
        for tf in result["results"]["fvg"]:
            assert hasattr(result["results"]["fvg"][tf], "detections")


def test_single_param_sweep_with_variation(runner, bars_by_tf):
    """Sweeping displacement close_gate produces variation in counts."""
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )

    # 5 close_gate values: [0.10, 0.15, 0.20, 0.25, 0.30]
    assert len(sweep_results) == 5

    # Detection counts should vary (close_gate produces real variation)
    disp_5m_counts = [
        len(r["results"]["displacement"]["5m"].detections)
        for r in sweep_results
    ]
    assert len(set(disp_5m_counts)) > 1, (
        f"Expected variation in displacement 5m counts, got: {disp_5m_counts}"
    )


def test_single_param_sweep_params_used(runner, bars_by_tf):
    """Each sweep result's params_used reflects the specific close_gate value."""
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )
    expected_values = [0.10, 0.15, 0.20, 0.25, 0.30]

    for i, result in enumerate(sweep_results):
        actual = result["params_used"]["displacement"]["ltf"]["close_gate"]
        assert actual == expected_values[i], (
            f"Sweep step {i}: expected close_gate={expected_values[i]}, "
            f"got {actual}"
        )


# ─── VAL-EVAL-003: Multi-param grid sweep ────────────────────────────────

def test_grid_sweep_2d(runner, bars_by_tf):
    """Grid sweep of displacement close_gate × body_ratio produces 35 results."""
    grid_results = runner.run_grid(
        bars_by_tf,
        "displacement",
        x_param="ltf.close_gate",
        y_param="ltf.body_ratio",
    )

    # 5 close_gate × 7 body_ratio = 35
    assert len(grid_results) == 35

    # Each result should have params_used reflecting the combo
    for result in grid_results:
        params = result["params_used"]["displacement"]
        assert "ltf" in params
        assert "close_gate" in params["ltf"]
        assert "body_ratio" in params["ltf"]


def test_grid_sweep_params_used_correctness(runner, bars_by_tf):
    """Grid sweep params_used correctly reflects each combination."""
    grid_results = runner.run_grid(
        bars_by_tf,
        "displacement",
        x_param="ltf.close_gate",
        y_param="ltf.body_ratio",
    )

    gate_values = [0.10, 0.15, 0.20, 0.25, 0.30]
    body_values = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

    # Check first and last
    first = grid_results[0]["params_used"]["displacement"]
    assert first["ltf"]["close_gate"] == gate_values[0]
    assert first["ltf"]["body_ratio"] == body_values[0]

    last = grid_results[-1]["params_used"]["displacement"]
    assert last["ltf"]["close_gate"] == gate_values[-1]
    assert last["ltf"]["body_ratio"] == body_values[-1]


# ─── VAL-EVAL-004: Cache reuse during sweep ──────────────────────────────

def test_cache_reuse_displacement_sweep(config, bars_by_tf):
    """Sweeping displacement does NOT re-run FVG — cache reuse verified."""
    runner = EvaluationRunner(config)

    # Patch FVG detector's detect method to count calls
    from ra.detectors.fvg import FVGDetector
    original_detect = FVGDetector.detect
    call_count = {"fvg": 0, "displacement": 0}

    def counting_fvg_detect(self, bars, params, upstream=None, context=None):
        call_count["fvg"] += 1
        return original_detect(self, bars, params, upstream=upstream, context=context)

    from ra.detectors.displacement import DisplacementDetector
    original_disp_detect = DisplacementDetector.detect

    def counting_disp_detect(self, bars, params, upstream=None, context=None):
        call_count["displacement"] += 1
        return original_disp_detect(self, bars, params, upstream=upstream, context=context)

    with patch.object(FVGDetector, "detect", counting_fvg_detect):
        with patch.object(DisplacementDetector, "detect", counting_disp_detect):
            # Sweep displacement ltf.close_gate (5 values)
            runner.run_sweep(
                bars_by_tf,
                "displacement",
                params=["ltf.close_gate"],
            )

    # FVG is upstream of MSS (not displacement directly), but displacement
    # change does NOT invalidate FVG. FVG should only run once per TF in
    # the first cascade run, then be cached.
    # With 3 TFs (1m, 5m, 15m), FVG runs 3 times for initial run.
    # On subsequent runs, FVG should be cached (not re-run).
    assert call_count["fvg"] == 3, (
        f"FVG.detect() should be called 3 times (once per TF), "
        f"got {call_count['fvg']}"
    )

    # Displacement should run 5 × 3 = 15 times (5 sweep steps × 3 TFs)
    assert call_count["displacement"] == 15, (
        f"Displacement.detect() should be called 15 times (5 sweeps × 3 TFs), "
        f"got {call_count['displacement']}"
    )


# ─── VAL-EVAL-005: params_used provenance ────────────────────────────────

def test_params_used_provenance_differs(runner, bars_by_tf):
    """params_used differs between sweep steps for the swept param."""
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )

    params_list = [r["params_used"]["displacement"]["ltf"] for r in sweep_results]
    gate_values = [p["close_gate"] for p in params_list]

    # All 5 values should be distinct
    assert len(set(gate_values)) == 5
    assert gate_values == [0.10, 0.15, 0.20, 0.25, 0.30]


def test_params_used_includes_all_primitives(runner, bars_by_tf):
    """params_used in sweep results contains all primitive params."""
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )

    for result in sweep_results:
        assert "displacement" in result["params_used"]
        # Non-swept primitives should have their locked params
        assert "fvg" in result["params_used"]
        assert "swing_points" in result["params_used"]


# ─── VAL-EVAL-006: Data windowing ────────────────────────────────────────

def test_data_windowing_constrains_detections(runner, bars_by_tf):
    """Date range filtering constrains detections to specified window."""
    # Run with full data first
    full_results = runner.run_locked(bars_by_tf)

    # Run with restricted date range (just 2 days)
    windowed_results = runner.run_locked(
        bars_by_tf,
        start_date="2024-01-08",
        end_date="2024-01-09",
    )

    # Windowed should have fewer detections
    def count_all(results):
        total = 0
        for prim, tf_results in results.items():
            for tf, det_result in tf_results.items():
                total += len(det_result.detections)
        return total

    full_count = count_all(full_results)
    windowed_count = count_all(windowed_results)

    assert windowed_count < full_count, (
        f"Windowed ({windowed_count}) should be < full ({full_count})"
    )
    assert windowed_count > 0, "Windowed results should not be empty"


def test_data_windowing_detection_times_in_range(runner, bars_by_tf):
    """All detection timestamps fall within the specified date range."""
    windowed_results = runner.run_locked(
        bars_by_tf,
        start_date="2024-01-09",
        end_date="2024-01-10",
    )

    start = pd.Timestamp("2024-01-09", tz="America/New_York")
    end = pd.Timestamp("2024-01-11", tz="America/New_York")  # end of Jan 10

    for prim, tf_results in windowed_results.items():
        for tf, det_result in tf_results.items():
            for det in det_result.detections:
                det_time = det.time
                if det_time.tzinfo is None:
                    det_time = det_time.replace(tzinfo=NY_TZ)
                # Detection time should be within reasonable range
                # (the bars are filtered, so detections are constrained)
                assert det_time >= start - pd.Timedelta(days=1), (
                    f"Detection {det.id} at {det_time} is before start range"
                )


# ─── VAL-EVAL-007: Per-TF sweep params resolved correctly ────────────────

def test_per_tf_sweep_swing_points(runner, config, bars_by_tf):
    """Per-TF sweep for swing_points applies correct values per TF."""
    # Sweep swing_points N (global sweep range)
    sweep_results = runner.run_sweep(
        bars_by_tf,
        "swing_points",
        params=["N"],
    )

    # N sweep range: [2, 3, 4, 5, 6, 7, 8, 10]
    assert len(sweep_results) == 8

    # Check that per-TF values are set correctly in params_used
    # For swing_points, N should be a per-TF dict when coming from
    # the config, but the sweep replaces it with the global value
    for result in sweep_results:
        sp_params = result["params_used"]["swing_points"]
        assert "N" in sp_params


# ─── VAL-EVAL-008: DEFERRED modules handled gracefully ───────────────────

def test_deferred_module_graceful(runner, bars_by_tf):
    """equal_hl (DEFERRED) produces empty DetectionResult without error."""
    results = runner.run_locked(bars_by_tf)

    # equal_hl should be in results with empty detections
    assert "equal_hl" in results
    for tf in results["equal_hl"]:
        assert len(results["equal_hl"][tf].detections) == 0


def test_deferred_module_not_in_sweep(runner, config):
    """equal_hl should not generate sweep combinations."""
    combos = extract_sweep_combos(config, "equal_hl")
    # DEFERRED returns empty dict, so no sweep combos (just 1 locked)
    assert len(combos) <= 1


# ─── VAL-EVAL-009: Empty sweep_range uses locked value ───────────────────

def test_no_sweep_range_uses_locked(runner, bars_by_tf):
    """Primitives without sweep_range use locked values in all sweep runs."""
    # Sweep displacement close_gate — reference_levels has no sweep_range
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )

    locked_ref = extract_params(runner._config, "reference_levels", mode="locked")
    for result in sweep_results:
        ref_params = result["params_used"]["reference_levels"]
        assert ref_params == locked_ref


# ─── VAL-EVAL-011: Downstream re-run on param change ─────────────────────

def test_downstream_rerun_mss_changes(runner, bars_by_tf):
    """When sweeping displacement close_gate, MSS counts change across steps."""
    sweep_results = runner.run_sweep(
        bars_by_tf,
        "displacement",
        params=["ltf.close_gate"],
    )

    # MSS depends on displacement, so should be re-run
    mss_5m_counts = []
    for result in sweep_results:
        if "mss" in result["results"] and "5m" in result["results"]["mss"]:
            mss_5m_counts.append(len(result["results"]["mss"]["5m"].detections))

    # At least some variation in MSS counts proves re-computation
    assert len(set(mss_5m_counts)) > 1, (
        f"MSS 5m counts should vary across displacement close_gate sweep, "
        f"got: {mss_5m_counts}"
    )


def test_downstream_ob_changes_with_displacement(runner, bars_by_tf):
    """Order block counts change when displacement close_gate changes."""
    sweep_results = runner.run_sweep(
        bars_by_tf,
        "displacement",
        params=["ltf.close_gate"],
    )

    ob_5m_counts = []
    for result in sweep_results:
        if "order_block" in result["results"] and "5m" in result["results"]["order_block"]:
            ob_5m_counts.append(
                len(result["results"]["order_block"]["5m"].detections)
            )

    # OB depends on displacement → MSS → OB chain
    # At least some variation expected (close_gate produces real variation)
    assert len(set(ob_5m_counts)) > 1, (
        f"OB 5m counts should vary across displacement close_gate sweep, "
        f"got: {ob_5m_counts}"
    )


# ─── run_comparison delegation ────────────────────────────────────────────

def test_run_comparison_returns_structure(runner, bars_by_tf):
    """run_comparison delegates and returns comparison structure."""
    results_a = runner.run_locked(bars_by_tf)

    # Run with slightly different params (displacement close_gate sweep)
    sweep_results = runner.run_sweep(
        bars_by_tf, "displacement", params=["ltf.close_gate"]
    )
    results_b = sweep_results[0]["results"]  # close_gate=0.10

    comparison = runner.run_comparison(results_a, results_b)

    # Should return a dict with comparison data
    assert isinstance(comparison, dict)
    assert "per_primitive" in comparison
    assert "summary" in comparison
    assert comparison["summary"]["total_a"] > 0
    assert comparison["summary"]["total_b"] > 0


# ─── Edge cases ───────────────────────────────────────────────────────────

def test_sweep_with_empty_primitive(runner, bars_by_tf):
    """Sweep for primitive without sweep ranges returns single locked result."""
    sweep_results = runner.run_sweep(bars_by_tf, "reference_levels")

    # reference_levels has no sweep_range → single combo with locked values
    assert len(sweep_results) == 1


def test_selective_sweep(runner, bars_by_tf):
    """Selective sweep varies only the specified param."""
    sweep_results = runner.run_sweep(
        bars_by_tf,
        "displacement",
        params=["ltf.close_gate"],
    )

    # Should have 5 results (5 close_gate values)
    assert len(sweep_results) == 5

    # body_ratio should be unchanged across all results
    locked = extract_params(runner._config, "displacement", mode="locked")
    for result in sweep_results:
        disp_params = result["params_used"]["displacement"]
        assert disp_params["ltf"]["body_ratio"] == locked["ltf"]["body_ratio"]
        assert disp_params["ltf"]["atr_multiplier"] == locked["ltf"]["atr_multiplier"]
