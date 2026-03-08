"""Tests for engine base classes and registry."""

from datetime import datetime
from typing import Optional

import pandas as pd
import pytest

from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)
from ra.engine.registry import Registry, RegistryError


# ─── Detection ID tests ──────────────────────────────────────────────────

class TestMakeDetectionId:
    def test_basic_id_format(self):
        ts = datetime(2024, 1, 8, 9, 10, 0)
        result = make_detection_id("fvg", "5m", ts, "bullish")
        assert result == "fvg_5m_2024-01-08T09:10:00_bull"

    def test_bearish_direction(self):
        ts = datetime(2024, 1, 8, 9, 10, 0)
        result = make_detection_id("fvg", "5m", ts, "bearish")
        assert result == "fvg_5m_2024-01-08T09:10:00_bear"

    def test_high_direction(self):
        ts = datetime(2024, 1, 8, 9, 10, 0)
        result = make_detection_id("swing_points", "1m", ts, "high")
        assert result == "swing_points_1m_2024-01-08T09:10:00_high"

    def test_low_direction(self):
        ts = datetime(2024, 1, 8, 9, 10, 0)
        result = make_detection_id("swing_points", "15m", ts, "low")
        assert result == "swing_points_15m_2024-01-08T09:10:00_low"

    def test_deterministic(self):
        """Same inputs produce same ID."""
        ts = datetime(2024, 1, 8, 9, 10, 0)
        id1 = make_detection_id("fvg", "5m", ts, "bullish")
        id2 = make_detection_id("fvg", "5m", ts, "bullish")
        assert id1 == id2


# ─── Detection dataclass tests ───────────────────────────────────────────

class TestDetection:
    def test_required_fields(self):
        d = Detection(
            id="fvg_5m_2024-01-08T09:10:00_bull",
            time=datetime(2024, 1, 8, 9, 10, 0),
            direction="bullish",
            type="fvg",
            price=1.09500,
        )
        assert d.id == "fvg_5m_2024-01-08T09:10:00_bull"
        assert d.time == datetime(2024, 1, 8, 9, 10, 0)
        assert d.direction == "bullish"
        assert d.type == "fvg"
        assert d.price == 1.09500

    def test_default_fields(self):
        d = Detection(
            id="test",
            time=datetime.now(),
            direction="bullish",
            type="fvg",
            price=1.0,
        )
        assert d.properties == {}
        assert d.tags == {}
        assert d.upstream_refs == []

    def test_all_fields(self):
        d = Detection(
            id="fvg_5m_2024-01-08T09:10:00_bull",
            time=datetime(2024, 1, 8, 9, 10, 0),
            direction="bullish",
            type="fvg",
            price=1.09500,
            properties={"gap_pips": 1.2, "ce": 1.09550},
            tags={"session": "nyokz", "forex_day": "2024-01-08"},
            upstream_refs=["disp_5m_2024-01-08T09:10:00_bull"],
        )
        assert d.properties["gap_pips"] == 1.2
        assert d.tags["session"] == "nyokz"
        assert len(d.upstream_refs) == 1


# ─── DetectionResult dataclass tests ─────────────────────────────────────

class TestDetectionResult:
    def test_basic_result(self):
        r = DetectionResult(
            primitive="fvg",
            variant="a8ra_v1",
            timeframe="5m",
        )
        assert r.primitive == "fvg"
        assert r.variant == "a8ra_v1"
        assert r.timeframe == "5m"
        assert r.detections == []
        assert r.metadata == {}
        assert r.params_used == {}

    def test_result_with_detections(self):
        d = Detection(
            id="fvg_5m_2024-01-08T09:10:00_bull",
            time=datetime(2024, 1, 8, 9, 10, 0),
            direction="bullish",
            type="fvg",
            price=1.09500,
        )
        r = DetectionResult(
            primitive="fvg",
            variant="a8ra_v1",
            timeframe="5m",
            detections=[d],
            metadata={"count": 1},
            params_used={"floor_threshold_pips": 0.5},
        )
        assert len(r.detections) == 1
        assert r.metadata["count"] == 1


# ─── PrimitiveDetector ABC tests ─────────────────────────────────────────

class TestPrimitiveDetector:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PrimitiveDetector()

    def test_concrete_subclass(self):
        class TestDetector(PrimitiveDetector):
            primitive_name = "test"
            variant_name = "v1"
            version = "1.0.0"

            def detect(self, bars, params, upstream=None, context=None):
                return DetectionResult(
                    primitive=self.primitive_name,
                    variant=self.variant_name,
                    timeframe="5m",
                )

            def required_upstream(self):
                return []

        det = TestDetector()
        assert det.primitive_name == "test"
        assert det.variant_name == "v1"
        result = det.detect(pd.DataFrame(), {})
        assert isinstance(result, DetectionResult)
        assert det.required_upstream() == []


# ─── Registry tests ──────────────────────────────────────────────────────

class _FakeDetector(PrimitiveDetector):
    primitive_name = "fake"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(self, bars, params, upstream=None, context=None):
        return DetectionResult(
            primitive=self.primitive_name,
            variant=self.variant_name,
            timeframe="5m",
        )

    def required_upstream(self):
        return []


class _AnotherDetector(PrimitiveDetector):
    primitive_name = "another"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(self, bars, params, upstream=None, context=None):
        return DetectionResult(
            primitive=self.primitive_name,
            variant=self.variant_name,
            timeframe="5m",
        )

    def required_upstream(self):
        return ["fake"]


class TestRegistry:
    def test_register_and_get(self):
        reg = Registry()
        reg.register(_FakeDetector)
        det = reg.get("fake", "a8ra_v1")
        assert isinstance(det, _FakeDetector)

    def test_get_default_variant(self):
        reg = Registry()
        reg.register(_FakeDetector)
        det = reg.get("fake")
        assert isinstance(det, _FakeDetector)

    def test_register_multiple(self):
        reg = Registry()
        reg.register(_FakeDetector)
        reg.register(_AnotherDetector)
        assert len(reg) == 2

    def test_duplicate_registration_raises(self):
        reg = Registry()
        reg.register(_FakeDetector)
        with pytest.raises(RegistryError, match="already registered"):
            reg.register(_FakeDetector)

    def test_get_nonexistent_raises(self):
        reg = Registry()
        with pytest.raises(RegistryError, match="No detector registered"):
            reg.get("nonexistent")

    def test_list_registered(self):
        reg = Registry()
        reg.register(_FakeDetector)
        reg.register(_AnotherDetector)
        keys = reg.list_registered()
        assert ("another", "a8ra_v1") in keys
        assert ("fake", "a8ra_v1") in keys

    def test_has(self):
        reg = Registry()
        reg.register(_FakeDetector)
        assert reg.has("fake")
        assert not reg.has("nonexistent")

    def test_repr(self):
        reg = Registry()
        reg.register(_FakeDetector)
        assert "fake/a8ra_v1" in repr(reg)
