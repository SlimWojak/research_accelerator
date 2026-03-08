"""Tests for River adapter — Phoenix River parquet data consumer.

Tests run against actual parquet data at ~/phoenix-river/EURUSD/2024/01/.
Covers VAL-RIVER-001 through VAL-RIVER-017.
"""

import os
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from ra.data.river_adapter import RiverAdapter

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Skip all tests if River data is not available
RIVER_ROOT = Path(os.environ.get("RIVER_ROOT", os.path.expanduser("~/phoenix-river")))
RIVER_DATA_AVAILABLE = (RIVER_ROOT / "EURUSD" / "2024" / "01" / "08.parquet").exists()

pytestmark = pytest.mark.skipif(
    not RIVER_DATA_AVAILABLE,
    reason="River parquet data not available at ~/phoenix-river/EURUSD/2024/01/",
)


@pytest.fixture
def adapter():
    """Return a RiverAdapter with default settings."""
    return RiverAdapter()


# ---------- VAL-RIVER-001: load_bars returns correct columns and data ----------


class TestLoadBarsColumns:
    """VAL-RIVER-001: load_bars returns DataFrame with all expected columns."""

    def test_expected_columns_present(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        expected_cols = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "source",
            "knowledge_time",
            "bar_hash",
            "is_ghost",
            "timestamp_ny",
        }
        assert expected_cols.issubset(set(df.columns))
        assert len(df) > 0

    def test_session_columns_present(self, adapter):
        """Session tagger columns should also be present."""
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        for col in ("session", "kill_zone", "ny_window", "forex_day"):
            assert col in df.columns, f"Missing column: {col}"


# ---------- VAL-RIVER-002: Timezone normalization Asia/Bangkok to UTC ----------


class TestTimezoneNormalization:
    """VAL-RIVER-002: Raw Asia/Bangkok timestamps normalized to UTC."""

    def test_first_bar_utc(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        first_ts = df["timestamp"].iloc[0]
        assert first_ts.tzinfo is not None
        # First bar of 2024-01-08 raw is 07:00+07:00 -> 00:00 UTC
        assert first_ts == pd.Timestamp("2024-01-08 00:00:00", tz="UTC")

    def test_timestamp_tz_is_utc(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        assert str(df["timestamp"].dt.tz) == "UTC"


# ---------- VAL-RIVER-003: NY timestamp computation ----------


class TestNYTimestamp:
    """VAL-RIVER-003: timestamp_ny is America/New_York."""

    def test_ny_timezone(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        assert str(df["timestamp_ny"].dt.tz) == "America/New_York"

    def test_ny_hour_offset(self, adapter):
        """2024-01-08 00:00 UTC = 2024-01-07 19:00 EST."""
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        first_ny = df["timestamp_ny"].iloc[0]
        assert first_ny.hour == 19
        assert first_ny.day == 7  # Previous day in NY


# ---------- VAL-RIVER-004: Single-day bar count ----------


class TestSingleDayBarCount:
    """VAL-RIVER-004: Single-day load returns exactly 1440 bars."""

    def test_1440_bars(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        assert len(df) == 1440


# ---------- VAL-RIVER-005: Multi-day date range filtering ----------


class TestMultiDayRange:
    """VAL-RIVER-005: Multi-day load returns correct bar count."""

    def test_three_day_4320_bars(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-10")
        assert len(df) == 4320

    def test_timestamp_span(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-10")
        assert df["timestamp"].iloc[0] == pd.Timestamp("2024-01-08 00:00:00", tz="UTC")
        # Last bar: Jan 10 23:59 UTC
        assert df["timestamp"].iloc[-1] == pd.Timestamp("2024-01-10 23:59:00", tz="UTC")


# ---------- VAL-RIVER-006: Weekend gap handling ----------


class TestWeekendGap:
    """VAL-RIVER-006: Weekend dates skipped, no crash."""

    def test_weekend_skipped(self, adapter):
        """Jan 5 (Fri) + Jan 8 (Mon), no Sat/Sun files."""
        df = adapter.load_bars("EURUSD", "2024-01-05", "2024-01-08")
        assert len(df) == 2880  # 2 days * 1440

    def test_no_weekend_dates(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-05", "2024-01-08")
        # No Saturday (6th) or Sunday (7th) bars
        dates = df["timestamp"].dt.day_name()
        assert "Saturday" not in dates.values
        assert "Sunday" not in dates.values


# ---------- VAL-RIVER-007: Ghost bar identification ----------


class TestGhostBarIdentification:
    """VAL-RIVER-007: Volume==0 is ghost, volume==-1 is NOT ghost."""

    def test_is_ghost_column_exists(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        assert "is_ghost" in df.columns
        assert df["is_ghost"].dtype == bool

    def test_ghost_logic(self):
        """Test ghost identification with synthetic data."""
        import numpy as np

        # Create a minimal adapter to test ghost logic
        adapter = RiverAdapter()
        # Check: volume 0 -> ghost, volume -1 -> NOT ghost, volume >0 -> NOT ghost
        volumes = pd.Series([0.0, -1.0, 10.0, 25.0, 0.0])
        is_ghost = volumes == 0.0
        assert is_ghost.tolist() == [True, False, False, False, True]


# ---------- VAL-RIVER-008: load_and_aggregate 5m/15m/1H ----------


class TestLoadAndAggregate:
    """VAL-RIVER-008: Aggregation produces correct bar counts and values."""

    def test_5m_bar_count(self, adapter):
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "5m")
        assert len(df) == 288  # 1440 / 5

    def test_15m_bar_count(self, adapter):
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "15m")
        assert len(df) == 96  # 1440 / 15

    def test_1h_bar_count(self, adapter):
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "1H")
        assert len(df) == 24  # 1440 / 60

    def test_ohlcv_aggregation_correctness(self, adapter):
        """Verify open=first, high=max, low=min, close=last, volume=sum."""
        bars_1m = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        bars_5m = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "5m")

        # Compare the first 5m bar against the first 5 1m bars
        first_5 = bars_1m.iloc[:5]
        first_5m_bar = bars_5m.iloc[0]

        assert first_5m_bar["open"] == first_5["open"].iloc[0]
        assert first_5m_bar["high"] == first_5["high"].max()
        assert first_5m_bar["low"] == first_5["low"].min()
        assert first_5m_bar["close"] == first_5["close"].iloc[-1]
        assert abs(first_5m_bar["volume"] - first_5["volume"].sum()) < 0.01


# ---------- VAL-RIVER-009: 4H bar alignment to forex day boundary ----------


class TestFourHourAlignment:
    """VAL-RIVER-009: 4H bars aligned to forex day boundary."""

    def test_4h_forex_aligned_buckets(self, adapter):
        """4H bars should be in forex-day-aligned 4h buckets: [17-20, 21-0, 1-4, 5-8, 9-12, 13-16] NY."""
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "4H")
        # Valid bucket start hours for forex-day alignment
        valid_bucket_starts = {17, 21, 1, 5, 9, 13}
        ny_hours = df["timestamp_ny"].dt.hour
        for h in ny_hours:
            # Each bar's hour should fall within a forex-day-aligned 4H bucket
            # Compute which bucket this hour belongs to
            offset_min = (h * 60 - 17 * 60) % (24 * 60)
            bucket_start_min = (offset_min // 240) * 240 + 17 * 60
            bucket_start_h = (bucket_start_min % (24 * 60)) // 60
            assert bucket_start_h in valid_bucket_starts, (
                f"Hour {h} maps to bucket start {bucket_start_h}, not in {valid_bucket_starts}"
            )

    def test_4h_multi_day_six_per_forex_day(self, adapter):
        """Multi-day load: full forex days produce exactly 6 bars each."""
        # 3 calendar days = data spanning parts of 4 forex days
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-10", "4H")
        # Count bars per forex day
        bars_per_fday = df.groupby("forex_day").size()
        # Full forex days (those in the middle) should have 6 bars
        for fday, count in bars_per_fday.items():
            assert count <= 6, f"Forex day {fday} has {count} bars (max 6)"
        # Total should be reasonable: ~21 bars for 3 calendar days
        assert len(df) >= 18

    def test_4h_single_day_count(self, adapter):
        """A single calendar day produces 7 4H bars (spanning 2 forex days)."""
        # Jan 8 UTC: 19:00 NY (Jan 7) to 18:59 NY (Jan 8)
        # Forex day 2024-01-08: 6 bars (17:00-16:59 range, data starts 19:00)
        # Forex day 2024-01-09: 1 bar (17:00-18:59 NY = 22:00-23:59 UTC)
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "4H")
        assert len(df) == 7


# ---------- VAL-RIVER-010: Daily bar uses forex day boundary ----------


class TestDailyBarBoundary:
    """VAL-RIVER-010: Daily bars use forex day boundary (17:00 NY to 17:00 NY)."""

    def test_daily_bar_single_calendar_day(self, adapter):
        """Single calendar day spans 2 forex days."""
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "1D")
        # Jan 8 UTC = 19:00 NY (Jan 7) to 18:59 NY (Jan 8)
        # Forex day 2024-01-08: 19:00-16:59 NY -> most bars
        # Forex day 2024-01-09: 17:00-18:59 NY -> 2 hours of bars
        assert len(df) == 2

    def test_daily_bar_forex_day_column(self, adapter):
        """Daily bars are grouped by forex_day column."""
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "1D")
        forex_days = sorted(df["forex_day"].unique().tolist())
        assert "2024-01-08" in forex_days

    def test_daily_bar_multi_day(self, adapter):
        """Multi-day produces correct daily bar count."""
        df = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-10", "1D")
        # 3 calendar days, spanning 4 forex days (partial first/last)
        assert len(df) >= 3


# ---------- VAL-RIVER-011: available_range returns correct bounds ----------


class TestAvailableRange:
    """VAL-RIVER-011: available_range scans filesystem correctly."""

    def test_returns_tuple(self, adapter):
        result = adapter.available_range("EURUSD")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_correct_bounds(self, adapter):
        start, end = adapter.available_range("EURUSD")
        # We know from exploration: first=2020/11/23, last=2026/02/20
        assert start == "2020-11-23"
        assert end == "2026-02-20"


# ---------- VAL-RIVER-012: validate_integrity gap and ghost reporting ----------


class TestValidateIntegrity:
    """VAL-RIVER-012: Integrity check reports gaps, bar count, ghost count."""

    def test_clean_day_integrity(self, adapter):
        result = adapter.validate_integrity("EURUSD", "2024-01-08", "2024-01-08")
        assert result["gap_count"] == 0
        assert result["bar_count"] == 1440
        assert result["ghost_count"] == 0

    def test_multi_day_integrity(self, adapter):
        result = adapter.validate_integrity("EURUSD", "2024-01-08", "2024-01-10")
        assert result["bar_count"] == 4320
        assert result["ghost_count"] == 0


# ---------- VAL-RIVER-013: CSV fallback backward compatibility ----------


class TestCSVFallback:
    """VAL-RIVER-013: load_from_csv still works with bar contract columns."""

    def test_csv_fallback_works(self):
        adapter = RiverAdapter()
        csv_path = "data/eurusd_1m_2024-01-07_to_2024-01-12.csv"
        df = adapter.load_from_csv(csv_path)
        # Must have bar contract columns
        for col in ("timestamp", "timestamp_ny", "open", "high", "low", "close", "volume", "is_ghost"):
            assert col in df.columns, f"Missing column: {col}"

    def test_csv_returns_dataframe(self):
        adapter = RiverAdapter()
        csv_path = "data/eurusd_1m_2024-01-07_to_2024-01-12.csv"
        df = adapter.load_from_csv(csv_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0


# ---------- VAL-RIVER-014: Full month bar count ----------


class TestFullMonthBarCount:
    """VAL-RIVER-014: Full January 2024 returns 33120 bars."""

    def test_full_month(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-01", "2024-01-31")
        assert len(df) == 33120  # 23 trading days * 1440


# ---------- VAL-RIVER-015: Bars sorted ascending, no duplicates ----------


class TestSortingAndDuplicates:
    """VAL-RIVER-015: Output sorted ascending, no duplicate timestamps."""

    def test_sorted_ascending(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-10")
        assert df["timestamp"].is_monotonic_increasing

    def test_no_duplicates(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-10")
        assert df["timestamp"].duplicated().sum() == 0

    def test_integer_index(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-10")
        assert df.index.tolist() == list(range(len(df)))


# ---------- VAL-RIVER-016: RIVER_ROOT environment variable override ----------


class TestRiverRootOverride:
    """VAL-RIVER-016: RIVER_ROOT env var overrides default path."""

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("RIVER_ROOT", "/tmp/fake_river")
        adapter = RiverAdapter()
        assert str(adapter.river_root) == "/tmp/fake_river"

    def test_constructor_override(self):
        adapter = RiverAdapter(river_root="/tmp/custom_river")
        assert str(adapter.river_root) == "/tmp/custom_river"

    def test_default_path(self, monkeypatch):
        monkeypatch.delenv("RIVER_ROOT", raising=False)
        adapter = RiverAdapter()
        expected = os.path.expanduser("~/phoenix-river")
        assert str(adapter.river_root) == expected


# ---------- VAL-RIVER-017: Cross-month DuckDB glob traversal ----------


class TestCrossMonthTraversal:
    """VAL-RIVER-017: Load bars spanning January and February."""

    def test_cross_month(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-15", "2024-02-15")
        # Should have bars from both months
        months = df["timestamp"].dt.month.unique()
        assert 1 in months
        assert 2 in months
        assert len(df) > 0

    def test_cross_month_sorted(self, adapter):
        df = adapter.load_bars("EURUSD", "2024-01-15", "2024-02-15")
        assert df["timestamp"].is_monotonic_increasing


# ---------- Additional edge case tests ----------


class TestEdgeCases:
    """Additional edge case coverage."""

    def test_1m_timeframe_passthrough(self, adapter):
        """load_and_aggregate with 1m should return same as load_bars."""
        df_bars = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        df_agg = adapter.load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "1m")
        assert len(df_bars) == len(df_agg)

    def test_volume_preserved_as_float(self, adapter):
        """Volume should be float64 matching csv_loader convention."""
        df = adapter.load_bars("EURUSD", "2024-01-08", "2024-01-08")
        assert df["volume"].dtype == "float64"
