"""Tests for OTEDetector — fib retracement zones anchored to MSS events.

Tests cover:
- 44 OTE zones on 5m (one per MSS event)
- Each zone has 3 fib levels: 0.618 (lower), 0.705 (sweet_spot), 0.79 (upper)
- Kill zone gate: actionable flag only set within LOKZ/NYOKZ
- Correct fib level calculations from MSS dealing range
- Detector implements PrimitiveDetector ABC
"""

import json
from pathlib import Path

import pytest

from ra.detectors.displacement import DisplacementDetector
from ra.detectors.fvg import FVGDetector
from ra.detectors.mss import MSSDetector
from ra.detectors.ote import OTEDetector
from ra.detectors.swing_points import SwingPointDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked params from locked_baseline.yaml
LOCKED_OTE_PARAMS = {
    "fib_levels": {
        "lower": 0.618,
        "sweet_spot": 0.705,
        "upper": 0.79,
    },
    "anchor_rule": "most_recent_mss",
    "kill_zone_gate": True,
}

# Locked upstream params (same as test_mss.py)
_SWING_N = {"1m": 5, "5m": 3, "15m": 2}
_SWING_HEIGHT = {"1m": 0.5, "5m": 3.0, "15m": 3.0}


def _swing_params(tf: str) -> dict:
    return {
        "N": _SWING_N.get(tf, 3),
        "height_filter_pips": _SWING_HEIGHT.get(tf, 3.0),
        "strength_cap": 20,
        "strength_as_gate": False,
    }


LOCKED_DISP_PARAMS = {
    "atr_period": 14,
    "combination_mode": "AND",
    "ltf": {
        "applies_to": ["1m", "5m", "15m"],
        "atr_multiplier": 1.50,
        "body_ratio": 0.60,
        "close_gate": 0.25,
        "structure_close_required": False,
    },
    "htf": {
        "applies_to": ["1H", "4H", "1D"],
        "atr_multiplier": 1.50,
        "body_ratio": 0.65,
        "close_gate": 0.25,
        "structure_close_required": True,
    },
    "decisive_override": {
        "enabled": True,
        "body_min": 0.75,
        "close_max": 0.10,
        "pip_floor": {
            "1m": 3.0, "5m": 5.0, "15m": 6.0,
            "1H": 8.0, "4H": 15.0, "1D": 20.0,
        },
    },
    "cluster": {
        "cluster_2_enabled": True,
        "cluster_3_enabled": False,
        "net_efficiency_min": 0.65,
        "overlap_max": 0.35,
    },
    "quality_grades": {
        "STRONG": {"atr_ratio_min": 2.0},
        "VALID": {"atr_ratio_min": 1.5},
        "WEAK": {"atr_ratio_min": 1.25},
    },
    "evaluation_order": ["check_cluster_2", "check_single_atr", "check_single_override"],
}

LOCKED_FVG_PARAMS = {
    "floor_threshold_pips": 0.5,
}

LOCKED_MSS_PARAMS = {
    "ltf": {
        "applies_to": ["1m", "5m", "15m"],
        "displacement_required": True,
        "confirmation_window_bars": 3,
        "close_beyond_swing": True,
        "impulse_suppression": {
            "pullback_reset_pips": 5,
            "pullback_reset_atr_factor": 0.25,
            "opposite_displacement_reset": True,
            "new_day_reset": True,
        },
    },
    "htf": {
        "applies_to": ["1H", "4H", "1D"],
        "displacement_required": True,
        "confirmation_window_bars": 1,
        "close_beyond_swing": True,
        "structure_close_required": True,
        "impulse_suppression": {
            "pullback_reset_pips": 5,
            "pullback_reset_atr_factor": 0.25,
            "opposite_displacement_reset": True,
            "new_day_reset": True,
        },
    },
    "fvg_tag_only": True,
    "break_classification": ["REVERSAL", "CONTINUATION"],
    "swing_consumption": True,
}


def _run_mss_upstream(bars, tf: str) -> dict[str, DetectionResult]:
    """Run all upstream detectors needed for MSS -> OTE chain."""
    swing_det = SwingPointDetector()
    disp_det = DisplacementDetector()
    fvg_det = FVGDetector()
    mss_det = MSSDetector()

    swing_result = swing_det.detect(bars, _swing_params(tf), context={"timeframe": tf})
    disp_result = disp_det.detect(bars, LOCKED_DISP_PARAMS, context={"timeframe": tf})
    fvg_result = fvg_det.detect(bars, LOCKED_FVG_PARAMS, context={"timeframe": tf})

    upstream_mss = {
        "swing_points": swing_result,
        "displacement": disp_result,
        "fvg": fvg_result,
    }
    mss_result = mss_det.detect(bars, LOCKED_MSS_PARAMS, upstream=upstream_mss, context={"timeframe": tf})

    return {"mss": mss_result}


def _load_mss_baseline(tf: str) -> list[dict]:
    """Load baseline MSS fixture for a given TF."""
    path = FIXTURE_DIR / f"mss_data_{tf}.json"
    with open(path) as f:
        data = json.load(f)
    return data["mss_events"]


@pytest.fixture(scope="module")
def ote_result_5m(bars_5m):
    """Run OTEDetector on 5m bars."""
    upstream = _run_mss_upstream(bars_5m, "5m")
    detector = OTEDetector()
    return detector.detect(bars_5m, LOCKED_OTE_PARAMS, upstream=upstream, context={"timeframe": "5m"})


# ─── Count regression tests ──────────────────────────────────────────────

class TestOTEZoneCount:
    """OTE detector produces one zone per MSS event."""

    def test_5m_zone_count(self, ote_result_5m):
        """44 OTE zones on 5m (one per MSS)."""
        assert len(ote_result_5m.detections) == 44, \
            f"Expected 44 OTE zones, got {len(ote_result_5m.detections)}"

    def test_each_zone_has_three_fib_levels(self, ote_result_5m):
        """Each zone has lower (0.618), sweet_spot (0.705), upper (0.79)."""
        for det in ote_result_5m.detections:
            fib_levels = det.properties.get("fib_levels", {})
            assert "lower" in fib_levels, f"Missing 'lower' level in {det.id}"
            assert "sweet_spot" in fib_levels, f"Missing 'sweet_spot' level in {det.id}"
            assert "upper" in fib_levels, f"Missing 'upper' level in {det.id}"


# ─── Fib level calculation tests ─────────────────────────────────────────

class TestOTEFibCalculation:
    """Verify fib levels are computed correctly from MSS dealing range."""

    def test_fib_levels_within_dealing_range(self, ote_result_5m):
        """All fib levels should be between swing price and break price."""
        for det in ote_result_5m.detections:
            fib_levels = det.properties.get("fib_levels", {})
            swing_price = det.properties.get("swing_price")
            break_price = det.properties.get("break_price")
            if swing_price is None or break_price is None:
                continue

            low = min(swing_price, break_price)
            high = max(swing_price, break_price)

            for level_name, level_price in fib_levels.items():
                assert low <= level_price <= high, \
                    f"Fib level {level_name}={level_price} outside range [{low}, {high}] for {det.id}"

    def test_fib_level_ordering(self, ote_result_5m):
        """Fib levels at 0.618 < 0.705 < 0.79 represent deeper retracement.
           For bullish: lower > sweet_spot > upper (lower is closest to break, upper deepest).
           For bearish: lower < sweet_spot < upper (lower is closest to break, upper deepest)."""
        for det in ote_result_5m.detections:
            fib_levels = det.properties.get("fib_levels", {})
            direction = det.direction

            if direction == "bullish":
                # Retracement DOWN from break: 0.618 retrace > 0.705 retrace > 0.79 retrace
                # lower (0.618) is highest price, upper (0.79) is lowest price
                assert fib_levels["lower"] >= fib_levels["sweet_spot"] >= fib_levels["upper"], \
                    f"Bullish fib ordering wrong for {det.id}: {fib_levels}"
            elif direction == "bearish":
                # Retracement UP from break: 0.618 retrace < 0.705 retrace < 0.79 retrace
                # lower (0.618) is lowest price, upper (0.79) is highest price
                assert fib_levels["lower"] <= fib_levels["sweet_spot"] <= fib_levels["upper"], \
                    f"Bearish fib ordering wrong for {det.id}: {fib_levels}"


# ─── Kill zone gate tests ────────────────────────────────────────────────

class TestOTEKillZoneGate:
    """OTE zones only actionable within LOKZ (02:00-05:00) or NYOKZ (07:00-10:00)."""

    def test_actionable_only_in_kill_zones(self, ote_result_5m):
        """Zones flagged actionable must be in LOKZ or NYOKZ."""
        for det in ote_result_5m.detections:
            if det.properties.get("actionable"):
                session = det.tags.get("session", "")
                assert session in ("lokz", "nyokz"), \
                    f"Actionable zone {det.id} in session '{session}' — expected lokz or nyokz"

    def test_non_kz_zones_not_actionable(self, ote_result_5m):
        """Zones outside kill zones should NOT be actionable."""
        for det in ote_result_5m.detections:
            session = det.tags.get("session", "")
            if session not in ("lokz", "nyokz"):
                assert not det.properties.get("actionable"), \
                    f"Zone {det.id} in session '{session}' should not be actionable"

    def test_some_zones_are_actionable(self, ote_result_5m):
        """At least some zones should be actionable (sanity check)."""
        actionable = [d for d in ote_result_5m.detections if d.properties.get("actionable")]
        assert len(actionable) > 0, "No actionable OTE zones found"

    def test_some_zones_are_not_actionable(self, ote_result_5m):
        """At least some zones should NOT be actionable (sanity check)."""
        non_actionable = [d for d in ote_result_5m.detections if not d.properties.get("actionable")]
        assert len(non_actionable) > 0, "All OTE zones are actionable — expected some outside KZ"


# ─── MSS anchor consistency tests ────────────────────────────────────────

class TestOTEMSSAnchoring:
    """OTE zones are correctly anchored to MSS events."""

    def test_each_zone_references_mss(self, ote_result_5m):
        """Each OTE zone should reference an MSS event."""
        for det in ote_result_5m.detections:
            assert det.properties.get("mss_bar_index") is not None, \
                f"OTE zone {det.id} missing mss_bar_index"
            assert det.properties.get("mss_direction") is not None, \
                f"OTE zone {det.id} missing mss_direction"

    def test_zone_direction_matches_mss(self, ote_result_5m):
        """OTE zone direction should match the MSS direction."""
        for det in ote_result_5m.detections:
            assert det.direction == det.properties.get("mss_direction", "").lower(), \
                f"Direction mismatch for {det.id}: {det.direction} vs {det.properties.get('mss_direction')}"


# ─── Detector interface tests ────────────────────────────────────────────

class TestOTEInterface:
    """Verify detector implements PrimitiveDetector correctly."""

    def test_primitive_name(self):
        det = OTEDetector()
        assert det.primitive_name == "ote"

    def test_variant_name(self):
        det = OTEDetector()
        assert det.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        det = OTEDetector()
        assert det.required_upstream() == ["mss"]

    def test_result_is_detection_result(self, ote_result_5m):
        assert isinstance(ote_result_5m, DetectionResult)
        assert ote_result_5m.primitive == "ote"
        assert ote_result_5m.variant == "a8ra_v1"
        assert ote_result_5m.timeframe == "5m"
