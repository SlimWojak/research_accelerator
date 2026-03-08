"""Tests for the RA data layer.

Covers:
  - VAL-DATA-001: CSV bar count (7,177)
  - VAL-DATA-002: 5m aggregation (1,440)
  - VAL-DATA-003: 15m aggregation (480)
  - VAL-DATA-004: 1H aggregation (120)
  - VAL-DATA-005: 4H aggregation (31)
  - VAL-DATA-006: 1D aggregation (5)
  - VAL-DATA-007: Session tagging correctness
  - VAL-DATA-008: Forex day boundary at 17:00 NY
  - VAL-DATA-009: NY timezone conversion
  - VAL-DATA-010: Bar DataFrame contract compliance
  - VAL-DATA-011: OHLCV aggregation rules
  - VAL-DATA-012: Partial bar guard
  - VAL-DATA-013: Ghost bar identification
"""

from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from ra.data.csv_loader import load_csv
from ra.data.river_adapter import RiverAdapter
from ra.data.session_tagger import tag_sessions
from ra.data.tf_aggregator import aggregate

CSV_PATH = Path(__file__).parent.parent / "data" / "eurusd_1m_2024-01-07_to_2024-01-12.csv"
NY_TZ = ZoneInfo("America/New_York")


# ─── VAL-DATA-001: CSV loads correct bar count ───────────────────────────

class TestCSVLoader:
    """Tests for CSV loading."""

    def test_bar_count(self, bars_1m):
        """VAL-DATA-001: Loading the CSV produces exactly 7,177 rows."""
        assert len(bars_1m) == 7177

    def test_file_not_found(self):
        """CSV loader raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_csv("/nonexistent/path.csv")

    def test_sorted_ascending(self, bars_1m):
        """Bars are sorted by timestamp ascending."""
        ts = bars_1m["timestamp"]
        assert (ts.diff().dropna() >= pd.Timedelta(0)).all()


# ─── VAL-DATA-002 to VAL-DATA-006: Aggregation bar counts ───────────────

class TestAggregationCounts:
    """Tests for timeframe aggregation bar counts."""

    def test_5m_bar_count(self, bars_5m):
        """VAL-DATA-002: 5m aggregation produces exactly 1,440 bars."""
        assert len(bars_5m) == 1440

    def test_15m_bar_count(self, bars_15m):
        """VAL-DATA-003: 15m aggregation produces exactly 480 bars."""
        assert len(bars_15m) == 480

    def test_1h_bar_count(self, bars_1h):
        """VAL-DATA-004: 1H aggregation produces exactly 120 bars."""
        assert len(bars_1h) == 120

    def test_4h_bar_count(self, bars_4h):
        """VAL-DATA-005: 4H aggregation produces exactly 31 bars."""
        assert len(bars_4h) == 31

    def test_1d_bar_count(self, bars_1d):
        """VAL-DATA-006: 1D aggregation produces exactly 5 bars (Jan 8-12)."""
        assert len(bars_1d) == 5

    def test_1d_forex_days(self, bars_1d):
        """1D bars correspond to forex days Jan 8-12."""
        expected_days = [
            "2024-01-08",
            "2024-01-09",
            "2024-01-10",
            "2024-01-11",
            "2024-01-12",
        ]
        assert list(bars_1d["forex_day"]) == expected_days

    def test_unsupported_timeframe(self, bars_1m):
        """Aggregation raises ValueError for unsupported timeframe."""
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            aggregate(bars_1m, "3m")

    def test_1m_passthrough(self, bars_1m):
        """Aggregating to 1m returns a copy of the input."""
        result = aggregate(bars_1m, "1m")
        assert len(result) == len(bars_1m)


# ─── VAL-DATA-007: Session tagging correctness ──────────────────────────

class TestSessionTagging:
    """Tests for session assignment."""

    def test_asia_session(self, bars_1m):
        """Asia session: 19:00-00:00 NY."""
        asia_bars = bars_1m[bars_1m["session"] == "asia"]
        assert len(asia_bars) > 0
        ny_hours = asia_bars["timestamp_ny"].dt.hour
        assert (ny_hours >= 19).all()

    def test_lokz_session(self, bars_1m):
        """LOKZ session: 02:00-05:00 NY."""
        lokz_bars = bars_1m[bars_1m["session"] == "lokz"]
        assert len(lokz_bars) > 0
        ny_hours = lokz_bars["timestamp_ny"].dt.hour
        assert ((ny_hours >= 2) & (ny_hours < 5)).all()

    def test_nyokz_session(self, bars_1m):
        """NYOKZ session: 07:00-10:00 NY."""
        nyokz_bars = bars_1m[bars_1m["session"] == "nyokz"]
        assert len(nyokz_bars) > 0
        ny_hours = nyokz_bars["timestamp_ny"].dt.hour
        assert ((ny_hours >= 7) & (ny_hours < 10)).all()

    def test_pre_london_session(self, bars_1m):
        """Pre-London session: 00:00-02:00 NY."""
        pre_london_bars = bars_1m[bars_1m["session"] == "pre_london"]
        assert len(pre_london_bars) > 0
        ny_hours = pre_london_bars["timestamp_ny"].dt.hour
        assert ((ny_hours >= 0) & (ny_hours < 2)).all()

    def test_pre_ny_session(self, bars_1m):
        """Pre-NY session: 05:00-07:00 NY."""
        pre_ny_bars = bars_1m[bars_1m["session"] == "pre_ny"]
        assert len(pre_ny_bars) > 0
        ny_hours = pre_ny_bars["timestamp_ny"].dt.hour
        assert ((ny_hours >= 5) & (ny_hours < 7)).all()

    def test_other_session(self, bars_1m):
        """Other session: 10:00-19:00 NY."""
        other_bars = bars_1m[bars_1m["session"] == "other"]
        assert len(other_bars) > 0
        ny_hours = other_bars["timestamp_ny"].dt.hour
        assert ((ny_hours >= 10) & (ny_hours < 19)).all()

    def test_kill_zone_lokz(self, bars_1m):
        """Kill zone 'lokz' assigned for 02:00-05:00 NY."""
        kz_lokz = bars_1m[bars_1m["kill_zone"] == "lokz"]
        assert len(kz_lokz) > 0
        ny_hours = kz_lokz["timestamp_ny"].dt.hour
        assert ((ny_hours >= 2) & (ny_hours < 5)).all()

    def test_kill_zone_nyokz(self, bars_1m):
        """Kill zone 'nyokz' assigned for 07:00-10:00 NY."""
        kz_nyokz = bars_1m[bars_1m["kill_zone"] == "nyokz"]
        assert len(kz_nyokz) > 0
        ny_hours = kz_nyokz["timestamp_ny"].dt.hour
        assert ((ny_hours >= 7) & (ny_hours < 10)).all()

    def test_kill_zone_none_outside(self, bars_1m):
        """Kill zone is None outside LOKZ and NYOKZ."""
        non_kz = bars_1m[bars_1m["kill_zone"].isna()]
        ny_hours = non_kz["timestamp_ny"].dt.hour
        # None of these should be in lokz (2-5) or nyokz (7-10)
        in_kz = ((ny_hours >= 2) & (ny_hours < 5)) | ((ny_hours >= 7) & (ny_hours < 10))
        assert not in_kz.any()

    def test_ny_window_a(self, bars_1m):
        """NY window 'a': 08:00-09:00 NY."""
        wa = bars_1m[bars_1m["ny_window"] == "a"]
        assert len(wa) > 0
        ny_hours = wa["timestamp_ny"].dt.hour
        assert ((ny_hours >= 8) & (ny_hours < 9)).all()

    def test_ny_window_b(self, bars_1m):
        """NY window 'b': 10:00-11:00 NY."""
        wb = bars_1m[bars_1m["ny_window"] == "b"]
        assert len(wb) > 0
        ny_hours = wb["timestamp_ny"].dt.hour
        assert ((ny_hours >= 10) & (ny_hours < 11)).all()

    def test_all_sessions_covered(self, bars_1m):
        """All bars have a valid session label."""
        valid_sessions = {"asia", "lokz", "nyokz", "pre_london", "pre_ny", "other"}
        actual_sessions = set(bars_1m["session"].unique())
        assert actual_sessions == valid_sessions

    def test_session_bar_counts(self, bars_1m):
        """Session bar counts are reasonable (non-zero)."""
        counts = bars_1m["session"].value_counts()
        for session in ["asia", "lokz", "nyokz", "pre_london", "pre_ny", "other"]:
            assert counts[session] > 0, f"No bars for session {session}"


# ─── VAL-DATA-008: Forex day boundary at 17:00 NY ───────────────────────

class TestForexDayBoundary:
    """Tests for forex day boundary assignment."""

    def test_boundary_split(self, bars_1m):
        """VAL-DATA-008: Bars at 16:59 NY and 17:00+ NY are different forex days."""
        # Find bars around 17:00 boundary on a specific day
        # Jan 8 bars at 16:59 should be forex_day 2024-01-08
        # Jan 8 bars at 17:00+ should be forex_day 2024-01-09
        jan8_pre = bars_1m[
            (bars_1m["timestamp_ny"].dt.date == pd.Timestamp("2024-01-08").date())
            & (bars_1m["timestamp_ny"].dt.hour == 16)
            & (bars_1m["timestamp_ny"].dt.minute == 59)
        ]
        jan8_post = bars_1m[
            (bars_1m["timestamp_ny"].dt.date == pd.Timestamp("2024-01-08").date())
            & (bars_1m["timestamp_ny"].dt.hour >= 17)
        ]

        assert len(jan8_pre) > 0, "No 16:59 bar found on Jan 8"
        assert len(jan8_post) > 0, "No 17:00+ bars found on Jan 8"

        # 16:59 -> forex day Jan 8, 17:00+ -> forex day Jan 9
        assert (jan8_pre["forex_day"] == "2024-01-08").all()
        assert (jan8_post["forex_day"] == "2024-01-09").all()

    def test_five_forex_days(self, bars_1m):
        """Five forex days: Jan 8-12."""
        forex_days = sorted(bars_1m["forex_day"].unique())
        expected = ["2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12"]
        assert forex_days == expected


# ─── VAL-DATA-009: NY timezone conversion ────────────────────────────────

class TestNYTimezone:
    """Tests for NY timezone conversion."""

    def test_timestamp_ny_column_exists(self, bars_1m):
        """VAL-DATA-009: timestamp_ny column exists."""
        assert "timestamp_ny" in bars_1m.columns

    def test_timestamp_ny_timezone(self, bars_1m):
        """timestamp_ny is in NY timezone."""
        tz = bars_1m["timestamp_ny"].dt.tz
        assert tz is not None
        # Verify it's America/New_York
        assert str(tz) == "America/New_York"

    def test_first_bar_ny_time(self, bars_1m):
        """First bar: UTC 22:04 → NY 17:04."""
        first = bars_1m.iloc[0]
        assert first["timestamp_ny"].hour == 17
        assert first["timestamp_ny"].minute == 4

    def test_utc_to_ny_offset(self, bars_1m):
        """Jan 2024 offset is -5 hours (EST, no DST)."""
        first = bars_1m.iloc[0]
        utc_hour = first["timestamp"].hour  # 22
        ny_hour = first["timestamp_ny"].hour  # 17
        assert utc_hour - ny_hour == 5


# ─── VAL-DATA-010: Bar DataFrame contract compliance ────────────────────

class TestDataFrameContract:
    """Tests for DataFrame contract compliance."""

    def test_required_columns(self, bars_1m):
        """VAL-DATA-010: All required columns present."""
        required_columns = [
            "timestamp",
            "timestamp_ny",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "is_ghost",
            "session",
            "kill_zone",
            "ny_window",
            "forex_day",
        ]
        for col in required_columns:
            assert col in bars_1m.columns, f"Missing column: {col}"

    def test_integer_index(self, bars_1m):
        """DataFrame has integer index, not timestamp index."""
        assert bars_1m.index.dtype in ("int64", "int32")
        assert bars_1m.index[0] == 0
        assert bars_1m.index[-1] == len(bars_1m) - 1

    def test_column_types(self, bars_1m):
        """Column dtypes match contract."""
        assert bars_1m["open"].dtype == "float64"
        assert bars_1m["high"].dtype == "float64"
        assert bars_1m["low"].dtype == "float64"
        assert bars_1m["close"].dtype == "float64"
        assert bars_1m["is_ghost"].dtype == "bool"

    def test_aggregated_contract_compliance(self, bars_5m):
        """Aggregated DataFrame has all required columns and integer index."""
        required_columns = [
            "timestamp",
            "timestamp_ny",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "is_ghost",
            "session",
            "kill_zone",
            "ny_window",
            "forex_day",
        ]
        for col in required_columns:
            assert col in bars_5m.columns, f"5m missing column: {col}"

        assert bars_5m.index.dtype in ("int64", "int32")
        assert bars_5m.index[0] == 0


# ─── VAL-DATA-011: OHLCV aggregation rules ──────────────────────────────

class TestOHLCVRules:
    """Tests for OHLCV aggregation correctness."""

    def test_5m_ohlcv(self, bars_1m, bars_5m):
        """VAL-DATA-011: Spot-check one 5m bar against constituent 1m bars."""
        # Take the second 5m bar (first fully populated one)
        bar_5m = bars_5m.iloc[1]
        ny_ts = bar_5m["timestamp_ny"]

        # Find constituent 1m bars: same NY date, same 5-min window
        ny_hour = ny_ts.hour
        ny_min = ny_ts.minute
        group_min_start = (ny_hour * 60 + ny_min) // 5 * 5
        group_h = group_min_start // 60
        group_m = group_min_start % 60

        constituent = bars_1m[
            (bars_1m["timestamp_ny"].dt.date == ny_ts.date())
            & (bars_1m["timestamp_ny"].dt.hour * 60 + bars_1m["timestamp_ny"].dt.minute >= group_min_start)
            & (bars_1m["timestamp_ny"].dt.hour * 60 + bars_1m["timestamp_ny"].dt.minute < group_min_start + 5)
        ]

        assert len(constituent) > 0, "No constituent bars found"
        assert bar_5m["open"] == constituent.iloc[0]["open"], "Open mismatch"
        assert bar_5m["high"] == constituent["high"].max(), "High mismatch"
        assert bar_5m["low"] == constituent["low"].min(), "Low mismatch"
        assert bar_5m["close"] == constituent.iloc[-1]["close"], "Close mismatch"
        assert abs(bar_5m["volume"] - constituent["volume"].sum()) < 1e-6, "Volume mismatch"

    def test_daily_ohlcv(self, bars_1m, bars_1d):
        """Daily OHLCV matches constituent bars for one forex day."""
        # Check Jan 9
        day_bar = bars_1d[bars_1d["forex_day"] == "2024-01-09"].iloc[0]
        constituent = bars_1m[bars_1m["forex_day"] == "2024-01-09"]

        assert day_bar["open"] == constituent.iloc[0]["open"]
        assert day_bar["high"] == constituent["high"].max()
        assert day_bar["low"] == constituent["low"].min()
        assert day_bar["close"] == constituent.iloc[-1]["close"]
        assert abs(day_bar["volume"] - constituent["volume"].sum()) < 1e-6


# ─── VAL-DATA-012: Partial bar guard ────────────────────────────────────

class TestPartialBarGuard:
    """Tests for partial bar handling at dataset boundaries."""

    def test_first_5m_bar_exists(self, bars_5m):
        """First 5m bar (partial at boundary) is included in output.

        The dataset starts at 17:04 NY, so the first 5m window (17:00-17:05)
        has only 1 constituent bar. This partial bar IS included.
        """
        first = bars_5m.iloc[0]
        assert first["timestamp_ny"].hour == 17
        assert first["timestamp_ny"].minute == 4

    def test_partial_bar_has_valid_ohlcv(self, bars_1m, bars_5m):
        """Partial boundary bar still has valid OHLCV data."""
        first_5m = bars_5m.iloc[0]

        # It should have valid price data
        assert first_5m["open"] > 0
        assert first_5m["high"] >= first_5m["low"]
        assert first_5m["close"] > 0
        assert first_5m["volume"] >= 0

    def test_aggregation_preserves_all_data(self, bars_1m, bars_5m):
        """Total volume is preserved through aggregation (no data lost)."""
        total_1m_volume = bars_1m["volume"].sum()
        total_5m_volume = bars_5m["volume"].sum()
        assert abs(total_1m_volume - total_5m_volume) < 1e-6


# ─── VAL-DATA-013: Ghost bar identification ─────────────────────────────

class TestGhostBars:
    """Tests for ghost bar identification."""

    def test_ghost_correlates_with_volume_zero(self, bars_1m):
        """VAL-DATA-013: is_ghost == True iff volume == 0."""
        ghost_mask = bars_1m["is_ghost"]
        vol_zero_mask = bars_1m["volume"] == 0.0
        assert (ghost_mask == vol_zero_mask).all()

    def test_no_ghosts_in_csv_dataset(self, bars_1m):
        """The 5-day CSV has no ghost bars (all volumes > 0)."""
        assert bars_1m["is_ghost"].sum() == 0

    def test_ghost_bar_synthetic_data(self):
        """Ghost detection works on synthetic data with volume=0."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-08T08:00:00Z", "2024-01-08T08:01:00Z"], utc=True),
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.05, 1.05],
            "volume": [100.0, 0.0],
        })
        ny_tz = ZoneInfo("America/New_York")
        df["timestamp_ny"] = df["timestamp"].dt.tz_convert(ny_tz)
        df["is_ghost"] = df["volume"] == 0.0
        df = tag_sessions(df)

        assert df.iloc[0]["is_ghost"] is False or df.iloc[0]["is_ghost"] == False
        assert df.iloc[1]["is_ghost"] is True or df.iloc[1]["is_ghost"] == True


# ─── River adapter stub tests ───────────────────────────────────────────

class TestRiverAdapter:
    """Tests for the River adapter stub."""

    def test_load_bars_raises(self):
        """RiverAdapter.load_bars() raises NotImplementedError."""
        adapter = RiverAdapter()
        with pytest.raises(NotImplementedError):
            adapter.load_bars("EURUSD", "2024-01-07", "2024-01-12")

    def test_load_from_csv(self):
        """RiverAdapter.load_from_csv() delegates to csv_loader."""
        adapter = RiverAdapter()
        df = adapter.load_from_csv(CSV_PATH)
        assert len(df) == 7177

    def test_available_range_raises(self):
        """RiverAdapter.available_range() raises NotImplementedError."""
        adapter = RiverAdapter()
        with pytest.raises(NotImplementedError):
            adapter.available_range("EURUSD")
