"""Tests for param extraction refactor (Phase 2).

Validates:
- Locked extraction equivalence with hardcoded function for all 14 primitives
- Sweep mode returns sweep_range values
- Per-TF override resolution
- Per-TF sweep ranges
- Cartesian product generation (single, multi, selective)
- Unknown primitive error handling
- CascadeEngine round-trip equivalence (9784 detections)
"""

import itertools

import pytest

from ra.config.loader import load_config
from ra.engine.cascade import (
    CascadeEngine,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.evaluation.param_extraction import (
    ParamExtractionError,
    extract_params,
    extract_sweep_combos,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def config():
    """Load the locked baseline config once for all tests."""
    return load_config("configs/locked_baseline.yaml")


@pytest.fixture(scope="module")
def old_params(config):
    """Get the hardcoded extraction result as ground truth."""
    return extract_locked_params_for_cascade(config)


ALL_PRIMITIVES = [
    "fvg", "ifvg", "bpr", "swing_points", "displacement",
    "session_liquidity", "asia_range", "mss", "order_block",
    "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
    "equal_hl",
]


# ─── VAL-PARAM-001: Locked extraction equivalence for all 14 primitives ──

@pytest.mark.parametrize("primitive", ALL_PRIMITIVES)
def test_locked_extraction_equivalence(config, old_params, primitive):
    """extract_params(mode='locked') matches hardcoded extraction exactly."""
    new = extract_params(config, primitive, mode="locked")
    expected = old_params[primitive]
    assert new == expected, (
        f"Locked extraction mismatch for '{primitive}':\n"
        f"  new:      {new}\n"
        f"  expected: {expected}"
    )


# ─── VAL-PARAM-009: Locked extraction preserves dict format (wrappers) ───

def test_session_liquidity_locked_wrappers(config):
    """Session liquidity locked params preserve {locked: value} wrappers."""
    params = extract_params(config, "session_liquidity", mode="locked")
    fgm = params["four_gate_model"]
    assert isinstance(fgm["efficiency_threshold"], dict)
    assert "locked" in fgm["efficiency_threshold"]
    assert fgm["efficiency_threshold"]["locked"] == 0.60


def test_liquidity_sweep_locked_wrappers(config):
    """Liquidity sweep rejection_wick_pct preserves {locked: value} wrapper."""
    params = extract_params(config, "liquidity_sweep", mode="locked")
    assert isinstance(params["rejection_wick_pct"], dict)
    assert "locked" in params["rejection_wick_pct"]
    assert params["rejection_wick_pct"]["locked"] == 0.40


# ─── VAL-PARAM-003: Per-TF override resolution in locked mode ────────────

def test_swing_points_per_tf_locked(config):
    """Swing points locked mode returns per-TF dict for N and height_filter_pips."""
    params = extract_params(config, "swing_points", mode="locked")
    assert params["N"] == {"1m": 5, "5m": 3, "15m": 2}
    assert params["height_filter_pips"] == {"1m": 0.5, "5m": 3.0, "15m": 3.0}
    assert params["strength_cap"] == 20
    assert params["strength_as_gate"] is False


# ─── VAL-PARAM-002: Sweep mode returns sweep_range values ────────────────

def test_fvg_sweep_mode(config):
    """FVG sweep mode returns sweep_range list for floor_threshold_pips."""
    params = extract_params(config, "fvg", mode="sweep")
    assert "floor_threshold_pips" in params
    assert params["floor_threshold_pips"] == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_displacement_sweep_mode_ltf(config):
    """Displacement sweep mode returns sweep ranges for LTF params."""
    params = extract_params(config, "displacement", mode="sweep")
    assert params["ltf"]["atr_multiplier"] == [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    assert params["ltf"]["body_ratio"] == [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    assert params["ltf"]["close_gate"] == [0.10, 0.15, 0.20, 0.25, 0.30]


def test_displacement_sweep_mode_htf(config):
    """Displacement sweep mode returns sweep ranges for HTF params."""
    params = extract_params(config, "displacement", mode="sweep")
    assert params["htf"]["atr_multiplier"] == [1.0, 1.25, 1.5, 1.75, 2.0]
    assert params["htf"]["body_ratio"] == [0.55, 0.60, 0.65, 0.70, 0.75]
    assert params["htf"]["close_gate"] == [0.10, 0.15, 0.20, 0.25, 0.30]


# ─── VAL-PARAM-004: Per-TF sweep ranges in sweep mode ────────────────────

def test_swing_points_height_filter_sweep_per_tf(config):
    """Swing points height_filter_pips has per-TF sweep ranges."""
    params = extract_params(config, "swing_points", mode="sweep")
    hf = params["height_filter_pips"]
    assert isinstance(hf, dict)
    assert hf["1m"] == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    assert hf["5m"] == [2.0, 3.0, 5.0, 7.0, 10.0, 15.0]
    assert hf["15m"] == [3.0, 5.0, 7.0, 10.0, 15.0, 20.0]


def test_swing_points_N_sweep_global(config):
    """Swing points N has a single global sweep range (shared across TFs)."""
    params = extract_params(config, "swing_points", mode="sweep")
    assert params["N"] == [2, 3, 4, 5, 6, 7, 8, 10]


# ─── VAL-PARAM-005: Single-param Cartesian product (FVG = 5 combos) ──────

def test_fvg_sweep_combos(config):
    """FVG sweep generates 5 param combinations."""
    combos = extract_sweep_combos(config, "fvg")
    assert len(combos) == 5
    # Each combo should be a full param dict
    assert combos[0]["floor_threshold_pips"] == 0.0
    assert combos[-1]["floor_threshold_pips"] == 2.0


# ─── VAL-PARAM-006: Multi-param Cartesian product (session_liq = 120) ────

def test_session_liquidity_sweep_combos(config):
    """Session liquidity sweep generates 120 combos (6 × 4 × 5)."""
    combos = extract_sweep_combos(config, "session_liquidity")
    assert len(combos) == 120
    # Each combo should have all three params
    for combo in combos:
        fgm = combo["four_gate_model"]
        assert "efficiency_threshold" in fgm
        assert "mid_cross_min" in fgm
        assert "balance_score_min" in fgm


# ─── VAL-PARAM-007: Selective param sweep ─────────────────────────────────

def test_displacement_selective_sweep(config):
    """Selective sweep of ltf.atr_multiplier produces 7 combos."""
    combos = extract_sweep_combos(
        config, "displacement", params=["ltf.atr_multiplier"]
    )
    assert len(combos) == 7
    # All other params should be at locked values
    locked = extract_params(config, "displacement", mode="locked")
    for combo in combos:
        assert combo["ltf"]["body_ratio"] == locked["ltf"]["body_ratio"]
        assert combo["ltf"]["close_gate"] == locked["ltf"]["close_gate"]
        assert combo["htf"]["atr_multiplier"] == locked["htf"]["atr_multiplier"]
    # The swept param should vary
    atr_values = [c["ltf"]["atr_multiplier"] for c in combos]
    assert atr_values == [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]


# ─── VAL-PARAM-008: Unknown primitive raises error ───────────────────────

def test_unknown_primitive_raises_error(config):
    """Unknown primitive raises ParamExtractionError with descriptive message."""
    with pytest.raises(ParamExtractionError, match="nonexistent"):
        extract_params(config, "nonexistent", mode="locked")


def test_unknown_primitive_sweep_raises_error(config):
    """Unknown primitive in sweep mode raises ParamExtractionError."""
    with pytest.raises(ParamExtractionError, match="nonexistent"):
        extract_params(config, "nonexistent", mode="sweep")


# ─── VAL-PARAM-010: Null locked value handling ───────────────────────────

def test_bpr_null_locked_value(config):
    """BPR min_overlap_pips locked is null, sweep returns range."""
    # Locked mode: hardcoded returns empty dict for bpr
    locked = extract_params(config, "bpr", mode="locked")
    assert locked == {}

    # Sweep mode: returns sweep_range for min_overlap_pips
    sweep = extract_params(config, "bpr", mode="sweep")
    assert sweep["min_overlap_pips"] == [0.0, 0.5, 1.0, 2.0]


# ─── VAL-PARAM-012: All primitives valid in both modes ───────────────────

@pytest.mark.parametrize("primitive", ALL_PRIMITIVES)
def test_all_primitives_locked_mode(config, primitive):
    """All 14 primitives return dicts in locked mode without error."""
    result = extract_params(config, primitive, mode="locked")
    assert isinstance(result, dict)


@pytest.mark.parametrize("primitive", ALL_PRIMITIVES)
def test_all_primitives_sweep_mode(config, primitive):
    """All 14 primitives return dicts in sweep mode without error."""
    result = extract_params(config, primitive, mode="sweep")
    assert isinstance(result, dict)


# ─── VAL-PARAM-011: CascadeEngine round-trip produces identical detections

@pytest.fixture(scope="module")
def bars_by_tf():
    """Load and aggregate 5-day CSV dataset."""
    from ra.data.csv_loader import load_csv
    from ra.data.session_tagger import tag_sessions
    from ra.data.tf_aggregator import aggregate

    bars_1m = load_csv("data/eurusd_1m_2024-01-07_to_2024-01-12.csv")
    bars_1m = tag_sessions(bars_1m)
    bars_by_tf = {"1m": bars_1m}
    for tf in ["5m", "15m"]:
        bars_by_tf[tf] = aggregate(bars_1m, tf)
    return bars_by_tf


def test_cascade_roundtrip_identical_detections(config, bars_by_tf):
    """CascadeEngine with new extraction produces identical 9784 detections."""
    registry = build_default_registry()
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }

    # Run with OLD extraction
    engine_old = CascadeEngine(registry, dep_graph)
    old_params = extract_locked_params_for_cascade(config)
    results_old = engine_old.run(bars_by_tf, old_params)

    # Run with NEW extraction
    engine_new = CascadeEngine(registry, dep_graph)
    new_params = {}
    for prim in ALL_PRIMITIVES:
        new_params[prim] = extract_params(config, prim, mode="locked")
    results_new = engine_new.run(bars_by_tf, new_params)

    # Compare total detection counts
    def count_detections(results):
        total = 0
        for prim, tf_results in results.items():
            for tf, det_result in tf_results.items():
                total += len(det_result.detections)
        return total

    old_total = count_detections(results_old)
    new_total = count_detections(results_new)
    assert old_total == new_total == 9784, (
        f"Detection count mismatch: old={old_total}, new={new_total}, expected=9784"
    )

    # Compare per-primitive per-TF counts
    for prim in results_old:
        for tf in results_old[prim]:
            old_count = len(results_old[prim][tf].detections)
            new_count = len(results_new[prim][tf].detections)
            assert old_count == new_count, (
                f"Detection count mismatch for {prim}/{tf}: "
                f"old={old_count}, new={new_count}"
            )


# ─── Sweep combos edge cases ─────────────────────────────────────────────

def test_sweep_combos_no_sweep_range_primitive(config):
    """Primitives without sweep_range return empty combos or single locked combo."""
    combos = extract_sweep_combos(config, "reference_levels")
    # reference_levels has no sweep_range, so it should return a single combo
    # with locked values
    assert len(combos) == 1
    assert combos[0] == extract_params(config, "reference_levels", mode="locked")


def test_sweep_combos_selective_multiple_params(config):
    """Selective sweep with two params generates correct Cartesian product."""
    combos = extract_sweep_combos(
        config, "displacement",
        params=["ltf.atr_multiplier", "ltf.body_ratio"]
    )
    # 7 atr_multiplier × 7 body_ratio = 49
    assert len(combos) == 49


def test_liquidity_sweep_rejection_wick_combos(config):
    """Liquidity sweep generates 5 combos for rejection_wick_pct."""
    combos = extract_sweep_combos(config, "liquidity_sweep")
    assert len(combos) == 5
    # Each combo should have rejection_wick_pct as a {locked: value} wrapper
    for combo in combos:
        assert isinstance(combo["rejection_wick_pct"], dict)
        assert "locked" in combo["rejection_wick_pct"]


def test_unknown_primitive_sweep_combos_raises(config):
    """extract_sweep_combos with unknown primitive raises error."""
    with pytest.raises(ParamExtractionError, match="nonexistent"):
        extract_sweep_combos(config, "nonexistent")
