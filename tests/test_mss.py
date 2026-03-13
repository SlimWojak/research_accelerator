"""Tests for MSSDetector — regression against baseline fixtures.

Tests cover:
- Count regression per TF (1m, 5m, 15m)
- Break type split (REVERSAL/CONTINUATION)
- FVG-tagged count
- Per-detection field matching against baseline
- Window_used distribution matches baseline
- Impulse suppression behavior
- Cluster-straddle displacement indexing
- Ghost bar handling
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from ra.detectors.displacement import DisplacementDetector
from ra.detectors.fvg import FVGDetector
from ra.detectors.mss import MSSDetector
from ra.detectors.swing_points import SwingPointDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked MSS params from config (matches locked_baseline.yaml)
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

# Locked upstream params — per-TF resolved (swing expects plain int for N)
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


def _load_baseline(tf: str) -> list[dict]:
    """Load baseline MSS fixture for a given TF."""
    path = FIXTURE_DIR / f"mss_data_{tf}.json"
    with open(path) as f:
        data = json.load(f)
    return data["mss_events"]


def _run_upstream(bars, tf: str) -> dict[str, DetectionResult]:
    """Run all upstream detectors and return results dict."""
    swing_det = SwingPointDetector()
    disp_det = DisplacementDetector()
    fvg_det = FVGDetector()

    context = {"timeframe": tf}
    swing_result = swing_det.detect(bars, _swing_params(tf), context=context)
    disp_result = disp_det.detect(bars, LOCKED_DISP_PARAMS, context=context)
    fvg_result = fvg_det.detect(bars, LOCKED_FVG_PARAMS, context=context)

    return {
        "swing_points": swing_result,
        "displacement": disp_result,
        "fvg": fvg_result,
    }


def _run_mss(bars, tf: str) -> DetectionResult:
    """Run MSS detector with upstream results."""
    upstream = _run_upstream(bars, tf)
    detector = MSSDetector()
    context = {"timeframe": tf}
    return detector.detect(bars, LOCKED_MSS_PARAMS, upstream=upstream, context=context)


# ──────────────────────────────────────────────────────────────────────
# Count regression tests
# ──────────────────────────────────────────────────────────────────────

class TestMSS1mCount:
    """1m regression: 179 total (88 reversal, 91 continuation, 129 FVG-tagged)."""

    def test_total_count(self, bars_1m):
        result = _run_mss(bars_1m, "1m")
        assert len(result.detections) == 179

    def test_reversal_count(self, bars_1m):
        result = _run_mss(bars_1m, "1m")
        rev = [d for d in result.detections if d.properties["break_type"] == "REVERSAL"]
        assert len(rev) == 88

    def test_continuation_count(self, bars_1m):
        result = _run_mss(bars_1m, "1m")
        cont = [d for d in result.detections if d.properties["break_type"] == "CONTINUATION"]
        assert len(cont) == 91

    def test_fvg_tagged_count(self, bars_1m):
        result = _run_mss(bars_1m, "1m")
        fvg = [d for d in result.detections if d.properties["fvg_created"]]
        assert len(fvg) == 129


class TestMSS5mCount:
    """5m regression: 44 total (20 reversal, 24 continuation, 35 FVG-tagged)."""

    def test_total_count(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        assert len(result.detections) == 44

    def test_reversal_count(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        rev = [d for d in result.detections if d.properties["break_type"] == "REVERSAL"]
        assert len(rev) == 20

    def test_continuation_count(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        cont = [d for d in result.detections if d.properties["break_type"] == "CONTINUATION"]
        assert len(cont) == 24

    def test_fvg_tagged_count(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        fvg = [d for d in result.detections if d.properties["fvg_created"]]
        assert len(fvg) == 35


class TestMSS15mCount:
    """15m regression: 20 total (10 reversal, 10 continuation, 17 FVG-tagged)."""

    def test_total_count(self, bars_15m):
        result = _run_mss(bars_15m, "15m")
        assert len(result.detections) == 20

    def test_reversal_count(self, bars_15m):
        result = _run_mss(bars_15m, "15m")
        rev = [d for d in result.detections if d.properties["break_type"] == "REVERSAL"]
        assert len(rev) == 10

    def test_continuation_count(self, bars_15m):
        result = _run_mss(bars_15m, "15m")
        cont = [d for d in result.detections if d.properties["break_type"] == "CONTINUATION"]
        assert len(cont) == 10

    def test_fvg_tagged_count(self, bars_15m):
        result = _run_mss(bars_15m, "15m")
        fvg = [d for d in result.detections if d.properties["fvg_created"]]
        assert len(fvg) == 17


# ──────────────────────────────────────────────────────────────────────
# Per-detection field match tests
# ──────────────────────────────────────────────────────────────────────

class TestMSS5mFieldMatch:
    """Per-detection field matching for 5m against baseline fixture."""

    def test_field_match(self, bars_5m):
        baseline = _load_baseline("5m")
        result = _run_mss(bars_5m, "5m")

        assert len(result.detections) == len(baseline), (
            f"Count mismatch: got {len(result.detections)}, expected {len(baseline)}"
        )

        for idx, (det, bl) in enumerate(zip(result.detections, baseline)):
            props = det.properties
            # Direction
            assert props["direction"] == bl["direction"], (
                f"Event {idx}: direction {props['direction']} != {bl['direction']}"
            )
            # Break type
            assert props["break_type"] == bl["break_type"], (
                f"Event {idx}: break_type {props['break_type']} != {bl['break_type']}"
            )
            # Bar index
            assert props["bar_index"] == bl["bar_index"], (
                f"Event {idx}: bar_index {props['bar_index']} != {bl['bar_index']}"
            )
            # Time
            assert props["time"] == bl["time"], (
                f"Event {idx}: time {props['time']} != {bl['time']}"
            )
            # Window used
            assert props["window_used"] == bl["window_used"], (
                f"Event {idx}: window_used {props['window_used']} != {bl['window_used']}"
            )
            # FVG created
            assert props["fvg_created"] == bl["fvg_created"], (
                f"Event {idx}: fvg_created {props['fvg_created']} != {bl['fvg_created']}"
            )
            # Broken swing
            bl_swing = bl["broken_swing"]
            det_swing = props["broken_swing"]
            assert det_swing["type"] == bl_swing["type"], (
                f"Event {idx}: swing type {det_swing['type']} != {bl_swing['type']}"
            )
            assert abs(det_swing["price"] - bl_swing["price"]) < 1e-6, (
                f"Event {idx}: swing price {det_swing['price']} != {bl_swing['price']}"
            )
            assert det_swing["bar_index"] == bl_swing["bar_index"], (
                f"Event {idx}: swing bar_index {det_swing['bar_index']} != {bl_swing['bar_index']}"
            )
            # Displacement info
            bl_disp = bl["displacement"]
            det_disp = props["displacement"]
            assert abs(det_disp["atr_multiple"] - bl_disp["atr_multiple"]) < 1e-3, (
                f"Event {idx}: atr_multiple {det_disp['atr_multiple']} != {bl_disp['atr_multiple']}"
            )
            assert det_disp["displacement_type"] == bl_disp["displacement_type"], (
                f"Event {idx}: displacement_type {det_disp['displacement_type']} != {bl_disp['displacement_type']}"
            )
            assert det_disp["path"] == bl_disp["path"], (
                f"Event {idx}: path {det_disp['path']} != {bl_disp['path']}"
            )
            # Session
            assert props["session"] == bl["session"], (
                f"Event {idx}: session {props['session']} != {bl['session']}"
            )
            # Forex day
            assert props["forex_day"] == bl["forex_day"], (
                f"Event {idx}: forex_day {props['forex_day']} != {bl['forex_day']}"
            )


class TestMSS1mFieldMatch:
    """Per-detection field matching for 1m against baseline fixture."""

    def test_field_match(self, bars_1m):
        baseline = _load_baseline("1m")
        result = _run_mss(bars_1m, "1m")

        assert len(result.detections) == len(baseline)

        for idx, (det, bl) in enumerate(zip(result.detections, baseline)):
            props = det.properties
            assert props["direction"] == bl["direction"], f"Event {idx}: direction mismatch"
            assert props["break_type"] == bl["break_type"], f"Event {idx}: break_type mismatch"
            assert props["bar_index"] == bl["bar_index"], f"Event {idx}: bar_index mismatch"
            assert props["time"] == bl["time"], f"Event {idx}: time mismatch"
            assert props["window_used"] == bl["window_used"], f"Event {idx}: window_used mismatch"
            assert props["fvg_created"] == bl["fvg_created"], f"Event {idx}: fvg_created mismatch"


class TestMSS15mFieldMatch:
    """Per-detection field matching for 15m against baseline fixture."""

    def test_field_match(self, bars_15m):
        baseline = _load_baseline("15m")
        result = _run_mss(bars_15m, "15m")

        assert len(result.detections) == len(baseline)

        for idx, (det, bl) in enumerate(zip(result.detections, baseline)):
            props = det.properties
            assert props["direction"] == bl["direction"], f"Event {idx}: direction mismatch"
            assert props["break_type"] == bl["break_type"], f"Event {idx}: break_type mismatch"
            assert props["bar_index"] == bl["bar_index"], f"Event {idx}: bar_index mismatch"
            assert props["time"] == bl["time"], f"Event {idx}: time mismatch"
            assert props["window_used"] == bl["window_used"], f"Event {idx}: window_used mismatch"
            assert props["fvg_created"] == bl["fvg_created"], f"Event {idx}: fvg_created mismatch"


# ──────────────────────────────────────────────────────────────────────
# Window used distribution test
# ──────────────────────────────────────────────────────────────────────

class TestMSSWindowUsedDistribution:
    """Verify window_used distribution matches baseline."""

    def test_window_used_5m(self, bars_5m):
        baseline = _load_baseline("5m")
        result = _run_mss(bars_5m, "5m")

        bl_dist = Counter(e["window_used"] for e in baseline)
        det_dist = Counter(d.properties["window_used"] for d in result.detections)
        assert det_dist == bl_dist, f"Window dist mismatch: got {dict(det_dist)}, expected {dict(bl_dist)}"

    def test_window_used_1m(self, bars_1m):
        baseline = _load_baseline("1m")
        result = _run_mss(bars_1m, "1m")

        bl_dist = Counter(e["window_used"] for e in baseline)
        det_dist = Counter(d.properties["window_used"] for d in result.detections)
        assert det_dist == bl_dist, f"Window dist mismatch: got {dict(det_dist)}, expected {dict(bl_dist)}"

    def test_window_used_15m(self, bars_15m):
        baseline = _load_baseline("15m")
        result = _run_mss(bars_15m, "15m")

        bl_dist = Counter(e["window_used"] for e in baseline)
        det_dist = Counter(d.properties["window_used"] for d in result.detections)
        assert det_dist == bl_dist, f"Window dist mismatch: got {dict(det_dist)}, expected {dict(bl_dist)}"


# ──────────────────────────────────────────────────────────────────────
# Cluster-straddle indexing test (VAL-MSS-006)
# ──────────────────────────────────────────────────────────────────────

class TestMSSClusterStraddle:
    """Verify cluster-straddle displacement indexing works correctly."""

    def test_cluster_straddle_5m(self, bars_5m):
        """At least one MSS event with CLUSTER_2 and window_used=-1 exists on 5m."""
        baseline = _load_baseline("5m")
        result = _run_mss(bars_5m, "5m")

        # Find cluster-straddle cases (window_used == -1 with CLUSTER_2)
        bl_straddle = [
            e for e in baseline
            if e["window_used"] == -1
            and e["displacement"]["displacement_type"] == "CLUSTER_2"
        ]
        det_straddle = [
            d for d in result.detections
            if d.properties["window_used"] == -1
            and d.properties["displacement"]["displacement_type"] == "CLUSTER_2"
        ]
        assert len(det_straddle) == len(bl_straddle), (
            f"Cluster straddle count mismatch: got {len(det_straddle)}, expected {len(bl_straddle)}"
        )


# ──────────────────────────────────────────────────────────────────────
# Ghost bar handling test
# ──────────────────────────────────────────────────────────────────────

class TestMSSGhostBars:
    """Verify no MSS detection anchors on a ghost bar."""

    def test_no_ghost_bar_detections(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        ghost_indices = set(bars_5m[bars_5m["is_ghost"]].index.tolist())
        for det in result.detections:
            assert det.properties["bar_index"] not in ghost_indices, (
                f"MSS detected at ghost bar index {det.properties['bar_index']}"
            )


# ──────────────────────────────────────────────────────────────────────
# Origin candle + extreme_candle propagation tests
# ──────────────────────────────────────────────────────────────────────

class TestMSSOriginCandle:
    """Verify origin_candle fields populated on every MSS event."""

    def test_origin_candle_present_5m(self, bars_5m):
        result = _run_mss(bars_5m, "5m")
        for d in result.detections:
            oc = d.properties.get("origin_candle")
            assert oc is not None, f"Missing origin_candle at bar {d.properties['bar_index']}"
            for key in ("body_high", "body_low", "wick_high", "wick_low"):
                assert key in oc, f"Missing origin_candle.{key}"

    def test_origin_candle_body_is_max_min_of_open_close_5m(self, bars_5m):
        """body_high = max(open, close), body_low = min(open, close) of break bar."""
        opens = bars_5m["open"].values
        closes = bars_5m["close"].values
        highs = bars_5m["high"].values
        lows = bars_5m["low"].values
        result = _run_mss(bars_5m, "5m")
        for d in result.detections:
            oc = d.properties["origin_candle"]
            i = d.properties["bar_index"]
            assert abs(oc["body_high"] - max(opens[i], closes[i])) < 1e-10
            assert abs(oc["body_low"] - min(opens[i], closes[i])) < 1e-10
            assert abs(oc["wick_high"] - highs[i]) < 1e-10
            assert abs(oc["wick_low"] - lows[i]) < 1e-10

    def test_extreme_candle_propagated_5m(self, bars_5m):
        """displacement.extreme_candle is propagated through to MSS event."""
        result = _run_mss(bars_5m, "5m")
        for d in result.detections:
            ec = d.properties["displacement"].get("extreme_candle")
            assert ec is not None, f"Missing displacement.extreme_candle at bar {d.properties['bar_index']}"
            for key in ("body_high", "body_low", "wick_high", "wick_low"):
                assert key in ec, f"Missing displacement.extreme_candle.{key}"

    def test_origin_candle_present_1m(self, bars_1m):
        result = _run_mss(bars_1m, "1m")
        for d in result.detections:
            assert d.properties.get("origin_candle") is not None


# ──────────────────────────────────────────────────────────────────────
# Required upstream test
# ──────────────────────────────────────────────────────────────────────

class TestMSSInterface:
    """Verify MSSDetector implements PrimitiveDetector correctly."""

    def test_required_upstream(self):
        detector = MSSDetector()
        upstream = detector.required_upstream()
        assert "swing_points" in upstream
        assert "displacement" in upstream
        assert "fvg" in upstream

    def test_primitive_name(self):
        detector = MSSDetector()
        assert detector.primitive_name == "mss"
        assert detector.variant_name == "a8ra_v1"
