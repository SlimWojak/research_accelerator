"""Tests for SessionLiquidityDetector — regression against baseline fixtures.

Tests cover:
- 15 box classifications match baseline exactly
- Classification labels: CONSOLIDATION_BOX, TREND_OR_EXPANSION
- Trend direction (UP/DOWN/null) for each box
- Range pips match baseline values
- Efficiency, mid_cross_count, balance_score values
- Interaction tracking per level
- Four-gate model behavior
"""

import json
from pathlib import Path

import pytest

from ra.detectors.session_liquidity import SessionLiquidityDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked session_liquidity params from config
LOCKED_PARAMS = {
    "four_gate_model": {
        "efficiency_threshold": {"locked": 0.60},
        "mid_cross_min": {"locked": 2},
        "balance_score_min": {"locked": 0.30},
    },
    "box_objects": {
        "asia": {
            "window": {"start_ny": "19:00", "end_ny": "00:00"},
            "range_cap_pips": 30,
        },
        "pre_london": {
            "window": {"start_ny": "00:00", "end_ny": "02:00"},
            "range_cap_pips": 15,
        },
        "pre_ny": {
            "window": {"start_ny": "05:00", "end_ny": "07:00"},
            "range_cap_pips": 20,
        },
    },
}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def session_baseline():
    """Load the session boxes baseline fixture."""
    with open(FIXTURE_DIR / "session_boxes.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def detector():
    """Create a SessionLiquidityDetector instance."""
    return SessionLiquidityDetector()


@pytest.fixture(scope="module")
def result(detector, bars_1m):
    """Run session liquidity detector on 1m bars."""
    return detector.detect(bars_1m, LOCKED_PARAMS)


# ── Count Tests ──────────────────────────────────────────────────────────────


class TestSessionLiquidityCount:
    """Verify total box count matches baseline."""

    def test_total_boxes(self, result, session_baseline):
        """15 boxes total (5 days x 3 sessions)."""
        baseline_boxes = session_baseline["boxes"]
        assert len(result.detections) == len(baseline_boxes)
        assert len(result.detections) == 15

    def test_consolidation_count(self, result, session_baseline):
        """Count of consolidation boxes matches baseline."""
        baseline_consol = sum(
            1
            for b in session_baseline["boxes"]
            if b["classification"] == "CONSOLIDATION_BOX"
        )
        ra_consol = sum(
            1
            for d in result.detections
            if d.properties["classification"] == "CONSOLIDATION_BOX"
        )
        assert ra_consol == baseline_consol

    def test_trend_count(self, result, session_baseline):
        """Count of trend/expansion boxes matches baseline."""
        baseline_trend = sum(
            1
            for b in session_baseline["boxes"]
            if b["classification"] == "TREND_OR_EXPANSION"
        )
        ra_trend = sum(
            1
            for d in result.detections
            if d.properties["classification"] == "TREND_OR_EXPANSION"
        )
        assert ra_trend == baseline_trend


# ── Classification Tests ─────────────────────────────────────────────────────


class TestSessionLiquidityClassification:
    """Verify all 15 classifications and trend directions match baseline."""

    def test_all_classifications_match(self, result, session_baseline):
        """Each box classification matches baseline exactly."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            props = det.properties
            assert props["type"] == base["type"], (
                f"Box {i}: type mismatch {props['type']} != {base['type']}"
            )
            assert props["forex_day"] == base["forex_day"], (
                f"Box {i}: forex_day mismatch"
            )
            assert props["classification"] == base["classification"], (
                f"Box {i} ({base['type']} {base['forex_day']}): "
                f"classification {props['classification']} != {base['classification']}"
            )

    def test_all_trend_directions_match(self, result, session_baseline):
        """Each box trend_direction matches baseline exactly."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            props = det.properties
            assert props["trend_direction"] == base["trend_direction"], (
                f"Box {i} ({base['type']} {base['forex_day']}): "
                f"trend_direction {props['trend_direction']} != {base['trend_direction']}"
            )

    def test_jan8_classifications(self, result):
        """Jan 8: CONSOL, TREND_UP, TREND_UP."""
        jan8 = [
            d for d in result.detections
            if d.properties["forex_day"] == "2024-01-08"
        ]
        assert len(jan8) == 3
        assert jan8[0].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan8[0].properties["trend_direction"] is None
        assert jan8[1].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan8[1].properties["trend_direction"] == "UP"
        assert jan8[2].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan8[2].properties["trend_direction"] == "UP"

    def test_jan9_classifications(self, result):
        """Jan 9: CONSOL, TREND_DOWN, TREND_DOWN."""
        jan9 = [
            d for d in result.detections
            if d.properties["forex_day"] == "2024-01-09"
        ]
        assert len(jan9) == 3
        assert jan9[0].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan9[1].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan9[1].properties["trend_direction"] == "DOWN"
        assert jan9[2].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan9[2].properties["trend_direction"] == "DOWN"

    def test_jan10_classifications(self, result):
        """Jan 10: CONSOL, TREND_DOWN, CONSOL."""
        jan10 = [
            d for d in result.detections
            if d.properties["forex_day"] == "2024-01-10"
        ]
        assert len(jan10) == 3
        assert jan10[0].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan10[1].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan10[1].properties["trend_direction"] == "DOWN"
        assert jan10[2].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan10[2].properties["trend_direction"] is None

    def test_jan11_classifications(self, result):
        """Jan 11: CONSOL, TREND_UP, TREND_UP."""
        jan11 = [
            d for d in result.detections
            if d.properties["forex_day"] == "2024-01-11"
        ]
        assert len(jan11) == 3
        assert jan11[0].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan11[1].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan11[1].properties["trend_direction"] == "UP"
        assert jan11[2].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan11[2].properties["trend_direction"] == "UP"

    def test_jan12_classifications(self, result):
        """Jan 12: CONSOL, CONSOL, TREND_DOWN."""
        jan12 = [
            d for d in result.detections
            if d.properties["forex_day"] == "2024-01-12"
        ]
        assert len(jan12) == 3
        assert jan12[0].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan12[1].properties["classification"] == "CONSOLIDATION_BOX"
        assert jan12[1].properties["trend_direction"] is None
        assert jan12[2].properties["classification"] == "TREND_OR_EXPANSION"
        assert jan12[2].properties["trend_direction"] == "DOWN"


# ── Range Pips Tests ─────────────────────────────────────────────────────────


class TestSessionLiquidityRangePips:
    """Verify range_pips for all boxes match baseline."""

    def test_all_range_pips_match(self, result, session_baseline):
        """Each box range_pips matches baseline within 0.1 pip tolerance."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["range_pips"] == pytest.approx(
                base["range_pips"], abs=0.15
            ), (
                f"Box {i} ({base['type']} {base['forex_day']}): "
                f"range_pips {det.properties['range_pips']} != {base['range_pips']}"
            )

    def test_asia_range_pips(self, result):
        """Asia range pips: Jan8=22.4, Jan9=17.0, Jan10=10.3, Jan11=11.7, Jan12=12.7."""
        asia = [
            d for d in result.detections
            if d.properties["type"] == "ASIA_BOX"
        ]
        expected = [22.4, 17.0, 10.3, 11.7, 12.7]
        for det, exp in zip(asia, expected):
            assert det.properties["range_pips"] == pytest.approx(exp, abs=0.15)


# ── Field Match Tests ────────────────────────────────────────────────────────


class TestSessionLiquidityFieldMatch:
    """Verify per-box field matching against baseline."""

    def test_high_low_mid_match(self, result, session_baseline):
        """High, low, mid prices match baseline within 1e-6."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            props = det.properties
            assert props["high"] == pytest.approx(base["high"], abs=1e-6), (
                f"Box {i}: high mismatch"
            )
            assert props["low"] == pytest.approx(base["low"], abs=1e-6), (
                f"Box {i}: low mismatch"
            )
            assert props["mid"] == pytest.approx(base["mid"], abs=1e-6), (
                f"Box {i}: mid mismatch"
            )

    def test_efficiency_match(self, result, session_baseline):
        """Efficiency values match baseline within 0.01."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["efficiency"] == pytest.approx(
                base["efficiency"], abs=0.01
            ), f"Box {i}: efficiency mismatch"

    def test_mid_cross_count_match(self, result, session_baseline):
        """Mid cross count matches baseline exactly."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["mid_cross_count"] == base["mid_cross_count"], (
                f"Box {i}: mid_cross_count {det.properties['mid_cross_count']} "
                f"!= {base['mid_cross_count']}"
            )

    def test_balance_score_match(self, result, session_baseline):
        """Balance score matches baseline within 0.01."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["balance_score"] == pytest.approx(
                base["balance_score"], abs=0.01
            ), f"Box {i}: balance_score mismatch"

    def test_start_end_times_match(self, result, session_baseline):
        """Start and end times match baseline."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["start_time"] == base["start_time"], (
                f"Box {i}: start_time mismatch"
            )
            assert det.properties["end_time"] == base["end_time"], (
                f"Box {i}: end_time mismatch"
            )

    def test_net_change_pips_match(self, result, session_baseline):
        """Net change pips match baseline within tolerance."""
        baseline_boxes = session_baseline["boxes"]
        for i, (det, base) in enumerate(
            zip(result.detections, baseline_boxes)
        ):
            assert det.properties["net_change_pips"] == pytest.approx(
                base["net_change_pips"], abs=0.15
            ), f"Box {i}: net_change_pips mismatch"


# ── Interaction Tests ────────────────────────────────────────────────────────


class TestSessionLiquidityInteractions:
    """Verify level interaction tracking matches baseline."""

    def test_interactions_present(self, result):
        """Each box has interaction data for high and low levels."""
        for det in result.detections:
            interactions = det.properties["interactions"]
            assert "high" in interactions
            assert "low" in interactions

    def test_first_box_interactions(self, result, session_baseline):
        """Verify first box (Asia Jan 8) interactions match baseline."""
        det = result.detections[0]
        base = session_baseline["boxes"][0]
        ra_int = det.properties["interactions"]
        base_int = base["interactions"]

        for level_name in ["high", "low"]:
            for event_type in [
                "traded_above",
                "traded_below",
                "closed_above",
                "closed_below",
            ]:
                ra_event = ra_int[level_name][event_type]
                base_event = base_int[level_name][event_type]
                assert ra_event["occurred"] == base_event["occurred"], (
                    f"{level_name}.{event_type}: occurred mismatch"
                )
                assert ra_event["first_time"] == base_event["first_time"], (
                    f"{level_name}.{event_type}: first_time mismatch "
                    f"{ra_event['first_time']} != {base_event['first_time']}"
                )


# ── Detector Interface Tests ─────────────────────────────────────────────────


class TestSessionLiquidityInterface:
    """Verify detector implements PrimitiveDetector ABC correctly."""

    def test_primitive_name(self):
        d = SessionLiquidityDetector()
        assert d.primitive_name == "session_liquidity"

    def test_variant_name(self):
        d = SessionLiquidityDetector()
        assert d.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        d = SessionLiquidityDetector()
        assert d.required_upstream() == []

    def test_result_type(self, result):
        assert isinstance(result, DetectionResult)
        assert result.primitive == "session_liquidity"
        assert result.variant == "a8ra_v1"
