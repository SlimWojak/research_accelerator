"""Tests for AsiaRangeDetector — regression against baseline fixtures.

Tests cover:
- 5-day range pips match baseline exactly
- Parametric binary classifications match at all thresholds
- High/low prices match baseline
- Bar count matches
"""

import json
from pathlib import Path

import pytest

from ra.detectors.asia_range import AsiaRangeDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked asia_range params from config
LOCKED_PARAMS = {
    "classification": {
        "tight_below_pips": 10,
        "mid_below_pips": 20,
        "wide_above_pips": 20,
    },
    "max_cap_pips": 30,
}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def asia_baseline():
    """Load the Asia range baseline fixture."""
    with open(FIXTURE_DIR / "asia_data.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def detector():
    """Create an AsiaRangeDetector instance."""
    return AsiaRangeDetector()


@pytest.fixture(scope="module")
def result(detector, bars_1m):
    """Run Asia range detector on 1m bars."""
    return detector.detect(bars_1m, LOCKED_PARAMS)


# ── Count Tests ──────────────────────────────────────────────────────────────


class TestAsiaRangeCount:
    """Verify total day count matches baseline."""

    def test_total_days(self, result, asia_baseline):
        """5 forex days with Asia session data."""
        baseline_ranges = asia_baseline["ranges"]
        assert len(result.detections) == len(baseline_ranges)
        assert len(result.detections) == 5


# ── Range Pips Tests ─────────────────────────────────────────────────────────


class TestAsiaRangeValues:
    """Verify range pips for all 5 days match baseline exactly."""

    def test_all_range_pips_match(self, result, asia_baseline):
        """Each day's range_pips matches baseline."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            assert det.properties["range_pips"] == pytest.approx(
                base["range_pips"], abs=0.15
            ), (
                f"Day {i} ({base['forex_day']}): "
                f"range_pips {det.properties['range_pips']} != {base['range_pips']}"
            )

    def test_specific_range_pips(self, result):
        """Exact range pips: Jan8=22.4, Jan9=17.0, Jan10=10.3, Jan11=11.7, Jan12=12.7."""
        expected = {
            "2024-01-08": 22.4,
            "2024-01-09": 17.0,
            "2024-01-10": 10.3,
            "2024-01-11": 11.7,
            "2024-01-12": 12.7,
        }
        for det in result.detections:
            day = det.properties["forex_day"]
            if day in expected:
                assert det.properties["range_pips"] == pytest.approx(
                    expected[day], abs=0.15
                ), f"Day {day}: range mismatch"


# ── Classification Tests ─────────────────────────────────────────────────────


class TestAsiaRangeClassifications:
    """Verify parametric classifications at all thresholds match baseline."""

    def test_all_classifications_match(self, result, asia_baseline):
        """Each threshold classification matches baseline."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            ra_class = det.properties["classifications"]
            base_class = base["classifications"]
            for threshold in base_class:
                assert ra_class[threshold] == base_class[threshold], (
                    f"Day {i} ({base['forex_day']}), threshold {threshold}: "
                    f"{ra_class.get(threshold)} != {base_class[threshold]}"
                )

    def test_thresholds_present(self, result, asia_baseline):
        """All baseline thresholds are present in output."""
        baseline_thresholds = asia_baseline["thresholds"]
        for det in result.detections:
            for t in baseline_thresholds:
                assert str(t) in det.properties["classifications"], (
                    f"Missing threshold {t} in classifications"
                )


# ── Field Match Tests ────────────────────────────────────────────────────────


class TestAsiaRangeFieldMatch:
    """Verify per-day field matching against baseline."""

    def test_high_low_match(self, result, asia_baseline):
        """High and low prices match baseline within 1e-6."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            assert det.properties["high"] == pytest.approx(
                base["high"], abs=1e-6
            ), f"Day {i}: high mismatch"
            assert det.properties["low"] == pytest.approx(
                base["low"], abs=1e-6
            ), f"Day {i}: low mismatch"

    def test_bar_count_match(self, result, asia_baseline):
        """Bar count matches baseline."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            assert det.properties["bar_count"] == base["bar_count"], (
                f"Day {i}: bar_count {det.properties['bar_count']} != {base['bar_count']}"
            )

    def test_start_end_times_match(self, result, asia_baseline):
        """Start and end times match baseline."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            assert det.properties["start_time"] == base["start_time"], (
                f"Day {i}: start_time mismatch"
            )
            assert det.properties["end_time"] == base["end_time"], (
                f"Day {i}: end_time mismatch"
            )

    def test_forex_day_match(self, result, asia_baseline):
        """Forex days match baseline."""
        baseline_ranges = asia_baseline["ranges"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_ranges)
        ):
            assert det.properties["forex_day"] == base["forex_day"], (
                f"Day {i}: forex_day mismatch"
            )


# ── Detector Interface Tests ─────────────────────────────────────────────────


class TestAsiaRangeInterface:
    """Verify detector implements PrimitiveDetector ABC correctly."""

    def test_primitive_name(self):
        d = AsiaRangeDetector()
        assert d.primitive_name == "asia_range"

    def test_variant_name(self):
        d = AsiaRangeDetector()
        assert d.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        d = AsiaRangeDetector()
        assert d.required_upstream() == []

    def test_result_type(self, result):
        assert isinstance(result, DetectionResult)
        assert result.primitive == "asia_range"
        assert result.variant == "a8ra_v1"
