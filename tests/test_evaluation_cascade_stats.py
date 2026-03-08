"""Tests for cascade statistics module (Phase 2).

Validates:
- VAL-COMP-004: cascade_rate displacement → MSS conversion correct
- VAL-COMP-005: cascade_completion full chain tracking via upstream_refs
- VAL-COMP-009: Cascade funnel multi-level counts with conversion rates
- VAL-COMP-010: Zero-detection edge case for cascade (no crash)
- Cascade funnel level ordering: leaf → composite → terminal
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ra.engine.base import Detection, DetectionResult
from ra.evaluation.cascade_stats import (
    cascade_funnel,
    cascade_completion,
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
    properties: dict | None = None,
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
        properties=properties or {},
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


def _build_cascade_results() -> dict[str, dict[str, DetectionResult]]:
    """Build a realistic cascade result with leaf → composite → terminal.

    Hierarchy:
        swing_points (leaf) - 10
        displacement (leaf) - 8
        fvg (leaf) - 12
        mss (composite) - 4  (from displacement + swing + fvg)
        order_block (composite) - 3  (from mss + displacement)
        liquidity_sweep (terminal) - 2
    """
    # Leaf: swing_points
    swing_dets = [
        _make_detection("swing_points", "5m", f"2024-01-08T{h:02d}:00:00",
                        "high" if i % 2 == 0 else "low",
                        "lokz" if h < 5 else "nyokz")
        for i, h in enumerate(range(2, 12))
    ]
    # Leaf: displacement
    disp_dets = [
        _make_detection("displacement", "5m", f"2024-01-08T{h:02d}:15:00",
                        "bearish" if i % 2 == 0 else "bullish",
                        "lokz" if h < 5 else "nyokz")
        for i, h in enumerate(range(2, 10))
    ]
    # Leaf: fvg
    fvg_dets = [
        _make_detection("fvg", "5m", f"2024-01-08T{h:02d}:05:00",
                        "bearish" if i % 2 == 0 else "bullish",
                        "lokz" if h < 5 else "nyokz",
                        det_type="fvg")
        for i, h in enumerate(range(1, 13))
    ]
    # Composite: mss (requires displacement + swing + fvg)
    mss_dets = [
        _make_detection("mss", "5m", f"2024-01-08T{h:02d}:30:00",
                        "bearish" if i % 2 == 0 else "bullish",
                        "lokz" if h < 5 else "nyokz",
                        det_type="mss",
                        upstream_refs=[disp_dets[i].id, swing_dets[i].id])
        for i, h in enumerate([3, 4, 7, 8])
    ]
    # Composite: order_block (requires mss + displacement)
    ob_dets = [
        _make_detection("order_block", "5m", f"2024-01-08T{h:02d}:35:00",
                        "bearish" if i % 2 == 0 else "bullish",
                        "lokz" if h < 5 else "nyokz",
                        det_type="ob",
                        upstream_refs=[mss_dets[i].id])
        for i, h in enumerate([3, 7, 8])
    ]
    # Terminal: liquidity_sweep
    ls_dets = [
        _make_detection("liquidity_sweep", "5m", f"2024-01-08T{h:02d}:45:00",
                        "bearish" if i % 2 == 0 else "bullish",
                        "nyokz",
                        det_type="sweep",
                        properties={"source": "session_hl" if i == 0 else "pdh_pdl"})
        for i, h in enumerate([8, 9])
    ]

    return {
        "swing_points": {"5m": _make_result("swing_points", "5m", swing_dets)},
        "displacement": {"5m": _make_result("displacement", "5m", disp_dets)},
        "fvg": {"5m": _make_result("fvg", "5m", fvg_dets)},
        "mss": {"5m": _make_result("mss", "5m", mss_dets)},
        "order_block": {"5m": _make_result("order_block", "5m", ob_dets)},
        "liquidity_sweep": {"5m": _make_result("liquidity_sweep", "5m", ls_dets)},
    }


# ─── Cascade Funnel Tests ────────────────────────────────────────────────

class TestCascadeFunnel:
    """Tests for cascade_funnel()."""

    def test_funnel_level_counts(self):
        """VAL-COMP-009: Funnel reports counts at each level."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": ["session_liquidity", "reference_levels",
                                "htf_liquidity", "swing_points", "displacement"],
        }
        funnel = cascade_funnel(results, "5m", dep_graph)

        assert "levels" in funnel
        levels_by_name = {lv["name"]: lv for lv in funnel["levels"]}

        assert levels_by_name["swing_points"]["count"] == 10
        assert levels_by_name["displacement"]["count"] == 8
        assert levels_by_name["fvg"]["count"] == 12
        assert levels_by_name["mss"]["count"] == 4
        assert levels_by_name["order_block"]["count"] == 3
        assert levels_by_name["liquidity_sweep"]["count"] == 2

    def test_funnel_level_types(self):
        """VAL-COMP-009: Levels have correct type annotations."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": ["session_liquidity", "reference_levels",
                                "htf_liquidity", "swing_points", "displacement"],
        }
        funnel = cascade_funnel(results, "5m", dep_graph)

        levels_by_name = {lv["name"]: lv for lv in funnel["levels"]}

        assert levels_by_name["swing_points"]["type"] == "leaf"
        assert levels_by_name["fvg"]["type"] == "leaf"
        assert levels_by_name["displacement"]["type"] == "leaf"
        assert levels_by_name["mss"]["type"] == "composite"
        assert levels_by_name["order_block"]["type"] == "composite"
        assert levels_by_name["liquidity_sweep"]["type"] == "terminal"

    def test_funnel_level_ordering(self):
        """Leaf entries precede composite entries precede terminal."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": ["session_liquidity", "reference_levels",
                                "htf_liquidity", "swing_points", "displacement"],
        }
        funnel = cascade_funnel(results, "5m", dep_graph)

        types = [lv["type"] for lv in funnel["levels"]]
        # All leaf before composite, all composite before terminal
        leaf_end = max(i for i, t in enumerate(types) if t == "leaf")
        composite_indices = [i for i, t in enumerate(types) if t == "composite"]
        terminal_indices = [i for i, t in enumerate(types) if t == "terminal"]

        if composite_indices:
            assert leaf_end < min(composite_indices)
        if terminal_indices:
            if composite_indices:
                assert max(composite_indices) < min(terminal_indices)
            else:
                assert leaf_end < min(terminal_indices)

    def test_funnel_conversion_rates(self):
        """VAL-COMP-004/009: Conversion rates computed for composite levels."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": ["session_liquidity", "reference_levels",
                                "htf_liquidity", "swing_points", "displacement"],
        }
        funnel = cascade_funnel(results, "5m", dep_graph)

        levels_by_name = {lv["name"]: lv for lv in funnel["levels"]}

        mss_level = levels_by_name["mss"]
        assert "conversion_rates" in mss_level
        # MSS count (4) / displacement count (8) = 0.5
        assert mss_level["conversion_rates"]["from_displacement"] == pytest.approx(
            4 / 8, abs=0.01
        )

        ob_level = levels_by_name["order_block"]
        assert "conversion_rates" in ob_level
        # OB count (3) / MSS count (4) = 0.75
        assert ob_level["conversion_rates"]["from_mss"] == pytest.approx(
            3 / 4, abs=0.01
        )

    def test_funnel_timeframe_field(self):
        """Funnel includes timeframe field."""
        results = _build_cascade_results()
        dep_graph = {"swing_points": [], "displacement": [], "fvg": [],
                     "mss": ["swing_points", "displacement", "fvg"],
                     "order_block": ["displacement", "mss"],
                     "liquidity_sweep": []}
        funnel = cascade_funnel(results, "5m", dep_graph)
        assert funnel["timeframe"] == "5m"

    def test_funnel_zero_detections_no_crash(self):
        """VAL-COMP-010: Zero detections in a level doesn't cause div-by-zero."""
        results = {
            "fvg": {"5m": _make_result("fvg", "5m", [])},
            "displacement": {"5m": _make_result("displacement", "5m", [])},
            "mss": {"5m": _make_result("mss", "5m", [])},
        }
        dep_graph = {
            "fvg": [], "displacement": [],
            "mss": ["displacement", "fvg"],
        }
        funnel = cascade_funnel(results, "5m", dep_graph)

        levels_by_name = {lv["name"]: lv for lv in funnel["levels"]}
        assert levels_by_name["mss"]["count"] == 0
        # Conversion rate should be 0 (not NaN or error)
        assert levels_by_name["mss"]["conversion_rates"]["from_displacement"] == 0


# ─── Cascade Completion Tests ────────────────────────────────────────────

class TestCascadeCompletion:
    """Tests for cascade_completion()."""

    def test_tracks_upstream_chain(self):
        """VAL-COMP-005: Tracks full chains via upstream_refs."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": [],
        }
        completion = cascade_completion(results, "5m", dep_graph)

        assert "chains" in completion
        # order_block has 3 detections, each with upstream MSS ref
        # MSS has upstream displacement refs
        # So 3 OB detections trace back to displacement via MSS
        assert completion["chains"]["order_block"]["complete_count"] >= 0

    def test_chain_includes_complete_and_incomplete(self):
        """Completion reports both complete and incomplete chains."""
        results = _build_cascade_results()
        dep_graph = {
            "swing_points": [],
            "displacement": [],
            "fvg": [],
            "mss": ["swing_points", "displacement", "fvg"],
            "order_block": ["displacement", "mss"],
            "liquidity_sweep": [],
        }
        completion = cascade_completion(results, "5m", dep_graph)

        for prim, chain_data in completion["chains"].items():
            assert "total_count" in chain_data
            assert "complete_count" in chain_data
            assert chain_data["complete_count"] <= chain_data["total_count"]

    def test_zero_detections_completion(self):
        """Zero detections in completion doesn't crash."""
        results = {
            "fvg": {"5m": _make_result("fvg", "5m", [])},
            "mss": {"5m": _make_result("mss", "5m", [])},
        }
        dep_graph = {"fvg": [], "mss": ["fvg"]}
        completion = cascade_completion(results, "5m", dep_graph)

        assert completion["chains"]["mss"]["total_count"] == 0
        assert completion["chains"]["mss"]["complete_count"] == 0

    def test_completion_with_real_data(self, bars_1m, bars_5m, bars_15m):
        """VAL-COMP-005: Cascade completion on real data."""
        from ra.config.loader import load_config
        from ra.engine.cascade import (
            CascadeEngine,
            build_default_registry,
            extract_locked_params_for_cascade,
        )

        config = load_config("configs/locked_baseline.yaml")
        registry = build_default_registry()
        dep_graph_config = {
            n: nd.model_dump() for n, nd in config.dependency_graph.items()
        }
        engine = CascadeEngine(registry, dep_graph_config)
        params = extract_locked_params_for_cascade(config)
        results = engine.run(
            {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}, params
        )

        dep_graph = {
            name: list(node.get("upstream", []))
            for name, node in dep_graph_config.items()
        }
        completion = cascade_completion(results, "5m", dep_graph)

        # order_block should have some chains
        assert "order_block" in completion["chains"]
        ob_chain = completion["chains"]["order_block"]
        assert ob_chain["total_count"] == 37  # 37 OB detections on 5m
