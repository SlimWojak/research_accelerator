"""Tests for HTFLiquidityDetector — regression against baseline fixture.

Tests cover:
- H1: 3 pools (2 untouched, 1 taken) from 34 fractal swings (120 bars)
- H4: 1 pool (1 untouched, 0 taken) from 9 fractal swings (31 bars)
- D1: 0 pools (too short for fractal detection)
- W1: 0 pools (too short)
- Per-pool field matching (price, touches, formation time, status)
- Pool touch prices match baseline
- Summary metadata correctness
"""

import json
from pathlib import Path

import pytest

from ra.detectors.htf_liquidity import HTFLiquidityDetector
from ra.engine.base import DetectionResult

# Path to baseline fixtures
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baseline_output"

# Locked HTF Liquidity params from locked_baseline.yaml
LOCKED_HTF_PARAMS = {
    "detection_source": "swing_points_fractal_2_2",
    "price_tolerance_pips": {
        "per_tf": {
            "1H": 2,
            "4H": 3,
            "1D": 5,
            "W1": 10,
            "MN": 15,
        },
    },
    "min_bars_between_touches": {
        "per_tf": {
            "1H": 6,
            "4H": 3,
            "1D": 2,
            "W1": 2,
            "MN": 2,
        },
    },
    "rotation_required": {
        "per_tf": {
            "1H": {"pip_floor": 5, "atr_factor": 0.25},
            "4H": {"pip_floor": 8, "atr_factor": 0.25},
            "1D": {"pip_floor": 12, "atr_factor": 0.25},
            "W1": {"pip_floor": 20, "atr_factor": 0.25},
            "MN": {"pip_floor": 30, "atr_factor": 0.25},
        },
    },
    "max_lookback": {
        "per_tf": {
            "1H": 500,
            "4H": 300,
            "1D": 180,
            "W1": 104,
            "MN": 60,
        },
    },
    "asia_range_filter": True,
    "invalidation_during_formation": True,
    "merge_tolerance_factor": 1.5,
    "min_touches": 2,
}


def _load_baseline() -> dict:
    """Load HTF liquidity baseline fixture."""
    path = FIXTURE_DIR / "htf_liquidity.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def baseline():
    return _load_baseline()


@pytest.fixture(scope="module")
def htf_result(bars_1m):
    """Run HTFLiquidityDetector on the 5-day dataset."""
    detector = HTFLiquidityDetector()
    result = detector.detect(bars_1m, LOCKED_HTF_PARAMS)
    return result


# ─── Count regression tests ──────────────────────────────────────────────

class TestHTFLiquidityH1Counts:
    """H1: 3 pools (2 untouched, 1 taken) from 34 swings."""

    def test_h1_pool_count(self, htf_result, baseline):
        h1_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H1"]
        assert len(h1_pools) == 3, f"Expected 3 H1 pools, got {len(h1_pools)}"

    def test_h1_untouched_count(self, htf_result):
        h1_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H1"]
        untouched = [p for p in h1_pools if p.properties.get("status") == "UNTOUCHED"]
        assert len(untouched) == 2

    def test_h1_taken_count(self, htf_result):
        h1_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H1"]
        taken = [p for p in h1_pools if p.properties.get("status") == "TAKEN"]
        assert len(taken) == 1

    def test_h1_swings_in_summary(self, htf_result, baseline):
        assert htf_result.metadata["H1"]["swings"] == baseline["summary"]["H1"]["swings"]
        assert htf_result.metadata["H1"]["swings"] == 34

    def test_h1_bars_in_summary(self, htf_result, baseline):
        assert htf_result.metadata["H1"]["bars"] == baseline["summary"]["H1"]["bars"]
        assert htf_result.metadata["H1"]["bars"] == 120


class TestHTFLiquidityH4Counts:
    """H4: 1 pool (1 untouched, 0 taken) from 9 swings."""

    def test_h4_pool_count(self, htf_result, baseline):
        h4_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H4"]
        assert len(h4_pools) == 1

    def test_h4_untouched_count(self, htf_result):
        h4_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H4"]
        untouched = [p for p in h4_pools if p.properties.get("status") == "UNTOUCHED"]
        assert len(untouched) == 1

    def test_h4_taken_count(self, htf_result):
        h4_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "H4"]
        taken = [p for p in h4_pools if p.properties.get("status") == "TAKEN"]
        assert len(taken) == 0

    def test_h4_swings_in_summary(self, htf_result, baseline):
        assert htf_result.metadata["H4"]["swings"] == baseline["summary"]["H4"]["swings"]
        assert htf_result.metadata["H4"]["swings"] == 9

    def test_h4_bars_in_summary(self, htf_result, baseline):
        assert htf_result.metadata["H4"]["bars"] == baseline["summary"]["H4"]["bars"]
        assert htf_result.metadata["H4"]["bars"] == 31


class TestHTFLiquidityD1W1:
    """D1 and W1 should produce 0 pools."""

    def test_d1_zero_pools(self, htf_result, baseline):
        d1_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "D1"]
        assert len(d1_pools) == 0

    def test_d1_zero_swings(self, htf_result, baseline):
        assert htf_result.metadata["D1"]["swings"] == 0

    def test_w1_zero_pools(self, htf_result, baseline):
        w1_pools = [d for d in htf_result.detections
                     if d.properties.get("timeframe") == "W1"]
        assert len(w1_pools) == 0

    def test_w1_zero_swings(self, htf_result, baseline):
        assert htf_result.metadata["W1"]["swings"] == 0


# ─── Field match tests ────────────────────────────────────────────────────

class TestHTFLiquidityFieldMatch:
    """Per-pool field matching against baseline fixture."""

    def test_pool_fields_match_baseline(self, htf_result, baseline):
        """All pools match baseline on type, timeframe, price, touches, status."""
        baseline_pools = baseline["pools"]
        det_pools = htf_result.detections

        # Sort both for comparison
        def _sort_key(p):
            if isinstance(p, dict):
                return (p["timeframe"], p["type"], p["price"])
            return (p.properties["timeframe"], p.properties["type"], p.price)

        baseline_sorted = sorted(baseline_pools, key=_sort_key)
        det_sorted = sorted(det_pools, key=_sort_key)

        assert len(det_sorted) == len(baseline_sorted), \
            f"Pool count mismatch: {len(det_sorted)} vs {len(baseline_sorted)}"

        for det, bl in zip(det_sorted, baseline_sorted):
            props = det.properties
            assert props["type"] == bl["type"], \
                f"Type mismatch: {props['type']} vs {bl['type']}"
            assert props["timeframe"] == bl["timeframe"], \
                f"TF mismatch: {props['timeframe']} vs {bl['timeframe']}"
            assert det.price == pytest.approx(bl["price"], abs=1e-6), \
                f"Price mismatch: {det.price} vs {bl['price']}"
            assert props["touches"] == bl["touches"], \
                f"Touch count mismatch: {props['touches']} vs {bl['touches']}"
            assert props["status"] == bl["status"], \
                f"Status mismatch: {props['status']} vs {bl['status']}"

    def test_touch_prices_match_baseline(self, htf_result, baseline):
        """Touch prices list matches baseline for each pool."""
        baseline_pools = baseline["pools"]
        det_pools = htf_result.detections

        def _sort_key(p):
            if isinstance(p, dict):
                return (p["timeframe"], p["type"], p["price"])
            return (p.properties["timeframe"], p.properties["type"], p.price)

        baseline_sorted = sorted(baseline_pools, key=_sort_key)
        det_sorted = sorted(det_pools, key=_sort_key)

        for det, bl in zip(det_sorted, baseline_sorted):
            det_prices = det.properties.get("touch_prices", [])
            bl_prices = bl["touch_prices"]
            assert len(det_prices) == len(bl_prices), \
                f"Touch prices length mismatch for {bl['type']} {bl['timeframe']}"
            for dp, bp in zip(det_prices, bl_prices):
                assert dp == pytest.approx(bp, abs=1e-6), \
                    f"Touch price mismatch: {dp} vs {bp}"

    def test_formation_times_match_baseline(self, htf_result, baseline):
        """First/last touch times match baseline."""
        baseline_pools = baseline["pools"]
        det_pools = htf_result.detections

        def _sort_key(p):
            if isinstance(p, dict):
                return (p["timeframe"], p["type"], p["price"])
            return (p.properties["timeframe"], p.properties["type"], p.price)

        baseline_sorted = sorted(baseline_pools, key=_sort_key)
        det_sorted = sorted(det_pools, key=_sort_key)

        for det, bl in zip(det_sorted, baseline_sorted):
            props = det.properties
            assert props["first_touch_time"] == bl["first_touch_time"], \
                f"First touch time mismatch: {props['first_touch_time']} vs {bl['first_touch_time']}"
            assert props["last_touch_time"] == bl["last_touch_time"], \
                f"Last touch time mismatch: {props['last_touch_time']} vs {bl['last_touch_time']}"

    def test_taken_time_match_baseline(self, htf_result, baseline):
        """Taken time matches baseline for TAKEN pools."""
        baseline_pools = baseline["pools"]
        det_pools = htf_result.detections

        def _sort_key(p):
            if isinstance(p, dict):
                return (p["timeframe"], p["type"], p["price"])
            return (p.properties["timeframe"], p.properties["type"], p.price)

        baseline_sorted = sorted(baseline_pools, key=_sort_key)
        det_sorted = sorted(det_pools, key=_sort_key)

        for det, bl in zip(det_sorted, baseline_sorted):
            props = det.properties
            assert props.get("taken_time") == bl.get("taken_time"), \
                f"Taken time mismatch: {props.get('taken_time')} vs {bl.get('taken_time')}"

    def test_tags_include_htf_structural(self, htf_result):
        """All pools should have HTF_STRUCTURAL tag."""
        for det in htf_result.detections:
            assert "HTF_STRUCTURAL" in det.properties.get("tags", [])


# ─── Summary metadata tests ──────────────────────────────────────────────

class TestHTFLiquiditySummary:
    """Summary metadata matches baseline."""

    def test_full_summary_matches(self, htf_result, baseline):
        """All TFs in summary match baseline."""
        for tf in ["H1", "H4", "D1", "W1"]:
            bl_tf = baseline["summary"].get(tf, {})
            meta_tf = htf_result.metadata.get(tf, {})
            assert meta_tf.get("pools", 0) == bl_tf.get("pools", 0), \
                f"{tf} pool count: {meta_tf.get('pools')} vs {bl_tf.get('pools')}"
            assert meta_tf.get("untouched", 0) == bl_tf.get("untouched", 0), \
                f"{tf} untouched: {meta_tf.get('untouched')} vs {bl_tf.get('untouched')}"
            assert meta_tf.get("taken", 0) == bl_tf.get("taken", 0), \
                f"{tf} taken: {meta_tf.get('taken')} vs {bl_tf.get('taken')}"


# ─── Detector interface tests ────────────────────────────────────────────

class TestHTFLiquidityInterface:
    """Verify detector implements PrimitiveDetector correctly."""

    def test_primitive_name(self):
        det = HTFLiquidityDetector()
        assert det.primitive_name == "htf_liquidity"

    def test_variant_name(self):
        det = HTFLiquidityDetector()
        assert det.variant_name == "a8ra_v1"

    def test_required_upstream(self):
        det = HTFLiquidityDetector()
        assert det.required_upstream() == ["swing_points"]

    def test_result_is_detection_result(self, htf_result):
        assert isinstance(htf_result, DetectionResult)
        assert htf_result.primitive == "htf_liquidity"
        assert htf_result.variant == "a8ra_v1"

    def test_total_pool_count(self, htf_result, baseline):
        """Total pool count across all TFs matches baseline."""
        assert len(htf_result.detections) == len(baseline["pools"])
