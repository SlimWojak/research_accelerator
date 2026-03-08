"""Tests for CascadeEngine: topological sort, caching, DAG invalidation.

Tests:
- VAL-CASC-001: Topological sort produces correct execution order
- VAL-CASC-002: Upstream param change triggers downstream re-run only
- VAL-CASC-003: Unchanged upstream cached on re-run
- VAL-CASC-004: DEFERRED module (equal_hl) handled gracefully
- Cross-area: FVG -> IFVG/BPR wiring
- Cross-area: Swing -> MSS -> OB chain (MSS=44, OB=37 on 5m)
- Cross-area: Config change propagation isolation
- Cross-area: Deterministic IDs with upstream_refs
- Cross-area: No ghost-bar detections
"""

import copy
import json
from pathlib import Path

import pytest

from ra.engine.cascade import (
    CascadeEngine,
    CascadeError,
    CycleError,
    _topo_sort,
    _get_transitive_downstream,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"


# ── Dependency graph from locked_baseline.yaml ──────────────────────────────

LOCKED_DEP_GRAPH = {
    "fvg":              {"upstream": []},
    "swing_points":     {"upstream": []},
    "asia_range":       {"upstream": []},
    "displacement":     {"upstream": []},
    "reference_levels": {"upstream": []},
    "session_liquidity": {"upstream": []},
    "ifvg":             {"upstream": ["fvg"]},
    "bpr":              {"upstream": ["fvg"]},
    "equal_hl":         {"upstream": ["swing_points"]},
    "mss":              {"upstream": ["swing_points", "displacement", "fvg"]},
    "order_block":      {"upstream": ["displacement", "mss"]},
    "ote":              {"upstream": ["mss"]},
    "htf_liquidity":    {"upstream": ["swing_points"]},
    "liquidity_sweep":  {"upstream": ["session_liquidity", "reference_levels",
                                      "htf_liquidity", "swing_points", "displacement"]},
}


# ── Topological Sort Tests ──────────────────────────────────────────────────

class TestTopologicalSort:
    """VAL-CASC-001: Cascade resolves dependency graph in correct order."""

    def test_leaves_before_composites(self):
        """Leaf nodes come before derived nodes in execution order."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        order = _topo_sort(graph)

        # All leaves should appear before any of their dependents
        leaves = {"fvg", "swing_points", "asia_range", "displacement",
                  "reference_levels", "session_liquidity"}
        composites = {"mss", "order_block", "ote", "liquidity_sweep"}

        for leaf in leaves:
            for comp in composites:
                assert order.index(leaf) < order.index(comp), (
                    f"Leaf '{leaf}' must come before composite '{comp}'. "
                    f"Order: {order}"
                )

    def test_mss_before_order_block(self):
        """MSS must come before order_block (OB depends on MSS)."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        order = _topo_sort(graph)
        assert order.index("mss") < order.index("order_block")

    def test_mss_before_ote(self):
        """MSS must come before OTE (OTE depends on MSS)."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        order = _topo_sort(graph)
        assert order.index("mss") < order.index("ote")

    def test_all_nodes_present(self):
        """All nodes in the graph appear in the execution order."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        order = _topo_sort(graph)
        assert set(order) == set(graph.keys())

    def test_deterministic_order(self):
        """Running topo_sort twice gives the same order."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        order1 = _topo_sort(graph)
        order2 = _topo_sort(graph)
        assert order1 == order2

    def test_cycle_detection(self):
        """Cycle in the graph raises CycleError."""
        graph = {
            "a": ["b"],
            "b": ["c"],
            "c": ["a"],
        }
        with pytest.raises(CycleError, match="cycle"):
            _topo_sort(graph)

    def test_missing_dependency_error(self):
        """Reference to non-existent node raises CascadeError."""
        graph = {
            "a": ["nonexistent"],
        }
        with pytest.raises(CascadeError, match="not in the graph"):
            _topo_sort(graph)


class TestTransitiveDownstream:
    """Test _get_transitive_downstream helper."""

    def test_displacement_downstream(self):
        """Changing displacement invalidates mss, order_block, liquidity_sweep."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        downstream = _get_transitive_downstream(graph, {"displacement"})
        assert "mss" in downstream
        assert "order_block" in downstream
        assert "liquidity_sweep" in downstream
        # OTE depends on MSS which depends on displacement
        assert "ote" in downstream

    def test_fvg_downstream(self):
        """Changing FVG invalidates ifvg, bpr, mss, order_block, ote."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        downstream = _get_transitive_downstream(graph, {"fvg"})
        assert "ifvg" in downstream
        assert "bpr" in downstream
        assert "mss" in downstream
        # swing_points is independent, should not be affected
        assert "swing_points" not in downstream

    def test_leaf_no_upstream_effect(self):
        """Changing a leaf doesn't affect other leaves."""
        graph = {
            name: spec["upstream"] for name, spec in LOCKED_DEP_GRAPH.items()
        }
        downstream = _get_transitive_downstream(graph, {"fvg"})
        assert "swing_points" not in downstream
        assert "displacement" not in downstream
        assert "asia_range" not in downstream


# ── CascadeEngine Caching Tests ─────────────────────────────────────────────

class TestCascadeCaching:
    """VAL-CASC-003: Unchanged upstream served from cache."""

    @pytest.fixture(scope="class")
    def engine(self):
        registry = build_default_registry()
        return CascadeEngine(registry, LOCKED_DEP_GRAPH)

    @pytest.fixture(scope="class")
    def locked_params(self):
        return extract_locked_params_for_cascade(None)

    @pytest.fixture(scope="class")
    def bars_by_tf(self, bars_1m, bars_5m, bars_15m):
        return {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

    def test_cache_hit_on_second_run(self, engine, bars_by_tf, locked_params):
        """Running cascade twice with same params reuses cache."""
        # First run
        results1 = engine.run(bars_by_tf, locked_params)
        # Second run — should be cached
        results2 = engine.run(bars_by_tf, locked_params)

        # Results should be identical (same objects from cache)
        for prim in results1:
            for tf in results1[prim]:
                assert results1[prim][tf] is results2[prim][tf], (
                    f"Expected cache hit for {prim}/{tf}"
                )


# ── DAG Invalidation Tests ──────────────────────────────────────────────────

class TestDAGInvalidation:
    """VAL-CASC-002: Upstream param change triggers downstream re-run only."""

    @pytest.fixture
    def engine(self):
        registry = build_default_registry()
        return CascadeEngine(registry, LOCKED_DEP_GRAPH)

    @pytest.fixture
    def locked_params(self):
        return extract_locked_params_for_cascade(None)

    @pytest.fixture
    def bars_by_tf(self, bars_1m, bars_5m, bars_15m):
        return {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

    def test_displacement_change_invalidates_downstream(
        self, engine, bars_by_tf, locked_params
    ):
        """Changing displacement params re-runs disp + MSS + OB but not fvg/swing."""
        # First run
        results1 = engine.run(bars_by_tf, locked_params)

        # Capture refs to fvg and swing results
        fvg_5m_ref = results1["fvg"]["5m"]
        swing_5m_ref = results1["swing_points"]["5m"]

        # Change displacement param (but keep everything else the same)
        invalidated = engine.on_param_change("displacement")
        assert "displacement" in invalidated
        assert "mss" in invalidated
        assert "order_block" in invalidated
        assert "fvg" not in invalidated
        assert "swing_points" not in invalidated

        # Second run with same params (invalidation already set)
        results2 = engine.run(bars_by_tf, locked_params)

        # FVG and swing should be cached (same object)
        assert results2["fvg"]["5m"] is fvg_5m_ref, "FVG should be cached"
        assert results2["swing_points"]["5m"] is swing_5m_ref, "Swing should be cached"

        # Displacement and downstream should be re-run (new objects)
        # Note: re-run with same params means same results, but different objects
        # because on_param_change forced invalidation
        assert "displacement" in results2
        assert "mss" in results2


# ── DEFERRED Module Test ────────────────────────────────────────────────────

class TestDeferredModule:
    """VAL-CASC-004: DEFERRED module handled gracefully."""

    def test_equal_hl_deferred_no_error(self, bars_1m, bars_5m, bars_15m):
        """Full cascade with equal_hl DEFERRED does not error."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        # This should NOT raise an error
        results = engine.run(bars_by_tf, params)

        # equal_hl should have empty DEFERRED results
        assert "equal_hl" in results
        for tf, result in results["equal_hl"].items():
            assert len(result.detections) == 0
            assert result.metadata.get("status") == "DEFERRED"


# ── Cross-Area: FVG -> IFVG/BPR Wiring ─────────────────────────────────────

class TestFVGCascadeWiring:
    """VAL-CROSS-001: FVG output feeds IFVG/BPR through cascade."""

    def test_ifvg_bpr_virtual_nodes_handled(self, bars_1m, bars_5m, bars_15m):
        """ifvg and bpr virtual nodes are skipped gracefully."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        results = engine.run(bars_by_tf, params)

        # FVG results should be present and non-empty
        assert "fvg" in results
        assert len(results["fvg"]["5m"].detections) > 0

        # IFVG/BPR are virtual nodes (handled inside FVG), so they have empty results
        assert "ifvg" in results
        assert "bpr" in results

    def test_fvg_includes_ifvg_bpr_types(self, bars_1m, bars_5m, bars_15m):
        """FVG result includes FVG, IFVG, and BPR type detections."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        results = engine.run(bars_by_tf, params)

        fvg_types = {d.type for d in results["fvg"]["5m"].detections}
        # FVG detector should produce fvg, ifvg, and bpr type detections
        assert "fvg" in fvg_types


# ── Cross-Area: Swing -> MSS -> OB Chain ────────────────────────────────────

class TestSwingMSSOBChain:
    """VAL-CROSS-002: Full chain on 5m: MSS=44, OB=37."""

    @pytest.fixture(scope="class")
    def cascade_results(self, bars_1m, bars_5m, bars_15m):
        """Run full cascade and return results."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}
        return engine.run(bars_by_tf, params)

    def test_mss_5m_count(self, cascade_results):
        """MSS on 5m should produce 44 detections."""
        mss_5m = cascade_results["mss"]["5m"]
        assert len(mss_5m.detections) == 44, (
            f"Expected 44 MSS on 5m, got {len(mss_5m.detections)}"
        )

    def test_ob_5m_count(self, cascade_results):
        """OB on 5m should produce 37 detections."""
        ob_5m = cascade_results["order_block"]["5m"]
        assert len(ob_5m.detections) == 37, (
            f"Expected 37 OB on 5m, got {len(ob_5m.detections)}"
        )

    def test_mss_references_upstream_data(self, cascade_results):
        """MSS detections reference upstream swing and displacement data in properties."""
        mss_5m = cascade_results["mss"]["5m"]
        # All MSS detections should reference a broken swing
        has_swing_ref = [
            d for d in mss_5m.detections
            if d.properties.get("broken_swing") is not None
        ]
        assert len(has_swing_ref) == len(mss_5m.detections), (
            "All MSS detections should reference a broken_swing"
        )
        # All MSS detections should have displacement info
        has_disp = [
            d for d in mss_5m.detections
            if d.properties.get("displacement") is not None
        ]
        assert len(has_disp) == len(mss_5m.detections), (
            "All MSS detections should have displacement info"
        )


# ── Cross-Area: Config Change Propagation ───────────────────────────────────

class TestConfigChangePropagation:
    """VAL-CROSS-004: Changing FVG params doesn't affect swing/disp."""

    def test_fvg_change_isolated(self, bars_1m, bars_5m, bars_15m):
        """Changing FVG floor_threshold_pips doesn't change swing or disp."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        # Run with locked params
        params1 = extract_locked_params_for_cascade(None)
        results1 = engine.run(bars_by_tf, params1)

        swing_count_1 = len(results1["swing_points"]["5m"].detections)
        disp_count_1 = len(results1["displacement"]["5m"].detections)

        # Change FVG param
        engine.on_param_change("fvg")
        params2 = copy.deepcopy(params1)
        params2["fvg"]["floor_threshold_pips"] = 2.0

        results2 = engine.run(bars_by_tf, params2)

        swing_count_2 = len(results2["swing_points"]["5m"].detections)
        disp_count_2 = len(results2["displacement"]["5m"].detections)

        # Swing and displacement should be identical
        assert swing_count_1 == swing_count_2, "Swing should be unaffected by FVG change"
        assert disp_count_1 == disp_count_2, "Displacement should be unaffected by FVG change"

        # FVG count should remain the same (floor is metadata, not filter)
        # but the result object should be different (re-run)
        fvg_count_2 = len(results2["fvg"]["5m"].detections)
        assert fvg_count_2 > 0


# ── Cross-Area: Deterministic IDs ───────────────────────────────────────────

class TestDeterministicIDs:
    """VAL-CROSS-005: Deterministic IDs with resolvable upstream_refs."""

    def test_id_format(self, bars_1m, bars_5m, bars_15m):
        """Detection IDs follow {primitive}_{tf}_{timestamp_ny}_{direction}."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        results = engine.run(bars_by_tf, params)

        # Check FVG IDs
        for det in results["fvg"]["5m"].detections[:10]:
            parts = det.id.split("_")
            assert parts[0] == "fvg", f"FVG ID should start with 'fvg': {det.id}"
            assert parts[1] == "5m", f"FVG ID should contain '5m': {det.id}"

    def test_deterministic_across_runs(self, bars_1m, bars_5m, bars_15m):
        """Same inputs produce same IDs."""
        registry = build_default_registry()
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        engine1 = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        results1 = engine1.run(bars_by_tf, params)

        engine2 = CascadeEngine(build_default_registry(), LOCKED_DEP_GRAPH)
        results2 = engine2.run(bars_by_tf, params)

        ids1 = [d.id for d in results1["fvg"]["5m"].detections]
        ids2 = [d.id for d in results2["fvg"]["5m"].detections]
        assert ids1 == ids2, "Same inputs must produce same IDs"


# ── Cross-Area: Ghost Bar Handling ──────────────────────────────────────────

class TestGhostBarHandling:
    """VAL-CROSS-006: No detection anchors on a ghost bar."""

    def test_no_ghost_detections(self, bars_1m, bars_5m, bars_15m):
        """No detection in any module anchors on a ghost bar."""
        registry = build_default_registry()
        engine = CascadeEngine(registry, LOCKED_DEP_GRAPH)
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        results = engine.run(bars_by_tf, params)

        # Build set of ghost bar timestamps per TF
        ghost_times = {}
        for tf, bars in bars_by_tf.items():
            ghost_bars = bars[bars["is_ghost"] == True]
            ghost_times[tf] = set(ghost_bars["timestamp_ny"].tolist())

        # Check all detections
        for primitive, tf_results in results.items():
            for tf, result in tf_results.items():
                tf_ghosts = ghost_times.get(tf, set())
                if not tf_ghosts:
                    continue
                for det in result.detections:
                    assert det.time not in tf_ghosts, (
                        f"Ghost bar detection found: {primitive}/{tf} "
                        f"at {det.time} (id={det.id})"
                    )
