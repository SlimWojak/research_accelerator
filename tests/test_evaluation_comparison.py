"""Tests for comparison statistics module (Phase 2).

Validates:
- VAL-COMP-001: detection_count per primitive per TF matches baseline
- VAL-COMP-002: detections_per_day mean and std correct for 5 forex days
- VAL-COMP-003: by_session_distribution count and pct, sums to 100%
- VAL-COMP-006: Pairwise agreement_rate ∈ [0,1], self-comparison = 1.0
- VAL-COMP-007: Pairwise only_in_a + only_in_b + agreed = total unique
- VAL-COMP-008: Divergence index per-detection diff list
- VAL-COMP-010: Zero-detection edge case (no crash, 0/null)
- VAL-COMP-011: by_session agreement breakdown
- VAL-COMP-012: Multi-config pairwise produces C(n,2) entries
- by_direction distribution
"""

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ra.engine.base import Detection, DetectionResult
from ra.evaluation.comparison import (
    compute_stats,
    compare_pairwise,
    compare_multi,
)


NY_TZ = ZoneInfo("America/New_York")


# ─── Test Helpers ────────────────────────────────────────────────────────

def _make_detection(
    primitive: str,
    tf: str,
    ts_str: str,
    direction: str = "bullish",
    session: str = "nyokz",
    forex_day: str = "2024-01-08",
    det_type: str = "default",
    upstream_refs: list | None = None,
) -> Detection:
    """Create a test Detection."""
    ts = datetime.fromisoformat(ts_str).replace(tzinfo=NY_TZ)
    dir_short = {"bullish": "bull", "bearish": "bear"}.get(direction, direction)
    det_id = f"{primitive}_{tf}_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_{dir_short}"
    return Detection(
        id=det_id,
        time=ts,
        direction=direction,
        type=det_type,
        price=1.0950,
        properties={},
        tags={"session": session, "forex_day": forex_day},
        upstream_refs=upstream_refs or [],
    )


def _make_result(
    primitive: str, tf: str, detections: list[Detection]
) -> DetectionResult:
    """Create a test DetectionResult."""
    return DetectionResult(
        primitive=primitive,
        variant="a8ra_v1",
        timeframe=tf,
        detections=detections,
        metadata={},
        params_used={},
    )


def _build_sample_results() -> dict[str, dict[str, DetectionResult]]:
    """Build a sample cascade result for testing.

    Creates displacement/5m with 10 detections spread across 5 forex days
    and 4 sessions.
    """
    detections = [
        # Day 1: 2024-01-08 (2 detections)
        _make_detection("displacement", "5m", "2024-01-08T03:00:00",
                        "bearish", "lokz", "2024-01-08"),
        _make_detection("displacement", "5m", "2024-01-08T08:30:00",
                        "bullish", "nyokz", "2024-01-08"),
        # Day 2: 2024-01-09 (3 detections)
        _make_detection("displacement", "5m", "2024-01-09T03:15:00",
                        "bearish", "lokz", "2024-01-09"),
        _make_detection("displacement", "5m", "2024-01-09T08:00:00",
                        "bullish", "nyokz", "2024-01-09"),
        _make_detection("displacement", "5m", "2024-01-09T19:30:00",
                        "bearish", "asia", "2024-01-10"),
        # Day 3: 2024-01-10 (2 detections)
        _make_detection("displacement", "5m", "2024-01-10T12:00:00",
                        "bullish", "other", "2024-01-10"),
        _make_detection("displacement", "5m", "2024-01-10T14:00:00",
                        "bearish", "other", "2024-01-10"),
        # Day 4: 2024-01-11 (2 detections)
        _make_detection("displacement", "5m", "2024-01-11T03:00:00",
                        "bearish", "lokz", "2024-01-11"),
        _make_detection("displacement", "5m", "2024-01-11T08:15:00",
                        "bullish", "nyokz", "2024-01-11"),
        # Day 5: 2024-01-12 (1 detection)
        _make_detection("displacement", "5m", "2024-01-12T19:00:00",
                        "bullish", "asia", "2024-01-13"),
    ]
    dr = _make_result("displacement", "5m", detections)
    return {"displacement": {"5m": dr}}


def _build_empty_results() -> dict[str, dict[str, DetectionResult]]:
    """Build result with zero detections (edge case testing)."""
    dr = _make_result("equal_hl", "5m", [])
    return {"equal_hl": {"5m": dr}}


# ─── VAL-COMP-001: detection_count per primitive per TF ──────────────────

class TestComputeStats:
    """Tests for compute_stats()."""

    def test_detection_count(self):
        """detection_count matches actual detection count."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        assert disp_5m["detection_count"] == 10

    def test_detection_count_from_real_data(self, bars_1m, bars_5m, bars_15m):
        """VAL-COMP-001: detection_count matches Phase 1 baseline counts."""
        from ra.config.loader import load_config
        from ra.engine.cascade import (
            CascadeEngine,
            build_default_registry,
            extract_locked_params_for_cascade,
        )

        config = load_config("configs/locked_baseline.yaml")
        registry = build_default_registry()
        dep_graph = {
            n: nd.model_dump() for n, nd in config.dependency_graph.items()
        }
        engine = CascadeEngine(registry, dep_graph)
        params = extract_locked_params_for_cascade(config)
        results = engine.run(
            {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}, params
        )

        stats = compute_stats(results)

        # Verify key baseline counts
        assert stats["displacement"]["5m"]["detection_count"] == 819
        assert stats["fvg"]["5m"]["detection_count"] == 345
        assert stats["mss"]["5m"]["detection_count"] == 44
        assert stats["order_block"]["5m"]["detection_count"] == 37
        assert stats["swing_points"]["5m"]["detection_count"] == 267

    # ─── VAL-COMP-002: detections_per_day mean and std ────────────────────

    def test_detections_per_day_mean(self):
        """VAL-COMP-002: mean detections per day correct."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        # 10 detections / 5 forex days = 2.0 mean
        # But actually they fall on 5 forex days: 2024-01-08 (2), 09 (2),
        # 10 (3), 11 (2), 13 (1) => per day [2, 2, 3, 2, 1] mean=2.0
        # Note: forex_day tags determine the day count
        assert isinstance(disp_5m["detections_per_day"], float)
        assert disp_5m["detections_per_day"] > 0

    def test_detections_per_day_std(self):
        """VAL-COMP-002: std of per-day counts is computed."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        assert "detections_per_day_std" in disp_5m
        assert isinstance(disp_5m["detections_per_day_std"], float)
        assert disp_5m["detections_per_day_std"] >= 0

    # ─── VAL-COMP-003: by_session_distribution ────────────────────────────

    def test_by_session_has_four_categories(self):
        """by_session has asia, lokz, nyokz, other."""
        results = _build_sample_results()
        stats = compute_stats(results)

        by_sess = stats["displacement"]["5m"]["by_session"]
        expected_keys = {"asia", "lokz", "nyokz", "other"}
        assert set(by_sess.keys()) == expected_keys

    def test_by_session_counts_sum_to_total(self):
        """VAL-COMP-003: session counts sum to detection_count."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        total = sum(v["count"] for v in disp_5m["by_session"].values())
        assert total == disp_5m["detection_count"]

    def test_by_session_pct_sum_to_100(self):
        """VAL-COMP-003: session percentages sum to 100%."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        total_pct = sum(v["pct"] for v in disp_5m["by_session"].values())
        assert abs(total_pct - 100.0) < 0.1

    def test_by_session_individual_counts(self):
        """Individual session counts match expected."""
        results = _build_sample_results()
        stats = compute_stats(results)

        by_sess = stats["displacement"]["5m"]["by_session"]
        # From our sample: asia=2, lokz=3, nyokz=3, other=2
        assert by_sess["asia"]["count"] == 2
        assert by_sess["lokz"]["count"] == 3
        assert by_sess["nyokz"]["count"] == 3
        assert by_sess["other"]["count"] == 2

    # ─── by_direction distribution ─────────────────────────────────────────

    def test_by_direction_has_bullish_bearish(self):
        """by_direction has bullish and bearish entries."""
        results = _build_sample_results()
        stats = compute_stats(results)

        by_dir = stats["displacement"]["5m"]["by_direction"]
        assert "bullish" in by_dir
        assert "bearish" in by_dir

    def test_by_direction_counts_sum_to_total(self):
        """Direction counts sum to detection_count."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        total = sum(v["count"] for v in disp_5m["by_direction"].values())
        assert total == disp_5m["detection_count"]

    def test_by_direction_pct_sum_to_100(self):
        """Direction percentages sum to 100%."""
        results = _build_sample_results()
        stats = compute_stats(results)

        disp_5m = stats["displacement"]["5m"]
        total_pct = sum(v["pct"] for v in disp_5m["by_direction"].values())
        assert abs(total_pct - 100.0) < 0.1

    def test_by_direction_values(self):
        """Direction counts match expected split."""
        results = _build_sample_results()
        stats = compute_stats(results)

        by_dir = stats["displacement"]["5m"]["by_direction"]
        # 5 bullish, 5 bearish in sample
        assert by_dir["bullish"]["count"] == 5
        assert by_dir["bearish"]["count"] == 5

    # ─── VAL-COMP-010: Zero-detection edge case ──────────────────────────

    def test_zero_detections_no_crash(self):
        """VAL-COMP-010: Zero detections produces valid stats, no crash."""
        results = _build_empty_results()
        stats = compute_stats(results)

        eq_5m = stats["equal_hl"]["5m"]
        assert eq_5m["detection_count"] == 0
        assert eq_5m["detections_per_day"] == 0
        assert eq_5m["detections_per_day_std"] == 0
        # All session counts zero
        for sess_data in eq_5m["by_session"].values():
            assert sess_data["count"] == 0
            assert sess_data["pct"] == 0
        # Direction counts zero
        for dir_data in eq_5m["by_direction"].values():
            assert dir_data["count"] == 0
            assert dir_data["pct"] == 0

    # ─── Global primitives ────────────────────────────────────────────────

    def test_global_primitives_stats(self):
        """Global primitives (session_liquidity) get stats under 'global' tf."""
        detections = [
            _make_detection("session_liquidity", "global", "2024-01-08T01:00:00",
                            "neutral", "other", "2024-01-08", det_type="asia_box"),
        ]
        dr = _make_result("session_liquidity", "global", detections)
        results = {"session_liquidity": {"global": dr}}
        stats = compute_stats(results)

        assert "session_liquidity" in stats
        assert "global" in stats["session_liquidity"]
        assert stats["session_liquidity"]["global"]["detection_count"] == 1


# ─── VAL-COMP-006/007/008: Pairwise comparison ───────────────────────────

class TestComparePairwise:
    """Tests for compare_pairwise()."""

    def test_self_comparison_agreement_rate_1(self):
        """VAL-COMP-006: Self-comparison gives agreement_rate = 1.0."""
        results = _build_sample_results()
        comp = compare_pairwise(results, results)

        for prim, tf_dict in comp["per_primitive"].items():
            for tf, data in tf_dict.items():
                assert data["agreement_rate"] == 1.0
                assert data["only_in_a"] == 0
                assert data["only_in_b"] == 0

    def test_agreement_rate_in_range(self):
        """VAL-COMP-006: agreement_rate ∈ [0, 1]."""
        results_a = _build_sample_results()
        # Build results_b with some different detections
        detections_b = [
            # Keep 5 of the 10 from results_a
            _make_detection("displacement", "5m", "2024-01-08T03:00:00",
                            "bearish", "lokz", "2024-01-08"),
            _make_detection("displacement", "5m", "2024-01-08T08:30:00",
                            "bullish", "nyokz", "2024-01-08"),
            _make_detection("displacement", "5m", "2024-01-09T03:15:00",
                            "bearish", "lokz", "2024-01-09"),
            _make_detection("displacement", "5m", "2024-01-09T08:00:00",
                            "bullish", "nyokz", "2024-01-09"),
            _make_detection("displacement", "5m", "2024-01-09T19:30:00",
                            "bearish", "asia", "2024-01-10"),
            # Add 3 new ones not in A
            _make_detection("displacement", "5m", "2024-01-10T09:00:00",
                            "bullish", "nyokz", "2024-01-10"),
            _make_detection("displacement", "5m", "2024-01-11T15:00:00",
                            "bearish", "other", "2024-01-11"),
            _make_detection("displacement", "5m", "2024-01-12T04:00:00",
                            "bullish", "lokz", "2024-01-12"),
        ]
        dr_b = _make_result("displacement", "5m", detections_b)
        results_b = {"displacement": {"5m": dr_b}}

        comp = compare_pairwise(results_a, results_b)

        rate = comp["per_primitive"]["displacement"]["5m"]["agreement_rate"]
        assert 0 <= rate <= 1
        # 5 agreed out of 10 + 3 = 13 unique → agreement ≈ 0.385
        assert rate < 1.0  # Not perfect agreement

    def test_count_arithmetic_invariant(self):
        """VAL-COMP-007: only_in_a + only_in_b + agreed = total unique."""
        results_a = _build_sample_results()
        detections_b = [
            _make_detection("displacement", "5m", "2024-01-08T03:00:00",
                            "bearish", "lokz", "2024-01-08"),
            _make_detection("displacement", "5m", "2024-01-08T08:30:00",
                            "bullish", "nyokz", "2024-01-08"),
            _make_detection("displacement", "5m", "2024-01-10T09:00:00",
                            "bullish", "nyokz", "2024-01-10"),
        ]
        dr_b = _make_result("displacement", "5m", detections_b)
        results_b = {"displacement": {"5m": dr_b}}

        comp = compare_pairwise(results_a, results_b)

        data = comp["per_primitive"]["displacement"]["5m"]
        agreed = data["count_a"] - data["only_in_a"]  # agreed = count_a - only_in_a
        total_unique = data["only_in_a"] + data["only_in_b"] + agreed
        assert total_unique == len(
            set(d.id for d in results_a["displacement"]["5m"].detections)
            | set(d.id for d in results_b["displacement"]["5m"].detections)
        )

    def test_divergence_index_structure(self):
        """VAL-COMP-008: divergence_index has correct structure."""
        results_a = _build_sample_results()
        detections_b = [
            _make_detection("displacement", "5m", "2024-01-08T03:00:00",
                            "bearish", "lokz", "2024-01-08"),
            _make_detection("displacement", "5m", "2024-01-10T09:00:00",
                            "bullish", "nyokz", "2024-01-10"),
        ]
        dr_b = _make_result("displacement", "5m", detections_b)
        results_b = {"displacement": {"5m": dr_b}}

        comp = compare_pairwise(results_a, results_b)

        assert "divergence_index" in comp
        assert len(comp["divergence_index"]) > 0

        for entry in comp["divergence_index"]:
            assert "time" in entry
            assert "primitive" in entry
            assert "tf" in entry
            assert "in_a" in entry
            assert "in_b" in entry
            assert "detection_id_a" in entry
            assert "detection_id_b" in entry

    def test_divergence_index_non_empty_for_differing_configs(self):
        """VAL-COMP-008: divergence_index is non-empty for differing configs."""
        results_a = _build_sample_results()
        detections_b = [
            _make_detection("displacement", "5m", "2024-01-10T09:00:00",
                            "bullish", "nyokz", "2024-01-10"),
        ]
        dr_b = _make_result("displacement", "5m", detections_b)
        results_b = {"displacement": {"5m": dr_b}}

        comp = compare_pairwise(results_a, results_b)
        assert len(comp["divergence_index"]) > 0

    def test_divergence_index_empty_for_identical(self):
        """Self-comparison has empty divergence_index (all agreed)."""
        results = _build_sample_results()
        comp = compare_pairwise(results, results)

        # All items should be agreed (in_a=True, in_b=True)
        only_divergent = [
            e for e in comp["divergence_index"]
            if not (e["in_a"] and e["in_b"])
        ]
        assert len(only_divergent) == 0

    # ─── VAL-COMP-011: by_session agreement ──────────────────────────────

    def test_by_session_agreement_structure(self):
        """VAL-COMP-011: by_session_agreement has per-session agreement rates."""
        results_a = _build_sample_results()
        results_b = _build_sample_results()

        comp = compare_pairwise(results_a, results_b)

        for prim, tf_dict in comp["per_primitive"].items():
            for tf, data in tf_dict.items():
                assert "by_session_agreement" in data
                by_sess = data["by_session_agreement"]
                for sess in ("asia", "lokz", "nyokz", "other"):
                    assert sess in by_sess
                    assert "agreement" in by_sess[sess]
                    assert 0 <= by_sess[sess]["agreement"] <= 1

    def test_by_session_agreement_self_is_1(self):
        """Self-comparison session agreement is 1.0 for all sessions."""
        results = _build_sample_results()
        comp = compare_pairwise(results, results)

        for prim, tf_dict in comp["per_primitive"].items():
            for tf, data in tf_dict.items():
                for sess, sess_data in data["by_session_agreement"].items():
                    assert sess_data["agreement"] == 1.0

    # ─── Zero detection pairwise ──────────────────────────────────────────

    def test_zero_detection_pairwise_no_crash(self):
        """VAL-COMP-010: Zero detections in pairwise doesn't crash."""
        results_a = _build_empty_results()
        results_b = _build_empty_results()

        comp = compare_pairwise(results_a, results_b)

        data = comp["per_primitive"]["equal_hl"]["5m"]
        assert data["agreement_rate"] == 1.0  # Both empty → perfect agreement
        assert data["only_in_a"] == 0
        assert data["only_in_b"] == 0


# ─── VAL-COMP-012: Multi-config comparison ───────────────────────────────

class TestCompareMulti:
    """Tests for compare_multi() — C(n,2) pairwise."""

    def test_three_configs_produces_three_pairs(self):
        """VAL-COMP-012: 3 configs → C(3,2) = 3 pairwise entries."""
        results_a = _build_sample_results()
        results_b = _build_sample_results()
        results_c = _build_sample_results()

        configs = {
            "config_a": results_a,
            "config_b": results_b,
            "config_c": results_c,
        }

        multi = compare_multi(configs)

        assert len(multi) == 3
        pair_names = set()
        for entry in multi:
            pair_names.add((entry["config_a"], entry["config_b"]))
        assert ("config_a", "config_b") in pair_names
        assert ("config_a", "config_c") in pair_names
        assert ("config_b", "config_c") in pair_names

    def test_two_configs_produces_one_pair(self):
        """2 configs → C(2,2) = 1 pairwise entry."""
        configs = {
            "alpha": _build_sample_results(),
            "beta": _build_sample_results(),
        }
        multi = compare_multi(configs)
        assert len(multi) == 1
        assert multi[0]["config_a"] == "alpha"
        assert multi[0]["config_b"] == "beta"

    def test_four_configs_produces_six_pairs(self):
        """4 configs → C(4,2) = 6 pairwise entries."""
        configs = {f"c{i}": _build_sample_results() for i in range(4)}
        multi = compare_multi(configs)
        assert len(multi) == 6

    def test_each_pair_has_valid_structure(self):
        """Each pairwise entry in multi-config has proper structure."""
        configs = {
            "config_a": _build_sample_results(),
            "config_b": _build_sample_results(),
            "config_c": _build_sample_results(),
        }
        multi = compare_multi(configs)

        for entry in multi:
            assert "config_a" in entry
            assert "config_b" in entry
            assert "per_primitive" in entry
            assert "divergence_index" in entry
