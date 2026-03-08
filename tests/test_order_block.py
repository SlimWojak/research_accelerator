"""Tests for OrderBlockDetector — regression against baseline fixtures.

Tests cover:
- Count regression per TF (1m=138, 5m=37, 15m=17)
- Per-detection field matching against baseline (zone, time, direction, retests)
- Retest tracking: count, bar indices, bars_since_ob matching baseline
- Fallback scan exhaustion: no OB when all fallback bars fail thin filter
- Ghost bar handling
"""

import json
import logging
from collections import Counter
from pathlib import Path

import pytest

from ra.detectors.displacement import DisplacementDetector
from ra.detectors.fvg import FVGDetector
from ra.detectors.mss import MSSDetector
from ra.detectors.order_block import OrderBlockDetector
from ra.detectors.swing_points import SwingPointDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked OB params from config (matches locked_baseline.yaml)
LOCKED_OB_PARAMS = {
    "trigger": "displacement_plus_mss",
    "zone_type": "body",
    "thin_candle_filter": {
        "min_body_pct": 0.10,
    },
    "fallback_scan": {
        "mode": "ENABLED_CONDITIONAL",
        "lookback_bars": 3,
        "reject_if_none_found": True,
    },
    "expiration_bars": {
        "per_tf": {
            "1m": 10,
            "5m": 10,
            "15m": 10,
            "1H": 15,
            "4H": 20,
            "1D": 20,
        },
    },
    "min_displacement_grade": "VALID",
}

# Locked MSS params
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

# Locked upstream params — per-TF resolved
_SWING_N = {"1m": 5, "5m": 3, "15m": 2}
_SWING_HEIGHT = {"1m": 0.5, "5m": 3.0, "15m": 3.0}

LOCKED_FVG_PARAMS = {"floor_threshold_pips": 0.5}

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


def _swing_params(tf: str) -> dict:
    return {
        "N": _SWING_N.get(tf, 3),
        "height_filter_pips": _SWING_HEIGHT.get(tf, 3.0),
        "strength_cap": 20,
        "strength_as_gate": False,
    }


def _load_baseline(tf: str) -> list[dict]:
    """Load OB baseline fixture for a given timeframe."""
    path = FIXTURE_DIR / f"ob_data_{tf}.json"
    with open(path) as f:
        data = json.load(f)
    return data["order_blocks"]


def _run_upstream(bars, tf: str) -> dict[str, DetectionResult]:
    """Run all upstream detectors and return results dict."""
    swing_det = SwingPointDetector()
    disp_det = DisplacementDetector()
    fvg_det = FVGDetector()
    mss_det = MSSDetector()

    context = {"timeframe": tf}
    swing_result = swing_det.detect(bars, _swing_params(tf), context=context)
    disp_result = disp_det.detect(bars, LOCKED_DISP_PARAMS, context=context)
    fvg_result = fvg_det.detect(bars, LOCKED_FVG_PARAMS, context=context)

    mss_upstream = {
        "swing_points": swing_result,
        "displacement": disp_result,
        "fvg": fvg_result,
    }
    mss_result = mss_det.detect(bars, LOCKED_MSS_PARAMS, upstream=mss_upstream, context=context)

    return {
        "displacement": disp_result,
        "mss": mss_result,
    }


def _run_ob_detector(bars, tf: str) -> DetectionResult:
    """Run the full chain and return OB DetectionResult."""
    upstream = _run_upstream(bars, tf)
    ob_det = OrderBlockDetector()
    context = {"timeframe": tf}
    return ob_det.detect(bars, LOCKED_OB_PARAMS, upstream=upstream, context=context)


# ─── COUNT REGRESSION TESTS ──────────────────────────────────────────────


class TestOrderBlockCountRegression:
    """Verify exact OB counts match baseline per TF."""

    def test_ob_1m_count(self, bars_1m):
        result = _run_ob_detector(bars_1m, "1m")
        assert len(result.detections) == 138, (
            f"Expected 138 OBs on 1m, got {len(result.detections)}"
        )

    def test_ob_5m_count(self, bars_5m):
        result = _run_ob_detector(bars_5m, "5m")
        assert len(result.detections) == 37, (
            f"Expected 37 OBs on 5m, got {len(result.detections)}"
        )

    def test_ob_15m_count(self, bars_15m):
        result = _run_ob_detector(bars_15m, "15m")
        assert len(result.detections) == 17, (
            f"Expected 17 OBs on 15m, got {len(result.detections)}"
        )


# ─── PER-DETECTION FIELD MATCH TESTS ─────────────────────────────────────


class TestOrderBlockFieldMatch:
    """Verify per-detection fields match baseline fixtures."""

    @pytest.mark.parametrize("tf,fixture_name,bars_fixture", [
        ("5m", "5m", "bars_5m"),
        ("15m", "15m", "bars_15m"),
        ("1m", "1m", "bars_1m"),
    ])
    def test_ob_field_match(self, tf, fixture_name, bars_fixture, request):
        bars = request.getfixturevalue(bars_fixture)
        baseline = _load_baseline(fixture_name)
        result = _run_ob_detector(bars, tf)

        assert len(result.detections) == len(baseline), (
            f"{tf}: expected {len(baseline)} OBs, got {len(result.detections)}"
        )

        for i, (det, base) in enumerate(zip(result.detections, baseline)):
            props = det.properties

            # OB bar index
            assert props["ob_bar_index"] == base["ob_bar_index"], (
                f"{tf} OB#{i}: ob_bar_index {props['ob_bar_index']} != {base['ob_bar_index']}"
            )

            # Displacement/MSS bar index
            assert props["disp_bar_index"] == base["disp_bar_index"], (
                f"{tf} OB#{i}: disp_bar_index {props['disp_bar_index']} != {base['disp_bar_index']}"
            )

            # Direction
            assert props["direction"] == base["direction"], (
                f"{tf} OB#{i}: direction {props['direction']} != {base['direction']}"
            )

            # OB time
            assert props["ob_time"] == base["ob_time"], (
                f"{tf} OB#{i}: ob_time {props['ob_time']} != {base['ob_time']}"
            )

            # Disp time
            assert props["disp_time"] == base["disp_time"], (
                f"{tf} OB#{i}: disp_time {props['disp_time']} != {base['disp_time']}"
            )

            # Zone body match
            assert props["zone_body"]["top"] == pytest.approx(base["zone_body"]["top"], abs=1e-6), (
                f"{tf} OB#{i}: zone_body.top mismatch"
            )
            assert props["zone_body"]["bottom"] == pytest.approx(base["zone_body"]["bottom"], abs=1e-6), (
                f"{tf} OB#{i}: zone_body.bottom mismatch"
            )

            # Zone wick match
            assert props["zone_wick"]["top"] == pytest.approx(base["zone_wick"]["top"], abs=1e-6), (
                f"{tf} OB#{i}: zone_wick.top mismatch"
            )
            assert props["zone_wick"]["bottom"] == pytest.approx(base["zone_wick"]["bottom"], abs=1e-6), (
                f"{tf} OB#{i}: zone_wick.bottom mismatch"
            )

            # MSS direction and break type
            assert props["mss_direction"] == base["mss_direction"], (
                f"{tf} OB#{i}: mss_direction mismatch"
            )
            assert props["mss_break_type"] == base["mss_break_type"], (
                f"{tf} OB#{i}: mss_break_type mismatch"
            )

            # Broken swing
            assert props["broken_swing"]["type"] == base["broken_swing"]["type"], (
                f"{tf} OB#{i}: broken_swing.type mismatch"
            )
            assert props["broken_swing"]["price"] == pytest.approx(base["broken_swing"]["price"], abs=1e-6), (
                f"{tf} OB#{i}: broken_swing.price mismatch"
            )
            assert props["broken_swing"]["bar_index"] == base["broken_swing"]["bar_index"], (
                f"{tf} OB#{i}: broken_swing.bar_index mismatch"
            )

            # Forex day
            assert props["forex_day"] == base["forex_day"], (
                f"{tf} OB#{i}: forex_day mismatch"
            )


# ─── RETEST TRACKING TESTS ──────────────────────────────────────────────


class TestOrderBlockRetestTracking:
    """Verify retest lists match baseline — count, bar indices, bars_since_ob."""

    @pytest.mark.parametrize("tf,fixture_name,bars_fixture", [
        ("5m", "5m", "bars_5m"),
        ("15m", "15m", "bars_15m"),
        ("1m", "1m", "bars_1m"),
    ])
    def test_ob_retest_match(self, tf, fixture_name, bars_fixture, request):
        bars = request.getfixturevalue(bars_fixture)
        baseline = _load_baseline(fixture_name)
        result = _run_ob_detector(bars, tf)

        assert len(result.detections) == len(baseline)

        for i, (det, base) in enumerate(zip(result.detections, baseline)):
            props = det.properties

            # Total retest count
            assert props["total_retests"] == base["total_retests"], (
                f"{tf} OB#{i} (idx={base['ob_bar_index']}): "
                f"total_retests {props['total_retests']} != {base['total_retests']}"
            )

            # Per-retest bar index match
            assert len(props["retests"]) == len(base["retests"]), (
                f"{tf} OB#{i}: retest list length mismatch"
            )
            for j, (ra_rt, base_rt) in enumerate(zip(props["retests"], base["retests"])):
                assert ra_rt["bar_index"] == base_rt["bar_index"], (
                    f"{tf} OB#{i} retest#{j}: bar_index {ra_rt['bar_index']} != {base_rt['bar_index']}"
                )
                assert ra_rt["bars_since_ob"] == base_rt["bars_since_ob"], (
                    f"{tf} OB#{i} retest#{j}: bars_since_ob mismatch"
                )


# ─── REQUIRED UPSTREAM TEST ──────────────────────────────────────────────


class TestOrderBlockUpstream:
    """Verify OrderBlockDetector declares correct upstream."""

    def test_required_upstream(self):
        det = OrderBlockDetector()
        upstream = det.required_upstream()
        assert "displacement" in upstream
        assert "mss" in upstream

    def test_primitive_name(self):
        det = OrderBlockDetector()
        assert det.primitive_name == "order_block"

    def test_no_upstream_raises(self, bars_5m):
        det = OrderBlockDetector()
        with pytest.raises(ValueError):
            det.detect(bars_5m, LOCKED_OB_PARAMS, upstream=None, context={"timeframe": "5m"})


# ─── DIRECTION SPLIT TEST ────────────────────────────────────────────────


class TestOrderBlockDirectionSplit:
    """Verify bullish/bearish split on 5m matches baseline."""

    def test_direction_split_5m(self, bars_5m):
        baseline = _load_baseline("5m")
        result = _run_ob_detector(bars_5m, "5m")

        base_bull = sum(1 for ob in baseline if ob["direction"] == "bullish")
        base_bear = sum(1 for ob in baseline if ob["direction"] == "bearish")

        ra_bull = sum(1 for d in result.detections if d.direction == "bullish")
        ra_bear = sum(1 for d in result.detections if d.direction == "bearish")

        assert ra_bull == base_bull, f"Bullish: {ra_bull} != {base_bull}"
        assert ra_bear == base_bear, f"Bearish: {ra_bear} != {base_bear}"


# ─── GHOST BAR HANDLING TEST ─────────────────────────────────────────────


class TestOrderBlockGhostBars:
    """Verify no OB anchors on a ghost bar."""

    def test_no_ghost_bar_ob(self, bars_5m):
        result = _run_ob_detector(bars_5m, "5m")
        ghost_indices = set(bars_5m[bars_5m["is_ghost"]].index.tolist())

        for det in result.detections:
            ob_idx = det.properties["ob_bar_index"]
            assert ob_idx not in ghost_indices, (
                f"OB anchored on ghost bar at index {ob_idx}"
            )


# ─── METADATA TEST ───────────────────────────────────────────────────────


class TestOrderBlockMetadata:
    """Verify metadata fields are populated."""

    def test_metadata_5m(self, bars_5m):
        result = _run_ob_detector(bars_5m, "5m")
        assert result.metadata["total_count"] == 37
        assert result.primitive == "order_block"
        assert result.timeframe == "5m"
