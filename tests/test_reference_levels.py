"""Tests for ReferenceLevelDetector — regression against baseline fixtures.

Tests cover:
- PDH/PDL per forex day exact match
- PWH=1.10001, PWL=1.09104
- Midnight open per day
- Day high/low per day
- Equilibrium computation
"""

import json
from pathlib import Path

import pytest

from ra.detectors.reference_levels import ReferenceLevelDetector
from ra.detectors.equal_hl import EqualHLDetector
from ra.engine.base import DetectionResult
from ra.engine.registry import Registry

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked reference_levels params from config
LOCKED_PARAMS = {
    "pdh_pdl": {
        "boundary": "forex_day",
        "measurement": "wicks",
    },
    "midnight_open": {
        "time_ny": "00:00",
    },
    "equilibrium": {
        "formula": "midpoint",
    },
}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def levels_baseline():
    """Load the levels baseline fixture."""
    with open(FIXTURE_DIR / "levels_data.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def detector():
    """Create a ReferenceLevelDetector instance."""
    return ReferenceLevelDetector()


@pytest.fixture(scope="module")
def result(detector, bars_1m):
    """Run reference level detector on 1m bars."""
    return detector.detect(bars_1m, LOCKED_PARAMS)


# ── Count Tests ──────────────────────────────────────────────────────────────


class TestReferenceLevelCount:
    """Verify detection count matches baseline."""

    def test_total_days(self, result, levels_baseline):
        """5 forex days in output."""
        assert len(result.detections) == len(levels_baseline)
        assert len(result.detections) == 5


# ── PDH/PDL Tests ────────────────────────────────────────────────────────────


class TestPDHPDL:
    """Verify PDH/PDL values per day match baseline exactly."""

    def test_jan9_pdh_pdl(self, result, levels_baseline):
        """Jan 9 PDH/PDL from Jan 8 day high/low."""
        jan9 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-09"
        ][0]
        base = levels_baseline["2024-01-09"]
        assert jan9.properties["pdh"] == pytest.approx(base["pdh"], abs=1e-6)
        assert jan9.properties["pdl"] == pytest.approx(base["pdl"], abs=1e-6)

    def test_jan10_pdh_pdl(self, result, levels_baseline):
        """Jan 10 PDH/PDL from Jan 9 day high/low."""
        jan10 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-10"
        ][0]
        base = levels_baseline["2024-01-10"]
        assert jan10.properties["pdh"] == pytest.approx(base["pdh"], abs=1e-6)
        assert jan10.properties["pdl"] == pytest.approx(base["pdl"], abs=1e-6)

    def test_jan11_pdh_pdl(self, result, levels_baseline):
        """Jan 11 PDH/PDL from Jan 10 day high/low."""
        jan11 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-11"
        ][0]
        base = levels_baseline["2024-01-11"]
        assert jan11.properties["pdh"] == pytest.approx(base["pdh"], abs=1e-6)
        assert jan11.properties["pdl"] == pytest.approx(base["pdl"], abs=1e-6)

    def test_jan12_pdh_pdl(self, result, levels_baseline):
        """Jan 12 PDH/PDL from Jan 11 day high/low."""
        jan12 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-12"
        ][0]
        base = levels_baseline["2024-01-12"]
        assert jan12.properties["pdh"] == pytest.approx(base["pdh"], abs=1e-6)
        assert jan12.properties["pdl"] == pytest.approx(base["pdl"], abs=1e-6)

    def test_jan8_no_pdh_pdl(self, result, levels_baseline):
        """Jan 8 (first day) has no PDH/PDL."""
        jan8 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-08"
        ][0]
        base = levels_baseline["2024-01-08"]
        assert "pdh" not in jan8.properties or jan8.properties.get("pdh") is None
        assert "pdh" not in base  # baseline also has no PDH for first day

    def test_all_pdh_pdl_match(self, result, levels_baseline):
        """PDH/PDL for all days with previous day match baseline within 1e-6."""
        for det in result.detections:
            day = det.tags["forex_day"]
            base = levels_baseline[day]
            if "pdh" in base:
                assert det.properties["pdh"] == pytest.approx(
                    base["pdh"], abs=1e-6
                ), f"{day}: PDH mismatch"
            if "pdl" in base:
                assert det.properties["pdl"] == pytest.approx(
                    base["pdl"], abs=1e-6
                ), f"{day}: PDL mismatch"


# ── PWH/PWL Tests ────────────────────────────────────────────────────────────


class TestPWHPWL:
    """Verify PWH and PWL dataset-level values."""

    def test_pwh(self, result):
        """PWH = 1.10001 (from VAL-REF-001)."""
        assert result.metadata["pwh"] == pytest.approx(1.10001, abs=1e-5)

    def test_pwl(self, result):
        """PWL = 1.09104 (from VAL-REF-001)."""
        assert result.metadata["pwl"] == pytest.approx(1.09104, abs=1e-5)


# ── Day High/Low Tests ───────────────────────────────────────────────────────


class TestDayHighLow:
    """Verify day_high and day_low per day match baseline."""

    def test_all_day_high_low_match(self, result, levels_baseline):
        """Day high/low for all days match baseline within 1e-6."""
        for det in result.detections:
            day = det.tags["forex_day"]
            base = levels_baseline[day]
            assert det.properties["day_high"] == pytest.approx(
                base["day_high"], abs=1e-6
            ), f"{day}: day_high mismatch"
            assert det.properties["day_low"] == pytest.approx(
                base["day_low"], abs=1e-6
            ), f"{day}: day_low mismatch"


# ── Midnight Open Tests ──────────────────────────────────────────────────────


class TestMidnightOpen:
    """Verify midnight open per day matches baseline."""

    def test_all_midnight_open_match(self, result, levels_baseline):
        """Midnight open for all days match baseline within 1e-6."""
        for det in result.detections:
            day = det.tags["forex_day"]
            base = levels_baseline[day]
            assert det.properties["midnight_open"] == pytest.approx(
                base["midnight_open"], abs=1e-6
            ), f"{day}: midnight_open mismatch"


# ── Equilibrium Tests ────────────────────────────────────────────────────────


class TestEquilibrium:
    """Verify equilibrium (midpoint of PDH/PDL) when available."""

    def test_equilibrium_computed(self, result):
        """Days with PDH/PDL have equilibrium as midpoint."""
        for det in result.detections:
            if "pdh" in det.properties and det.properties["pdh"] is not None:
                pdh = det.properties["pdh"]
                pdl = det.properties["pdl"]
                expected_eq = (pdh + pdl) / 2
                assert det.properties["equilibrium"] == pytest.approx(
                    expected_eq, abs=1e-6
                )

    def test_first_day_no_equilibrium(self, result):
        """First day has no equilibrium (no PDH/PDL)."""
        jan8 = [
            d for d in result.detections
            if d.tags["forex_day"] == "2024-01-08"
        ][0]
        assert jan8.properties["equilibrium"] is None


# ── Detector Interface Tests ─────────────────────────────────────────────────


class TestReferenceLevelInterface:
    """Verify detector implements PrimitiveDetector ABC correctly."""

    def test_primitive_name(self):
        d = ReferenceLevelDetector()
        assert d.primitive_name == "reference_levels"

    def test_variant_name(self):
        d = ReferenceLevelDetector()
        assert d.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        d = ReferenceLevelDetector()
        assert d.required_upstream() == []

    def test_result_type(self, result):
        assert isinstance(result, DetectionResult)
        assert result.primitive == "reference_levels"
        assert result.variant == "a8ra_v1"


# ── Equal HL Stub Tests ─────────────────────────────────────────────────────


class TestEqualHLStub:
    """Verify EqualHLDetector raises NotImplementedError and is registerable."""

    def test_raises_not_implemented(self, bars_1m):
        """detect() raises NotImplementedError."""
        detector = EqualHLDetector()
        with pytest.raises(NotImplementedError, match="DEFERRED"):
            detector.detect(bars_1m, {})

    def test_primitive_name(self):
        d = EqualHLDetector()
        assert d.primitive_name == "equal_hl"

    def test_variant_name(self):
        d = EqualHLDetector()
        assert d.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        d = EqualHLDetector()
        assert d.required_upstream() == ["swing_points"]

    def test_registry_registration(self):
        """EqualHLDetector can be registered in the registry."""
        registry = Registry()
        registry.register(EqualHLDetector)
        assert registry.has("equal_hl", "a8ra_v1")
        instance = registry.get("equal_hl", "a8ra_v1")
        assert isinstance(instance, EqualHLDetector)
