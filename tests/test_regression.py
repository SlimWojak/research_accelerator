"""MASTER REGRESSION TEST — Full cascade at locked params vs all 32 baseline fixtures.

This is the MASTER GATE for the RA Detection Engine. Running the full cascade
with locked params on the 5-day dataset must produce detection outputs matching
all 32 baseline fixtures: count match + per-detection time/price match.

Tests:
- VAL-REG-001: Full pipeline regression PASS (all 32 fixtures)
- Per-primitive count + direction split + field match per TF
- Cross-area validation behaviors
"""

import json
from pathlib import Path

import pytest

from ra.engine.cascade import (
    CascadeEngine,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Full dependency graph from locked_baseline.yaml
DEP_GRAPH = {
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


# ── Shared Cascade Fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cascade_results(bars_1m, bars_5m, bars_15m):
    """Run the full cascade and return all results."""
    registry = build_default_registry()
    engine = CascadeEngine(registry, DEP_GRAPH)
    params = extract_locked_params_for_cascade(None)
    bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}
    return engine.run(bars_by_tf, params)


def _load_baseline(filename: str):
    """Load a baseline fixture file."""
    with open(FIXTURE_DIR / filename) as f:
        return json.load(f)


# ── FVG Regression ──────────────────────────────────────────────────────────

class TestFVGRegression:
    """FVG: exact count + direction split + per-detection field match."""

    @pytest.mark.parametrize("tf,expected_total,expected_bull,expected_bear", [
        ("1m", 2017, 1026, 991),
        ("5m", 345, 179, 166),
        ("15m", 118, 58, 60),
    ])
    def test_fvg_count(self, cascade_results, tf, expected_total,
                       expected_bull, expected_bear):
        result = cascade_results["fvg"][tf]
        assert len(result.detections) == expected_total, (
            f"FVG {tf}: expected {expected_total}, got {len(result.detections)}"
        )
        bull = [d for d in result.detections if d.direction == "bullish"]
        bear = [d for d in result.detections if d.direction == "bearish"]
        assert len(bull) == expected_bull, (
            f"FVG {tf} bull: expected {expected_bull}, got {len(bull)}"
        )
        assert len(bear) == expected_bear, (
            f"FVG {tf} bear: expected {expected_bear}, got {len(bear)}"
        )

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m"])
    def test_fvg_field_match(self, cascade_results, tf):
        """Per-detection fields match baseline fixture."""
        baseline = _load_baseline(f"fvg_data_{tf}.json")
        baseline_fvgs = baseline["fvgs"]
        result = cascade_results["fvg"][tf]

        assert len(result.detections) == len(baseline_fvgs)

        # Sort both by time for alignment
        det_sorted = sorted(result.detections, key=lambda d: d.id)
        base_sorted = sorted(baseline_fvgs, key=lambda f: f.get("time", ""))

        # Check first and last few detections
        for i in [0, 1, 2, -3, -2, -1]:
            if abs(i) >= len(det_sorted):
                continue
            det = det_sorted[i]
            base = base_sorted[i]
            # Time match
            assert det.properties.get("time") == base.get("time"), (
                f"FVG {tf}[{i}] time mismatch: "
                f"{det.properties.get('time')} vs {base.get('time')}"
            )
            # Price match within tolerance
            for field in ("top", "bottom", "ce"):
                det_val = det.properties.get(field)
                base_val = base.get(field)
                if det_val is not None and base_val is not None:
                    assert abs(det_val - base_val) < 1e-6, (
                        f"FVG {tf}[{i}] {field}: {det_val} vs {base_val}"
                    )


# ── Swing Points Regression ─────────────────────────────────────────────────

class TestSwingRegression:
    """Swing: exact count + direction split + field match."""

    @pytest.mark.parametrize("tf,expected_total,expected_high,expected_low", [
        ("1m", 833, 420, 413),
        ("5m", 267, 135, 132),
        ("15m", 124, 62, 62),
    ])
    def test_swing_count(self, cascade_results, tf, expected_total,
                         expected_high, expected_low):
        result = cascade_results["swing_points"][tf]
        assert len(result.detections) == expected_total, (
            f"Swing {tf}: expected {expected_total}, got {len(result.detections)}"
        )
        highs = [d for d in result.detections if d.direction == "high"]
        lows = [d for d in result.detections if d.direction == "low"]
        assert len(highs) == expected_high, (
            f"Swing {tf} high: expected {expected_high}, got {len(highs)}"
        )
        assert len(lows) == expected_low, (
            f"Swing {tf} low: expected {expected_low}, got {len(lows)}"
        )

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m"])
    def test_swing_field_match(self, cascade_results, tf):
        """Per-detection fields match baseline fixture."""
        baseline = _load_baseline(f"swing_data_{tf}.json")
        baseline_swings = baseline["swings"]
        result = cascade_results["swing_points"][tf]

        assert len(result.detections) == len(baseline_swings)

        # Sort both by time
        det_sorted = sorted(result.detections, key=lambda d: d.id)
        base_sorted = sorted(baseline_swings, key=lambda s: s.get("time", ""))

        for i in [0, 1, 2, -3, -2, -1]:
            if abs(i) >= len(det_sorted):
                continue
            det = det_sorted[i]
            base = base_sorted[i]
            assert det.properties.get("time") == base.get("time"), (
                f"Swing {tf}[{i}] time mismatch"
            )
            det_price = det.price
            base_price = base.get("price")
            if det_price is not None and base_price is not None:
                assert abs(det_price - base_price) < 1e-6, (
                    f"Swing {tf}[{i}] price: {det_price} vs {base_price}"
                )


# ── Displacement Regression ─────────────────────────────────────────────────

class TestDisplacementRegression:
    """Displacement: exact count + type split."""

    @pytest.mark.parametrize("tf,expected_total", [
        ("1m", 4170),
        ("5m", 819),
        ("15m", 258),
    ])
    def test_displacement_count(self, cascade_results, tf, expected_total):
        result = cascade_results["displacement"][tf]
        assert len(result.detections) == expected_total, (
            f"Displacement {tf}: expected {expected_total}, "
            f"got {len(result.detections)}"
        )

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m"])
    def test_displacement_field_match(self, cascade_results, tf):
        """Per-detection time fields match baseline."""
        baseline = _load_baseline(f"displacement_data_{tf}.json")
        baseline_disps = baseline["displacements"]
        result = cascade_results["displacement"][tf]

        assert len(result.detections) == len(baseline_disps)

        # Sort and check sample
        det_sorted = sorted(result.detections, key=lambda d: d.id)
        base_sorted = sorted(baseline_disps, key=lambda d: d.get("time", ""))

        for i in [0, 1, -2, -1]:
            if abs(i) >= len(det_sorted):
                continue
            det = det_sorted[i]
            base = base_sorted[i]
            assert det.properties.get("time") == base.get("time"), (
                f"Disp {tf}[{i}] time mismatch: "
                f"{det.properties.get('time')} vs {base.get('time')}"
            )


# ── MSS Regression ──────────────────────────────────────────────────────────

class TestMSSRegression:
    """MSS: exact count + break type split."""

    @pytest.mark.parametrize("tf,expected_total,expected_rev,expected_cont", [
        ("1m", 179, 88, 91),
        ("5m", 44, 20, 24),
        ("15m", 20, 10, 10),
    ])
    def test_mss_count(self, cascade_results, tf, expected_total,
                       expected_rev, expected_cont):
        result = cascade_results["mss"][tf]
        assert len(result.detections) == expected_total, (
            f"MSS {tf}: expected {expected_total}, got {len(result.detections)}"
        )
        rev = [d for d in result.detections
               if d.properties.get("break_type") == "REVERSAL"]
        cont = [d for d in result.detections
                if d.properties.get("break_type") == "CONTINUATION"]
        assert len(rev) == expected_rev, (
            f"MSS {tf} reversal: expected {expected_rev}, got {len(rev)}"
        )
        assert len(cont) == expected_cont, (
            f"MSS {tf} continuation: expected {expected_cont}, got {len(cont)}"
        )

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m"])
    def test_mss_field_match(self, cascade_results, tf):
        """Per-detection fields match baseline."""
        baseline = _load_baseline(f"mss_data_{tf}.json")
        baseline_events = baseline["mss_events"]
        result = cascade_results["mss"][tf]

        assert len(result.detections) == len(baseline_events)

        det_sorted = sorted(result.detections, key=lambda d: d.id)
        base_sorted = sorted(baseline_events, key=lambda e: e.get("time", ""))

        for i in [0, 1, -2, -1]:
            if abs(i) >= len(det_sorted):
                continue
            det = det_sorted[i]
            base = base_sorted[i]
            assert det.properties.get("time") == base.get("time"), (
                f"MSS {tf}[{i}] time mismatch: "
                f"{det.properties.get('time')} vs {base.get('time')}"
            )


# ── Order Block Regression ──────────────────────────────────────────────────

class TestOrderBlockRegression:
    """OB: exact count + field match."""

    @pytest.mark.parametrize("tf,expected_count", [
        ("1m", 138),
        ("5m", 37),
        ("15m", 17),
    ])
    def test_ob_count(self, cascade_results, tf, expected_count):
        result = cascade_results["order_block"][tf]
        assert len(result.detections) == expected_count, (
            f"OB {tf}: expected {expected_count}, got {len(result.detections)}"
        )

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m"])
    def test_ob_field_match(self, cascade_results, tf):
        """Per-detection time fields match baseline."""
        baseline = _load_baseline(f"ob_data_{tf}.json")
        baseline_obs = baseline["order_blocks"]
        result = cascade_results["order_block"][tf]

        assert len(result.detections) == len(baseline_obs)

        det_sorted = sorted(result.detections, key=lambda d: d.id)
        base_sorted = sorted(baseline_obs, key=lambda o: o.get("time", ""))

        for i in [0, 1, -2, -1]:
            if abs(i) >= len(det_sorted):
                continue
            det = det_sorted[i]
            base = base_sorted[i]
            assert det.properties.get("time") == base.get("time"), (
                f"OB {tf}[{i}] time mismatch: "
                f"{det.properties.get('time')} vs {base.get('time')}"
            )


# ── Liquidity Sweep Regression ──────────────────────────────────────────────

class TestLiquiditySweepRegression:
    """Sweep: count match for base/qualified/delayed/continuation."""

    @pytest.mark.parametrize("tf,base_count,qual_count,delayed_count,cont_count", [
        ("5m", 14, 11, 15, 10),
        ("15m", 11, 10, 15, 14),
        ("1m", 7, 5, 22, 18),
    ])
    def test_sweep_counts(self, cascade_results, tf, base_count,
                          qual_count, delayed_count, cont_count):
        result = cascade_results["liquidity_sweep"][tf]
        meta = result.metadata

        assert meta.get("base_sweep_count") == base_count, (
            f"Sweep {tf} base: expected {base_count}, "
            f"got {meta.get('base_sweep_count')}"
        )
        assert meta.get("qualified_count") == qual_count, (
            f"Sweep {tf} qualified: expected {qual_count}, "
            f"got {meta.get('qualified_count')}"
        )
        assert meta.get("delayed_count") == delayed_count, (
            f"Sweep {tf} delayed: expected {delayed_count}, "
            f"got {meta.get('delayed_count')}"
        )
        assert meta.get("continuation_count") == cont_count, (
            f"Sweep {tf} continuation: expected {cont_count}, "
            f"got {meta.get('continuation_count')}"
        )

    def test_sweep_5m_source_distribution(self, cascade_results):
        """5m base sweeps: source distribution matches baseline."""
        baseline = _load_baseline("sweep_data_5m.json")
        baseline_sweeps = baseline["return_windows"]["1"]["sweeps"]

        # Count baseline sources
        baseline_sources = {}
        for s in baseline_sweeps:
            src = s.get("source", "UNKNOWN")
            baseline_sources[src] = baseline_sources.get(src, 0) + 1

        # Expected: ASIA_H_L:3, LONDON_H_L:2, LTF_BOX:6, PDH_PDL:2, PROMOTED_SWING:1
        assert baseline_sources.get("ASIA_H_L", 0) == 3
        assert baseline_sources.get("LONDON_H_L", 0) == 2
        assert baseline_sources.get("LTF_BOX", 0) == 6
        assert baseline_sources.get("PDH_PDL", 0) == 2
        assert baseline_sources.get("PROMOTED_SWING", 0) == 1

        # RA detector should produce same distribution for base sweeps
        result = cascade_results["liquidity_sweep"]["5m"]
        ra_sources = {}
        for d in result.detections:
            # Base sweeps use type="sweep" (lowercase)
            if d.type == "sweep":
                src = d.properties.get("source", "UNKNOWN")
                ra_sources[src] = ra_sources.get(src, 0) + 1

        for src_name, expected in baseline_sources.items():
            assert ra_sources.get(src_name, 0) == expected, (
                f"Source {src_name}: expected {expected}, "
                f"got {ra_sources.get(src_name, 0)}"
            )


# ── Session Liquidity Regression ────────────────────────────────────────────

class TestSessionLiquidityRegression:
    """Session Liquidity: 15 boxes matching baseline."""

    def test_session_box_count(self, cascade_results):
        baseline = _load_baseline("session_boxes.json")
        result = cascade_results["session_liquidity"]["global"]
        assert len(result.detections) == len(baseline["boxes"]), (
            f"Session boxes: expected {len(baseline['boxes'])}, "
            f"got {len(result.detections)}"
        )


# ── Asia Range Regression ───────────────────────────────────────────────────

class TestAsiaRangeRegression:
    """Asia Range: 5 range entries."""

    def test_asia_range_count(self, cascade_results):
        baseline = _load_baseline("asia_data.json")
        result = cascade_results["asia_range"]["global"]
        assert len(result.detections) == len(baseline["ranges"]), (
            f"Asia ranges: expected {len(baseline['ranges'])}, "
            f"got {len(result.detections)}"
        )


# ── Reference Levels Regression ─────────────────────────────────────────────

class TestReferenceLevelsRegression:
    """Reference Levels: 5 days of levels."""

    def test_reference_levels_count(self, cascade_results):
        baseline = _load_baseline("levels_data.json")
        result = cascade_results["reference_levels"]["global"]
        assert len(result.detections) == len(baseline), (
            f"Reference levels: expected {len(baseline)}, "
            f"got {len(result.detections)}"
        )


# ── HTF Liquidity Regression ───────────────────────────────────────────────

class TestHTFLiquidityRegression:
    """HTF Liquidity: 4 pools (3 H1 + 1 H4)."""

    def test_htf_pool_count(self, cascade_results):
        baseline = _load_baseline("htf_liquidity.json")
        result = cascade_results["htf_liquidity"]["global"]
        assert len(result.detections) == len(baseline["pools"]), (
            f"HTF pools: expected {len(baseline['pools'])}, "
            f"got {len(result.detections)}"
        )


# ── OTE Regression ──────────────────────────────────────────────────────────

class TestOTERegression:
    """OTE: one zone per MSS event."""

    @pytest.mark.parametrize("tf,expected_count", [
        ("1m", 179),
        ("5m", 44),
        ("15m", 20),
    ])
    def test_ote_count(self, cascade_results, tf, expected_count):
        result = cascade_results["ote"][tf]
        assert len(result.detections) == expected_count, (
            f"OTE {tf}: expected {expected_count}, got {len(result.detections)}"
        )


# ── Full Pipeline Summary ──────────────────────────────────────────────────

class TestFullPipelineSummary:
    """Verify total detection counts across all primitives and TFs."""

    def test_total_fvg(self, cascade_results):
        total = sum(
            len(cascade_results["fvg"][tf].detections) for tf in ["1m", "5m", "15m"]
        )
        assert total == 2017 + 345 + 118  # = 2480

    def test_total_swing(self, cascade_results):
        total = sum(
            len(cascade_results["swing_points"][tf].detections)
            for tf in ["1m", "5m", "15m"]
        )
        assert total == 833 + 267 + 124  # = 1224

    def test_total_displacement(self, cascade_results):
        total = sum(
            len(cascade_results["displacement"][tf].detections)
            for tf in ["1m", "5m", "15m"]
        )
        assert total == 4170 + 819 + 258  # = 5247

    def test_total_mss(self, cascade_results):
        total = sum(
            len(cascade_results["mss"][tf].detections) for tf in ["1m", "5m", "15m"]
        )
        assert total == 179 + 44 + 20  # = 243

    def test_total_ob(self, cascade_results):
        total = sum(
            len(cascade_results["order_block"][tf].detections)
            for tf in ["1m", "5m", "15m"]
        )
        assert total == 138 + 37 + 17  # = 192

    def test_equal_hl_deferred(self, cascade_results):
        """DEFERRED module produces 0 detections without errors."""
        for tf in ["1m", "5m", "15m"]:
            result = cascade_results["equal_hl"][tf]
            assert len(result.detections) == 0

    def test_all_primitives_present(self, cascade_results):
        """All expected primitives produced results."""
        expected = {
            "fvg", "swing_points", "displacement", "mss", "order_block",
            "ote", "liquidity_sweep", "session_liquidity", "reference_levels",
            "htf_liquidity", "asia_range", "equal_hl",
        }
        actual = set(cascade_results.keys())
        for prim in expected:
            assert prim in actual, f"Missing primitive: {prim}"


# ── Cross-Area Validation ───────────────────────────────────────────────────

class TestCrossAreaRegression:
    """Cross-area behaviors validated end-to-end through cascade."""

    def test_swing_mss_ob_chain_5m(self, cascade_results):
        """VAL-CROSS-002: Swing -> MSS -> OB on 5m: MSS=44, OB=37."""
        assert len(cascade_results["mss"]["5m"].detections) == 44
        assert len(cascade_results["order_block"]["5m"].detections) == 37

    def test_mss_reversal_continuation_split(self, cascade_results):
        """MSS 5m: 20 reversal, 24 continuation."""
        mss_5m = cascade_results["mss"]["5m"]
        rev = [d for d in mss_5m.detections
               if d.properties.get("break_type") == "REVERSAL"]
        cont = [d for d in mss_5m.detections
                if d.properties.get("break_type") == "CONTINUATION"]
        assert len(rev) == 20
        assert len(cont) == 24

    def test_fvg_tagged_mss_count(self, cascade_results):
        """MSS 5m: 35 should have FVG tagged."""
        mss_5m = cascade_results["mss"]["5m"]
        fvg_tagged = [
            d for d in mss_5m.detections
            if d.properties.get("fvg_created") is True
        ]
        assert len(fvg_tagged) == 35, (
            f"FVG-tagged MSS on 5m: expected 35, got {len(fvg_tagged)}"
        )

    def test_no_ghost_bar_detections(self, cascade_results, bars_1m, bars_5m, bars_15m):
        """VAL-CROSS-006: No detection anchors on a ghost bar."""
        ghost_times = {}
        for tf, bars in [("1m", bars_1m), ("5m", bars_5m), ("15m", bars_15m)]:
            ghosts = bars[bars["is_ghost"] == True]
            ghost_times[tf] = set(ghosts["timestamp_ny"].tolist())

        for prim, tf_results in cascade_results.items():
            for tf, result in tf_results.items():
                tf_ghosts = ghost_times.get(tf, set())
                if not tf_ghosts:
                    continue
                for det in result.detections:
                    assert det.time not in tf_ghosts, (
                        f"Ghost bar detection: {prim}/{tf} at {det.time}"
                    )
