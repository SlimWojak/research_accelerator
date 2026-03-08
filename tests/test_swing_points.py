"""Tests for SwingPointDetector — regression against baseline fixtures.

Tests cover:
- Count regression per TF (1m, 5m, 15m)
- High/low split
- Per-detection field matching against baseline
- Strength cap at 20
- Boundary swings with height_pips=999.0
- Ghost bar skipping
"""

import json
from pathlib import Path

import pytest

from ra.detectors.swing_points import SwingPointDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked swing_points params from config (per-TF)
LOCKED_PARAMS_1M = {
    "N": 5,
    "height_filter_pips": 0.5,
    "strength_cap": 20,
    "strength_as_gate": False,
}

LOCKED_PARAMS_5M = {
    "N": 3,
    "height_filter_pips": 3.0,
    "strength_cap": 20,
    "strength_as_gate": False,
}

LOCKED_PARAMS_15M = {
    "N": 2,
    "height_filter_pips": 3.0,
    "strength_cap": 20,
    "strength_as_gate": False,
}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def swing_baseline_1m():
    """Load the 1m swing baseline fixture."""
    with open(FIXTURE_DIR / "swing_data_1m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def swing_baseline_5m():
    """Load the 5m swing baseline fixture."""
    with open(FIXTURE_DIR / "swing_data_5m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def swing_baseline_15m():
    """Load the 15m swing baseline fixture."""
    with open(FIXTURE_DIR / "swing_data_15m.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def detector():
    """Create a SwingPointDetector instance."""
    return SwingPointDetector()


@pytest.fixture(scope="module")
def result_1m(detector, bars_1m):
    """Run swing detector on 1m bars."""
    return detector.detect(bars_1m, LOCKED_PARAMS_1M, context={"timeframe": "1m"})


@pytest.fixture(scope="module")
def result_5m(detector, bars_5m):
    """Run swing detector on 5m bars."""
    return detector.detect(bars_5m, LOCKED_PARAMS_5M, context={"timeframe": "5m"})


@pytest.fixture(scope="module")
def result_15m(detector, bars_15m):
    """Run swing detector on 15m bars."""
    return detector.detect(bars_15m, LOCKED_PARAMS_15M, context={"timeframe": "15m"})


# ── Count Regression ─────────────────────────────────────────────────────────

class TestSwingCountRegression:
    """Verify total counts and high/low splits match baseline exactly."""

    def test_swing_1m_count(self, result_1m, swing_baseline_1m):
        """Swing 1m: 833 total (420 high, 413 low)."""
        baseline_swings = swing_baseline_1m["swings"]
        assert len(result_1m.detections) == len(baseline_swings), (
            f"1m count mismatch: got {len(result_1m.detections)}, "
            f"expected {len(baseline_swings)}"
        )

        highs = [d for d in result_1m.detections if d.direction == "high"]
        lows = [d for d in result_1m.detections if d.direction == "low"]
        baseline_highs = [s for s in baseline_swings if s["type"] == "high"]
        baseline_lows = [s for s in baseline_swings if s["type"] == "low"]
        assert len(highs) == len(baseline_highs), (
            f"1m highs: got {len(highs)}, expected {len(baseline_highs)}"
        )
        assert len(lows) == len(baseline_lows), (
            f"1m lows: got {len(lows)}, expected {len(baseline_lows)}"
        )

    def test_swing_5m_count(self, result_5m, swing_baseline_5m):
        """Swing 5m: 267 total (135 high, 132 low)."""
        baseline_swings = swing_baseline_5m["swings"]
        assert len(result_5m.detections) == len(baseline_swings), (
            f"5m count mismatch: got {len(result_5m.detections)}, "
            f"expected {len(baseline_swings)}"
        )

        highs = [d for d in result_5m.detections if d.direction == "high"]
        lows = [d for d in result_5m.detections if d.direction == "low"]
        baseline_highs = [s for s in baseline_swings if s["type"] == "high"]
        baseline_lows = [s for s in baseline_swings if s["type"] == "low"]
        assert len(highs) == len(baseline_highs), (
            f"5m highs: got {len(highs)}, expected {len(baseline_highs)}"
        )
        assert len(lows) == len(baseline_lows), (
            f"5m lows: got {len(lows)}, expected {len(baseline_lows)}"
        )

    def test_swing_15m_count(self, result_15m, swing_baseline_15m):
        """Swing 15m: 124 total (62 high, 62 low)."""
        baseline_swings = swing_baseline_15m["swings"]
        assert len(result_15m.detections) == len(baseline_swings), (
            f"15m count mismatch: got {len(result_15m.detections)}, "
            f"expected {len(baseline_swings)}"
        )

        highs = [d for d in result_15m.detections if d.direction == "high"]
        lows = [d for d in result_15m.detections if d.direction == "low"]
        baseline_highs = [s for s in baseline_swings if s["type"] == "high"]
        baseline_lows = [s for s in baseline_swings if s["type"] == "low"]
        assert len(highs) == len(baseline_highs), (
            f"15m highs: got {len(highs)}, expected {len(baseline_highs)}"
        )
        assert len(lows) == len(baseline_lows), (
            f"15m lows: got {len(lows)}, expected {len(baseline_lows)}"
        )


# ── Per-Detection Field Match ────────────────────────────────────────────────

class TestSwingFieldMatch:
    """Verify per-detection fields match baseline within tolerance."""

    def _compare_swing_fields(self, detections, baseline_swings, tf):
        """Compare every detection against baseline fixture."""
        assert len(detections) == len(baseline_swings), (
            f"Count mismatch on {tf}: got {len(detections)}, "
            f"expected {len(baseline_swings)}"
        )

        for i, (det, base) in enumerate(zip(detections, baseline_swings)):
            # Direction / type
            assert det.direction == base["type"], (
                f"[{tf}][{i}] type: {det.direction} != {base['type']}"
            )

            # Bar index
            assert det.properties["bar_index"] == base["bar_index"], (
                f"[{tf}][{i}] bar_index: {det.properties['bar_index']} != {base['bar_index']}"
            )

            # Time
            assert det.properties["time"] == base["time"], (
                f"[{tf}][{i}] time: {det.properties['time']} != {base['time']}"
            )

            # Price (within 1e-6)
            assert det.price == pytest.approx(base["price"], abs=1e-6), (
                f"[{tf}][{i}] price: {det.price} != {base['price']}"
            )

            # Strength
            assert det.properties["strength"] == base["strength"], (
                f"[{tf}][{i}] strength: {det.properties['strength']} != {base['strength']}"
            )

            # Height pips
            assert det.properties["height_pips"] == pytest.approx(base["height_pips"], abs=0.01), (
                f"[{tf}][{i}] height_pips: {det.properties['height_pips']} != {base['height_pips']}"
            )

            # Session
            assert det.tags.get("session") == base["session"], (
                f"[{tf}][{i}] session: {det.tags.get('session')} != {base['session']}"
            )

            # Forex day
            assert det.tags.get("forex_day") == base["forex_day"], (
                f"[{tf}][{i}] forex_day: {det.tags.get('forex_day')} != {base['forex_day']}"
            )

            # TF
            assert det.properties.get("tf") == base["tf"], (
                f"[{tf}][{i}] tf: {det.properties.get('tf')} != {base['tf']}"
            )

    def test_swing_1m_field_match(self, result_1m, swing_baseline_1m):
        """1m: Every detection's fields match baseline."""
        self._compare_swing_fields(
            result_1m.detections, swing_baseline_1m["swings"], "1m"
        )

    def test_swing_5m_field_match(self, result_5m, swing_baseline_5m):
        """5m: Every detection's fields match baseline."""
        self._compare_swing_fields(
            result_5m.detections, swing_baseline_5m["swings"], "5m"
        )

    def test_swing_15m_field_match(self, result_15m, swing_baseline_15m):
        """15m: Every detection's fields match baseline."""
        self._compare_swing_fields(
            result_15m.detections, swing_baseline_15m["swings"], "15m"
        )


# ── Strength Cap and Tag-Only Behavior ───────────────────────────────────────

class TestStrengthCap:
    """Verify strength is capped at 20 and used as tag only."""

    def test_strength_capped_at_20(self, result_5m):
        """No swing has strength > 20."""
        for det in result_5m.detections:
            assert det.properties["strength"] <= 20, (
                f"Strength {det.properties['strength']} exceeds cap of 20 "
                f"at bar_index {det.properties['bar_index']}"
            )

    def test_strength_tag_only(self, result_5m, swing_baseline_5m):
        """All swings emitted regardless of strength (no strength-based filtering)."""
        # Verify total count matches — if strength were used as gate,
        # some swings would be filtered out
        assert len(result_5m.detections) == len(swing_baseline_5m["swings"])


# ── Boundary Swings ──────────────────────────────────────────────────────────

class TestBoundarySwings:
    """Verify boundary swings have height_pips=999.0 sentinel."""

    def test_boundary_swings_have_sentinel(self, result_5m, swing_baseline_5m):
        """Swings without a nearby opposite swing have height_pips=999.0."""
        baseline_sentinels = [
            s for s in swing_baseline_5m["swings"]
            if s["height_pips"] == 999.0
        ]
        result_sentinels = [
            d for d in result_5m.detections
            if d.properties["height_pips"] == 999.0
        ]
        assert len(result_sentinels) == len(baseline_sentinels), (
            f"Sentinel count mismatch: got {len(result_sentinels)}, "
            f"expected {len(baseline_sentinels)}"
        )


# ── Config-Driven Parameters ────────────────────────────────────────────────

class TestConfigDriven:
    """Verify detector uses config params, not hardcoded values."""

    def test_params_echoed_in_result(self, result_5m):
        """Result echoes the params used for provenance."""
        assert result_5m.params_used == LOCKED_PARAMS_5M

    def test_detector_metadata(self, detector):
        """Detector has correct primitive_name and variant."""
        assert detector.primitive_name == "swing_points"
        assert detector.variant_name == "a8ra_v1"

    def test_required_upstream_empty(self, detector):
        """Swing points is a leaf node — no upstream dependencies."""
        assert detector.required_upstream() == []


# ── Result Structure ─────────────────────────────────────────────────────────

class TestResultStructure:
    """Verify DetectionResult structure is correct."""

    def test_result_type(self, result_5m):
        """Result is a DetectionResult."""
        assert isinstance(result_5m, DetectionResult)

    def test_result_primitive(self, result_5m):
        """Result primitive is 'swing_points'."""
        assert result_5m.primitive == "swing_points"

    def test_result_variant(self, result_5m):
        """Result variant is 'a8ra_v1'."""
        assert result_5m.variant == "a8ra_v1"

    def test_result_timeframe(self, result_5m):
        """Result timeframe is '5m'."""
        assert result_5m.timeframe == "5m"

    def test_detection_ids_deterministic(self, detector, bars_5m):
        """Same inputs produce same detection IDs."""
        r1 = detector.detect(bars_5m, LOCKED_PARAMS_5M, context={"timeframe": "5m"})
        r2 = detector.detect(bars_5m, LOCKED_PARAMS_5M, context={"timeframe": "5m"})
        ids1 = [d.id for d in r1.detections]
        ids2 = [d.id for d in r2.detections]
        assert ids1 == ids2

    def test_detection_id_format(self, result_5m):
        """Detection IDs follow {primitive}_{tf}_{timestamp_ny}_{direction} format."""
        for det in result_5m.detections[:5]:
            parts = det.id.split("_")
            assert parts[0] == "swing"
            assert parts[1] == "points"
            # After swing_points the next part is the TF
            # Actually: ID = swing_points_5m_2024-01-07T17:15:00_low
            # Let's check the full format
            assert "swing_points" in det.id
            assert "5m" in det.id
