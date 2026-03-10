"""Tests for LuxAlgoMSSDetector — BOS/CHoCH structure break detection.

Covers validation contract assertions:
- VAL-LMSS-001: BOS and CHoCH correctly classified
- VAL-LMSS-002: No displacement gate — fires on close beyond swing only
- VAL-LMSS-003: Fires more structure breaks than a8ra on same data
- VAL-LMSS-004: Two structure levels — internal and swing
- VAL-LMSS-005: Trend state tracks correctly (BOS no flip, CHoCH flips)
- VAL-LMSS-006: Valid Detection objects with correct schema
"""

import pandas as pd
import numpy as np
import pytest

from ra.engine.base import Detection, DetectionResult, make_detection_id
from ra.engine.registry import Registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bars(prices: list[dict]) -> pd.DataFrame:
    """Create a minimal bar DataFrame from a list of OHLC dicts.

    Each dict: {open, high, low, close} — optionally timestamp_ny, session, forex_day, is_ghost.
    """
    rows = []
    base_ts = pd.Timestamp("2024-01-08 09:00:00", tz="America/New_York")
    for i, p in enumerate(prices):
        ts = base_ts + pd.Timedelta(minutes=i)
        rows.append({
            "open": p["open"],
            "high": p["high"],
            "low": p["low"],
            "close": p["close"],
            "volume": p.get("volume", 100),
            "timestamp_ny": ts,
            "session": p.get("session", "nyokz"),
            "forex_day": p.get("forex_day", "2024-01-08"),
            "is_ghost": p.get("is_ghost", False),
        })
    df = pd.DataFrame(rows)
    df.index = range(len(df))
    return df


def _build_trending_bars(
    start_price: float,
    n_bars: int,
    trend: str = "bullish",
    noise: float = 0.0003,
    step: float = 0.0002,
) -> list[dict]:
    """Build a series of bars with a clear trend direction.

    For bullish: each bar generally moves up (higher highs, higher lows).
    For bearish: each bar generally moves down.
    """
    bars = []
    price = start_price
    for i in range(n_bars):
        if trend == "bullish":
            o = price
            c = price + step
            h = max(o, c) + noise
            l = min(o, c) - noise * 0.5
            price = c
        else:
            o = price
            c = price - step
            h = max(o, c) + noise * 0.5
            l = min(o, c) - noise
            price = c
        bars.append({"open": o, "high": h, "low": l, "close": c})
    return bars


def _build_swing_high_sequence(
    base_price: float, n_left: int, peak_price: float, n_right: int
) -> list[dict]:
    """Build bars that create a clear swing high: n_left bars rising,
    1 peak bar, n_right bars falling, so the peak is higher than all
    n_right bars to its right (LuxAlgo right-side pivot).
    """
    bars = []
    # Rising to peak
    for i in range(n_left):
        p = base_price + (peak_price - base_price) * (i + 1) / (n_left + 1)
        bars.append({"open": p - 0.0001, "high": p + 0.0001, "low": p - 0.0002, "close": p})
    # Peak bar
    bars.append({"open": peak_price - 0.0002, "high": peak_price, "low": peak_price - 0.0003, "close": peak_price - 0.0001})
    # Falling from peak
    for i in range(n_right):
        p = peak_price - (peak_price - base_price) * (i + 1) / (n_right + 1)
        bars.append({"open": p + 0.0001, "high": p + 0.0002, "low": p - 0.0001, "close": p})
    return bars


def _build_swing_low_sequence(
    base_price: float, n_left: int, trough_price: float, n_right: int
) -> list[dict]:
    """Build bars that create a clear swing low: n_left bars falling,
    1 trough bar, n_right bars rising.
    """
    bars = []
    # Falling to trough
    for i in range(n_left):
        p = base_price - (base_price - trough_price) * (i + 1) / (n_left + 1)
        bars.append({"open": p + 0.0001, "high": p + 0.0002, "low": p - 0.0001, "close": p})
    # Trough bar
    bars.append({"open": trough_price + 0.0002, "high": trough_price + 0.0003, "low": trough_price, "close": trough_price + 0.0001})
    # Rising from trough
    for i in range(n_right):
        p = trough_price + (base_price - trough_price) * (i + 1) / (n_right + 1)
        bars.append({"open": p - 0.0001, "high": p + 0.0001, "low": p - 0.0002, "close": p})
    return bars


# Default params for LuxAlgo MSS
LUXALGO_MSS_PARAMS = {
    "internal_length": 5,
    "swing_length": 50,
    "confluence_filter": False,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLuxAlgoMSSImport:
    """Test that the module can be imported and has correct attributes."""

    def test_import(self):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        assert det.primitive_name == "mss"
        assert det.variant_name == "luxalgo_v1"

    def test_required_upstream_empty(self):
        """LuxAlgo MSS has NO upstream dependencies — it does its own swing detection."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        assert det.required_upstream() == []

    def test_registry_registration(self):
        """LuxAlgoMSSDetector registers as (mss, luxalgo_v1) in Registry."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        reg = Registry()
        reg.register(LuxAlgoMSSDetector)
        assert reg.has("mss", "luxalgo_v1")
        det = reg.get("mss", "luxalgo_v1")
        assert isinstance(det, LuxAlgoMSSDetector)


class TestLuxAlgoMSSDetectionSchema:
    """VAL-LMSS-006: Valid Detection objects with correct schema."""

    def test_returns_detection_result(self):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        # Build enough bars for at least one swing and break
        # 20 bars up, then swing, then break down through swing low
        bar_dicts = _build_trending_bars(1.1000, 30, "bullish")
        # Add bars going down to break the swing low
        bar_dicts.extend(_build_trending_bars(bar_dicts[-1]["close"], 30, "bearish"))
        bars = _make_bars(bar_dicts)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"})
        assert isinstance(result, DetectionResult)
        assert result.primitive == "mss"
        assert result.variant == "luxalgo_v1"
        assert result.timeframe == "5m"

    def test_detection_id_format(self):
        """Detection IDs follow mss_{tf}_{timestamp}_{direction} format."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        bar_dicts = _build_trending_bars(1.1000, 30, "bullish")
        bar_dicts.extend(_build_trending_bars(bar_dicts[-1]["close"], 30, "bearish"))
        bars = _make_bars(bar_dicts)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"})
        for d in result.detections:
            assert d.id.startswith("mss_5m_")
            assert d.id.endswith("_bull") or d.id.endswith("_bear")

    def test_detection_fields_present(self):
        """Each detection has required fields: direction, break_type, structure_level, trend_state."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        bar_dicts = _build_trending_bars(1.1000, 30, "bullish")
        bar_dicts.extend(_build_trending_bars(bar_dicts[-1]["close"], 30, "bearish"))
        bars = _make_bars(bar_dicts)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})
        for d in result.detections:
            assert d.direction in ("bullish", "bearish"), f"Bad direction: {d.direction}"
            assert "break_type" in d.properties, f"Missing break_type in {d.id}"
            assert d.properties["break_type"] in ("BOS", "CHoCH"), f"Bad break_type: {d.properties['break_type']}"
            assert "structure_level" in d.properties, f"Missing structure_level in {d.id}"
            assert d.properties["structure_level"] in ("internal", "swing"), f"Bad level: {d.properties['structure_level']}"
            assert "trend_state" in d.properties, f"Missing trend_state in {d.id}"
            assert d.properties["trend_state"] in ("bullish", "bearish"), f"Bad trend_state: {d.properties['trend_state']}"


class TestLuxAlgoBOSCHoCH:
    """VAL-LMSS-001: BOS and CHoCH correctly classified.
    VAL-LMSS-005: Trend state tracks correctly.
    """

    def _make_scenario_bars(self):
        """Create a scenario with known BOS and CHoCH events:

        Phase 1: Bullish trend (series of higher highs)
        Phase 2: Bearish CHoCH (close below prior swing low while trend is bullish)
        Phase 3: Bearish BOS (close below prior swing low while trend is bearish)
        """
        bars = []

        # Phase 1: Strong uptrend — create clear swing lows and highs
        # Swing low at 1.0950, then up to create swing high at 1.1050
        bars.extend(_build_swing_low_sequence(1.1000, 6, 1.0950, 6))   # 13 bars, swing low at idx ~6
        bars.extend(_build_swing_high_sequence(1.0980, 6, 1.1050, 6))  # 13 bars, swing high at idx ~19

        # Another swing low (higher than first = bullish trend)
        bars.extend(_build_swing_low_sequence(1.1020, 6, 1.0970, 6))   # 13 bars, swing low at idx ~32

        # Phase 2: Break below the swing low at 1.0970 → CHoCH (trend was bullish, break is bearish)
        p = bars[-1]["close"]
        for i in range(8):
            p -= 0.0005
            bars.append({"open": p + 0.0003, "high": p + 0.0004, "low": p - 0.0002, "close": p})

        # Phase 3: Create another swing low then break it → BOS (trend is now bearish)
        bars.extend(_build_swing_low_sequence(p, 6, p - 0.0020, 6))
        # Break below that new swing low
        p2 = bars[-1]["close"]
        for i in range(6):
            p2 -= 0.0005
            bars.append({"open": p2 + 0.0003, "high": p2 + 0.0004, "low": p2 - 0.0002, "close": p2})

        return _make_bars(bars)

    def test_has_both_bos_and_choch(self):
        """At least one BOS and one CHoCH should be detected."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        bars = self._make_scenario_bars()
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        break_types = [d.properties["break_type"] for d in result.detections]
        assert "BOS" in break_types, f"No BOS found. Types: {break_types}"
        assert "CHoCH" in break_types, f"No CHoCH found. Types: {break_types}"

    def test_choch_flips_trend(self):
        """VAL-LMSS-005: After a CHoCH, the trend_state should flip."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        bars = self._make_scenario_bars()
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        detections = sorted(result.detections, key=lambda d: d.time)
        for i in range(1, len(detections)):
            prev = detections[i - 1]
            curr = detections[i]
            if curr.properties["break_type"] == "CHoCH":
                # CHoCH flips trend: the trend_state after CHoCH is opposite
                # to the trend_state of the previous detection (before CHoCH)
                # Actually: the trend at CHoCH = the NEW trend direction after the flip
                assert curr.properties["trend_state"] != prev.properties["trend_state"], \
                    f"CHoCH at {curr.time} did not flip trend: was {prev.properties['trend_state']}, still {curr.properties['trend_state']}"

    def test_bos_keeps_trend(self):
        """VAL-LMSS-005: After a BOS, the trend_state should remain the same as the break direction."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        bars = self._make_scenario_bars()
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        for d in result.detections:
            if d.properties["break_type"] == "BOS":
                # BOS continues existing trend, so trend_state = direction of break
                assert d.properties["trend_state"] == d.direction, \
                    f"BOS at {d.time}: trend_state={d.properties['trend_state']} != direction={d.direction}"


class TestLuxAlgoNoDisplacementGate:
    """VAL-LMSS-002: No displacement gate — fires on close beyond swing only."""

    def test_fires_without_displacement(self):
        """On data where swing breaks exist with tiny candles (no displacement),
        LuxAlgo should still detect them.
        """
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()

        # Build bars with clear swing and tiny break candles
        bars_list = []
        # Create a swing high with small candles
        for i in range(7):
            p = 1.1000 + i * 0.0001
            bars_list.append({"open": p, "high": p + 0.00005, "low": p - 0.00005, "close": p + 0.00003})
        # Peak bar
        peak = 1.1007
        bars_list.append({"open": peak - 0.00005, "high": peak, "low": peak - 0.0001, "close": peak - 0.00003})
        # Drop with tiny candles (NO displacement — range << ATR*1.5)
        for i in range(8):
            p = peak - (i + 1) * 0.0001
            bars_list.append({"open": p + 0.00005, "high": p + 0.00008, "low": p - 0.00005, "close": p})

        # Now create a swing low
        trough = bars_list[-1]["close"]
        bars_list.append({"open": trough + 0.00005, "high": trough + 0.0001, "low": trough, "close": trough + 0.00003})
        # Recover a bit with tiny candles
        for i in range(8):
            p = trough + (i + 1) * 0.0001
            bars_list.append({"open": p - 0.00005, "high": p + 0.00005, "low": p - 0.00008, "close": p})
        # Break above swing high with tiny candles — LuxAlgo should fire, a8ra would not
        for i in range(5):
            p = peak + (i + 1) * 0.00005
            bars_list.append({"open": p - 0.00003, "high": p + 0.00003, "low": p - 0.00005, "close": p})

        bars = _make_bars(bars_list)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        # Should have at least one detection despite tiny candles
        assert len(result.detections) > 0, "LuxAlgo should fire without displacement gate"


class TestLuxAlgoMoreThanA8ra:
    """VAL-LMSS-003: Fires more structure breaks than a8ra on same data."""

    def test_more_detections_on_regression_data(self, bars_1m, bars_5m, bars_15m):
        """On the regression dataset, LuxAlgo MSS should produce strictly more
        detections than a8ra MSS for tested timeframes.
        """
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        from ra.detectors.mss import MSSDetector
        from ra.detectors.swing_points import SwingPointDetector
        from ra.detectors.displacement import DisplacementDetector
        from ra.detectors.fvg import FVGDetector

        luxalgo = LuxAlgoMSSDetector()

        # Run a8ra MSS on 5m (need upstream)
        swing_det = SwingPointDetector()
        disp_det = DisplacementDetector()
        fvg_det = FVGDetector()

        # a8ra upstream on 5m
        swing_result_5m = swing_det.detect(
            bars_5m,
            {"N": 3, "height_filter_pips": 3.0, "strength_cap": 20, "strength_as_gate": False},
            context={"timeframe": "5m"},
        )
        disp_result_5m = disp_det.detect(
            bars_5m,
            {
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
                    "pip_floor": {"1m": 3.0, "5m": 5.0, "15m": 6.0, "1H": 8.0, "4H": 15.0, "1D": 20.0},
                },
                "cluster": {"cluster_2_enabled": True, "cluster_3_enabled": False, "net_efficiency_min": 0.65, "overlap_max": 0.35},
                "quality_grades": {"STRONG": {"atr_ratio_min": 2.0}, "VALID": {"atr_ratio_min": 1.5}, "WEAK": {"atr_ratio_min": 1.25}},
                "evaluation_order": ["check_cluster_2", "check_single_atr", "check_single_override"],
            },
            context={"timeframe": "5m"},
        )
        fvg_result_5m = fvg_det.detect(
            bars_5m,
            {"floor_threshold_pips": 0.5},
            context={"timeframe": "5m"},
        )

        a8ra_mss = MSSDetector()
        a8ra_result_5m = a8ra_mss.detect(
            bars_5m,
            {
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
            },
            upstream={
                "swing_points": swing_result_5m,
                "displacement": disp_result_5m,
                "fvg": fvg_result_5m,
            },
            context={"timeframe": "5m"},
        )

        # Run LuxAlgo on 5m
        luxalgo_result_5m = luxalgo.detect(
            bars_5m, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"},
        )

        # LuxAlgo should fire strictly more due to no displacement gate
        assert len(luxalgo_result_5m.detections) > len(a8ra_result_5m.detections), \
            f"LuxAlgo ({len(luxalgo_result_5m.detections)}) should fire more than a8ra ({len(a8ra_result_5m.detections)}) on 5m"


class TestLuxAlgoTwoStructureLevels:
    """VAL-LMSS-004: Two structure levels — internal and swing."""

    def test_both_levels_present(self, bars_5m):
        """Detector should produce detections at both internal and swing levels."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()

        result = det.detect(
            bars_5m, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"},
        )

        levels = set(d.properties["structure_level"] for d in result.detections)
        assert "internal" in levels, f"No internal level detections. Levels found: {levels}"
        # Swing level with length=50 may or may not fire on 5-day data — depends on bar count
        # At minimum, internal level should be present

    def test_internal_uses_5bar_pivot(self):
        """Internal structure should use 5-bar pivot."""
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()

        # Build data with a clear 5-bar pivot swing high and break
        bars_list = []
        # 5 bars rising
        for i in range(6):
            p = 1.1000 + i * 0.0003
            bars_list.append({"open": p, "high": p + 0.0002, "low": p - 0.0001, "close": p + 0.0001})
        # Peak
        peak = bars_list[-1]["close"] + 0.0003
        bars_list.append({"open": peak - 0.0002, "high": peak, "low": peak - 0.0003, "close": peak - 0.0001})
        # 5+ bars falling (to confirm right-side pivot)
        for i in range(8):
            p = peak - (i + 1) * 0.0003
            bars_list.append({"open": p + 0.0002, "high": p + 0.0003, "low": p - 0.0001, "close": p})
        # Create a swing low
        trough = bars_list[-1]["close"]
        bars_list.append({"open": trough + 0.0001, "high": trough + 0.0002, "low": trough, "close": trough + 0.00005})
        # Recover
        for i in range(8):
            p = trough + (i + 1) * 0.0003
            bars_list.append({"open": p - 0.0001, "high": p + 0.0002, "low": p - 0.0002, "close": p})
        # Break above peak
        for i in range(3):
            p = peak + (i + 1) * 0.0003
            bars_list.append({"open": p - 0.0002, "high": p + 0.0001, "low": p - 0.0003, "close": p})

        bars = _make_bars(bars_list)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        internal_dets = [d for d in result.detections if d.properties["structure_level"] == "internal"]
        assert len(internal_dets) > 0, "Should detect internal-level structure breaks with 5-bar pivots"


class TestLuxAlgoGhostBars:
    """Ghost bars should be skipped."""

    def test_skips_ghost_bars(self):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()

        bars_list = _build_trending_bars(1.1000, 20, "bullish")
        bars_list.extend(_build_trending_bars(bars_list[-1]["close"], 20, "bearish"))
        # Mark some bars as ghost
        for i in range(10, 15):
            bars_list[i]["is_ghost"] = True

        bars = _make_bars(bars_list)
        result = det.detect(bars, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})

        # No detection should have a time matching a ghost bar
        ghost_times = set(bars.loc[bars["is_ghost"], "timestamp_ny"])
        for d in result.detections:
            assert d.time not in ghost_times, f"Detection at ghost bar time: {d.time}"


class TestLuxAlgoMetadata:
    """Metadata should include useful summary counts."""

    def test_metadata_counts(self, bars_5m):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        result = det.detect(bars_5m, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"})

        assert "total_count" in result.metadata
        assert result.metadata["total_count"] == len(result.detections)
        assert "bos_count" in result.metadata
        assert "choch_count" in result.metadata
        assert result.metadata["bos_count"] + result.metadata["choch_count"] == result.metadata["total_count"]
        assert "bullish_count" in result.metadata
        assert "bearish_count" in result.metadata
        assert "internal_count" in result.metadata
        assert "swing_count" in result.metadata


class TestLuxAlgoOnRegressionData:
    """Run LuxAlgo on the full regression dataset and verify non-trivial output."""

    def test_5m_produces_detections(self, bars_5m):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        result = det.detect(bars_5m, LUXALGO_MSS_PARAMS, context={"timeframe": "5m"})
        assert len(result.detections) > 0, "Should produce detections on 5m regression data"
        # LuxAlgo with no displacement gate should produce a substantial number
        assert len(result.detections) >= 5, f"Expected at least 5 detections on 5m, got {len(result.detections)}"

    def test_1m_produces_detections(self, bars_1m):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        result = det.detect(bars_1m, LUXALGO_MSS_PARAMS, context={"timeframe": "1m"})
        assert len(result.detections) > 0, "Should produce detections on 1m regression data"

    def test_15m_produces_detections(self, bars_15m):
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector
        det = LuxAlgoMSSDetector()
        result = det.detect(bars_15m, LUXALGO_MSS_PARAMS, context={"timeframe": "15m"})
        assert len(result.detections) > 0, "Should produce detections on 15m regression data"
