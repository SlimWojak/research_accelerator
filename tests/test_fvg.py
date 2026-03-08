"""Tests for FVGDetector — regression against baseline fixtures.

Tests cover:
- Count regression per TF (1m, 5m, 15m)
- Bull/bear split
- Per-detection field matching against baseline
- IFVG state transitions (CE_TOUCHED, BOUNDARY_CLOSED)
- BPR overlap zones
- Floor threshold as metadata, not hard filter
"""

import json
from pathlib import Path

import pytest

from ra.detectors.fvg import FVGDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked FVG params from config
LOCKED_FVG_PARAMS = {
    "floor_threshold_pips": 0.5,
}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fvg_baseline_1m():
    """Load the 1m FVG baseline fixture."""
    with open(FIXTURE_DIR / "fvg_data_1m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fvg_baseline_5m():
    """Load the 5m FVG baseline fixture."""
    with open(FIXTURE_DIR / "fvg_data_5m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fvg_baseline_15m():
    """Load the 15m FVG baseline fixture."""
    with open(FIXTURE_DIR / "fvg_data_15m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def detector():
    """Create an FVGDetector instance."""
    return FVGDetector()


@pytest.fixture(scope="module")
def result_1m(detector, bars_1m):
    """Run FVG detector on 1m bars."""
    return detector.detect(bars_1m, LOCKED_FVG_PARAMS, context={"timeframe": "1m"})


@pytest.fixture(scope="module")
def result_5m(detector, bars_5m):
    """Run FVG detector on 5m bars."""
    return detector.detect(bars_5m, LOCKED_FVG_PARAMS, context={"timeframe": "5m"})


@pytest.fixture(scope="module")
def result_15m(detector, bars_15m):
    """Run FVG detector on 15m bars."""
    return detector.detect(bars_15m, LOCKED_FVG_PARAMS, context={"timeframe": "15m"})


# ── Count Regression ─────────────────────────────────────────────────────────

class TestFVGCountRegression:
    """Verify total counts and bull/bear splits match baseline exactly."""

    def test_fvg_1m_count(self, result_1m, fvg_baseline_1m):
        """FVG 1m: 2,017 total (1,026 bullish, 991 bearish)."""
        baseline_fvgs = fvg_baseline_1m["fvgs"]
        assert len(result_1m.detections) == len(baseline_fvgs)

        bull = [d for d in result_1m.detections if d.direction == "bullish"]
        bear = [d for d in result_1m.detections if d.direction == "bearish"]
        baseline_bull = [f for f in baseline_fvgs if f["type"] == "bullish"]
        baseline_bear = [f for f in baseline_fvgs if f["type"] == "bearish"]
        assert len(bull) == len(baseline_bull)
        assert len(bear) == len(baseline_bear)

    def test_fvg_5m_count(self, result_5m, fvg_baseline_5m):
        """FVG 5m: 345 total (179 bullish, 166 bearish)."""
        baseline_fvgs = fvg_baseline_5m["fvgs"]
        assert len(result_5m.detections) == len(baseline_fvgs)

        bull = [d for d in result_5m.detections if d.direction == "bullish"]
        bear = [d for d in result_5m.detections if d.direction == "bearish"]
        baseline_bull = [f for f in baseline_fvgs if f["type"] == "bullish"]
        baseline_bear = [f for f in baseline_fvgs if f["type"] == "bearish"]
        assert len(bull) == len(baseline_bull)
        assert len(bear) == len(baseline_bear)

    def test_fvg_15m_count(self, result_15m, fvg_baseline_15m):
        """FVG 15m: 118 total (58 bullish, 60 bearish)."""
        baseline_fvgs = fvg_baseline_15m["fvgs"]
        assert len(result_15m.detections) == len(baseline_fvgs)

        bull = [d for d in result_15m.detections if d.direction == "bullish"]
        bear = [d for d in result_15m.detections if d.direction == "bearish"]
        baseline_bull = [f for f in baseline_fvgs if f["type"] == "bullish"]
        baseline_bear = [f for f in baseline_fvgs if f["type"] == "bearish"]
        assert len(bull) == len(baseline_bull)
        assert len(bear) == len(baseline_bear)


# ── Per-Detection Field Match ────────────────────────────────────────────────

class TestFVGFieldMatch:
    """Verify per-detection fields match baseline within tolerance."""

    def _compare_fvg_fields(self, detections, baseline_fvgs, tf):
        """Compare every detection against baseline fixture."""
        assert len(detections) == len(baseline_fvgs), (
            f"Count mismatch on {tf}: got {len(detections)}, "
            f"expected {len(baseline_fvgs)}"
        )

        for i, (det, base) in enumerate(zip(detections, baseline_fvgs)):
            # Direction
            assert det.direction == base["type"], (
                f"[{tf}][{i}] direction: {det.direction} != {base['type']}"
            )

            # Bar index
            assert det.properties["bar_index"] == base["bar_index"], (
                f"[{tf}][{i}] bar_index: {det.properties['bar_index']} != {base['bar_index']}"
            )

            # Anchor time
            assert det.properties["anchor_time"] == base["anchor_time"], (
                f"[{tf}][{i}] anchor_time: {det.properties['anchor_time']} != {base['anchor_time']}"
            )

            # Detect time
            assert det.properties["detect_time"] == base["detect_time"], (
                f"[{tf}][{i}] detect_time: {det.properties['detect_time']} != {base['detect_time']}"
            )

            # Price fields (within 1e-6)
            assert det.properties["top"] == pytest.approx(base["top"], abs=1e-6), (
                f"[{tf}][{i}] top: {det.properties['top']} != {base['top']}"
            )
            assert det.properties["bottom"] == pytest.approx(base["bottom"], abs=1e-6), (
                f"[{tf}][{i}] bottom: {det.properties['bottom']} != {base['bottom']}"
            )
            assert det.properties["gap_pips"] == pytest.approx(base["gap_pips"], abs=0.01), (
                f"[{tf}][{i}] gap_pips: {det.properties['gap_pips']} != {base['gap_pips']}"
            )
            assert det.properties["ce"] == pytest.approx(base["ce"], abs=1e-6), (
                f"[{tf}][{i}] ce: {det.properties['ce']} != {base['ce']}"
            )

            # Context fields
            assert det.properties["vi_confluent"] == base["vi_confluent"], (
                f"[{tf}][{i}] vi_confluent: {det.properties['vi_confluent']} != {base['vi_confluent']}"
            )
            assert det.tags.get("forex_day") == base["forex_day"], (
                f"[{tf}][{i}] forex_day: {det.tags.get('forex_day')} != {base['forex_day']}"
            )
            assert det.tags.get("session") == base["session"], (
                f"[{tf}][{i}] session: {det.tags.get('session')} != {base['session']}"
            )
            assert det.properties.get("tf") == base["tf"], (
                f"[{tf}][{i}] tf: {det.properties.get('tf')} != {base['tf']}"
            )

    def test_fvg_1m_field_match(self, result_1m, fvg_baseline_1m):
        """1m: Every detection's fields match baseline."""
        self._compare_fvg_fields(
            result_1m.detections, fvg_baseline_1m["fvgs"], "1m"
        )

    def test_fvg_5m_field_match(self, result_5m, fvg_baseline_5m):
        """5m: Every detection's fields match baseline."""
        self._compare_fvg_fields(
            result_5m.detections, fvg_baseline_5m["fvgs"], "5m"
        )

    def test_fvg_15m_field_match(self, result_15m, fvg_baseline_15m):
        """15m: Every detection's fields match baseline."""
        self._compare_fvg_fields(
            result_15m.detections, fvg_baseline_15m["fvgs"], "15m"
        )


# ── IFVG State Transitions ──────────────────────────────────────────────────

class TestIFVGStateTransitions:
    """Verify CE_TOUCHED and BOUNDARY_CLOSED tracking matches baseline."""

    def _compare_state_fields(self, detections, baseline_fvgs, tf):
        """Compare IFVG state transition fields."""
        for i, (det, base) in enumerate(zip(detections, baseline_fvgs)):
            # CE touched
            assert det.properties.get("ce_touched_bar") == base["ce_touched_bar"], (
                f"[{tf}][{i}] ce_touched_bar: "
                f"{det.properties.get('ce_touched_bar')} != {base['ce_touched_bar']}"
            )
            assert det.properties.get("ce_touched_time") == base["ce_touched_time"], (
                f"[{tf}][{i}] ce_touched_time: "
                f"{det.properties.get('ce_touched_time')} != {base['ce_touched_time']}"
            )

            # Boundary closed
            assert det.properties.get("boundary_closed_bar") == base["boundary_closed_bar"], (
                f"[{tf}][{i}] boundary_closed_bar: "
                f"{det.properties.get('boundary_closed_bar')} != {base['boundary_closed_bar']}"
            )
            assert det.properties.get("boundary_closed_time") == base["boundary_closed_time"], (
                f"[{tf}][{i}] boundary_closed_time: "
                f"{det.properties.get('boundary_closed_time')} != {base['boundary_closed_time']}"
            )

    def test_ifvg_state_1m(self, result_1m, fvg_baseline_1m):
        """1m: IFVG state transition fields match baseline."""
        self._compare_state_fields(
            result_1m.detections, fvg_baseline_1m["fvgs"], "1m"
        )

    def test_ifvg_state_5m(self, result_5m, fvg_baseline_5m):
        """5m: IFVG state transition fields match baseline."""
        self._compare_state_fields(
            result_5m.detections, fvg_baseline_5m["fvgs"], "5m"
        )

    def test_ifvg_state_15m(self, result_15m, fvg_baseline_15m):
        """15m: IFVG state transition fields match baseline."""
        self._compare_state_fields(
            result_15m.detections, fvg_baseline_15m["fvgs"], "15m"
        )


# ── BPR Overlap ──────────────────────────────────────────────────────────────

class TestBPROverlap:
    """Verify BPR zones are computed for overlapping bull+bear FVGs."""

    def test_bpr_zones_computed(self, result_5m):
        """BPR zones exist in metadata for 5m."""
        assert "bpr_zones" in result_5m.metadata, (
            "Expected 'bpr_zones' in metadata"
        )
        bpr_zones = result_5m.metadata["bpr_zones"]
        assert isinstance(bpr_zones, list)
        # There should be some overlapping bull+bear FVGs
        # (exact count depends on data)

    def test_bpr_zone_structure(self, result_5m):
        """Each BPR zone has correct structure."""
        bpr_zones = result_5m.metadata.get("bpr_zones", [])
        if len(bpr_zones) > 0:
            zone = bpr_zones[0]
            assert "overlap_top" in zone
            assert "overlap_bottom" in zone
            assert "bull_source_idx" in zone
            assert "bear_source_idx" in zone
            assert zone["overlap_top"] > zone["overlap_bottom"]


# ── Floor Threshold Metadata ─────────────────────────────────────────────────

class TestFloorThresholdMetadata:
    """Verify floor threshold is metadata annotation, NOT a hard filter."""

    def test_sub_floor_fvgs_present(self, result_5m):
        """Sub-floor FVGs (gap_pips < floor_threshold) are included in output."""
        sub_floor = [
            d for d in result_5m.detections
            if d.properties["gap_pips"] < LOCKED_FVG_PARAMS["floor_threshold_pips"]
        ]
        # The baseline has 345 FVGs which includes sub-floor ones
        assert len(sub_floor) > 0, (
            "Expected sub-floor FVGs to be present (floor is metadata, not filter)"
        )

    def test_total_includes_all_sizes(self, result_5m, fvg_baseline_5m):
        """Total count includes ALL FVGs regardless of gap size."""
        assert len(result_5m.detections) == len(fvg_baseline_5m["fvgs"])


# ── Config-Driven Parameters ────────────────────────────────────────────────

class TestConfigDriven:
    """Verify detector uses config params, not hardcoded values."""

    def test_params_echoed_in_result(self, result_5m):
        """Result echoes the params used for provenance."""
        assert result_5m.params_used == LOCKED_FVG_PARAMS

    def test_detector_metadata(self, detector):
        """Detector has correct primitive_name and variant."""
        assert detector.primitive_name == "fvg"
        assert detector.variant_name == "a8ra_v1"

    def test_required_upstream_empty(self, detector):
        """FVG is a leaf node — no upstream dependencies."""
        assert detector.required_upstream() == []


# ── Result Structure ─────────────────────────────────────────────────────────

class TestResultStructure:
    """Verify DetectionResult structure is correct."""

    def test_result_type(self, result_5m):
        """Result is a DetectionResult."""
        assert isinstance(result_5m, DetectionResult)

    def test_result_primitive(self, result_5m):
        """Result primitive is 'fvg'."""
        assert result_5m.primitive == "fvg"

    def test_result_variant(self, result_5m):
        """Result variant is 'a8ra_v1'."""
        assert result_5m.variant == "a8ra_v1"

    def test_result_timeframe(self, result_5m):
        """Result timeframe is '5m'."""
        assert result_5m.timeframe == "5m"

    def test_detection_ids_deterministic(self, detector, bars_5m):
        """Same inputs produce same detection IDs."""
        r1 = detector.detect(bars_5m, LOCKED_FVG_PARAMS, context={"timeframe": "5m"})
        r2 = detector.detect(bars_5m, LOCKED_FVG_PARAMS, context={"timeframe": "5m"})
        ids1 = [d.id for d in r1.detections]
        ids2 = [d.id for d in r2.detections]
        assert ids1 == ids2

    def test_detection_id_format(self, result_5m):
        """Detection IDs follow {primitive}_{tf}_{timestamp_ny}_{direction} format."""
        for det in result_5m.detections[:5]:
            parts = det.id.split("_")
            assert parts[0] == "fvg"
            assert parts[1] == "5m"
            # timestamp is in format 2024-01-08T09:10:00
            assert "T" in parts[2]
            assert parts[3] in ("bull", "bear")
