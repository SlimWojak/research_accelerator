# a8ra Research Accelerator — River Adapter Spec

```yaml
purpose: Define read-only data consumption from River parquet files
status: DRAFT
date: 2026-03-08
invariant: INV-RA-RIVER-READONLY — RA never writes to phoenix-river/
```

## 1. DESIGN PRINCIPLE

The River is Phoenix's epistemic root — immutable, bitemporal, seam-attested
parquet files. The Research Accelerator reads River data as a consumer, never
as a participant.

```
phoenix-river/                     ← OWNED BY PHOENIX (read-only to RA)
  {pair}/{year}/{mm}/{dd}.parquet

research_accelerator/              ← RA REPO (our workspace)
  src/ra/data/river_adapter.py     ← reads parquet via DuckDB
```

**Zero code changes to Phoenix.** The RA depends on the parquet file format,
not on Phoenix Python modules. If River schema changes, the adapter updates.
Phoenix never knows the RA exists.

## 2. DATA SOURCE

### River Parquet Layout

```
~/phoenix-river/
  EURUSD/
    2024/
      01/
        07.parquet
        08.parquet
        09.parquet
        10.parquet
        11.parquet
        12.parquet
      02/
        ...
  GBPUSD/
    ...
```

**Partition:** `{RIVER_ROOT}/{pair}/{year}/{mm}/{dd}.parquet`

**Override:** Environment variable `RIVER_ROOT` (default: `~/phoenix-river`)

### Raw Bar Schema (9 columns, write-once)

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime (UTC) | World Time — when bar occurred |
| `open` | float64 | Open price |
| `high` | float64 | High price |
| `low` | float64 | Low price |
| `close` | float64 | Close price |
| `volume` | int64 | Tick count (Dukascopy), -1 (IBKR midpoint), 0 (ghost) |
| `source` | string | "dukascopy" \| "ibkr" |
| `knowledge_time` | datetime (UTC) | When Phoenix learned this bar |
| `bar_hash` | string | SHA-256 of bar content |

### Volume Semantics (from River spec)

- `volume > 0` → real tick count (Dukascopy)
- `volume = -1` → IBKR MIDPOINT (no tick data)
- `volume = 0` → ghost bar (synthetic continuity)

**RA treatment:** Ghost bars (`volume == 0`) are included in the DataFrame
but detection modules skip them. A ghost bar cannot trigger FVG, swing,
displacement, etc. This mirrors Phoenix's gate behavior (ghost → SKIP).

## 3. RIVER ADAPTER INTERFACE

```python
# src/ra/data/river_adapter.py

class RiverAdapter:
    """Read-only adapter for Phoenix River parquet data."""

    def __init__(self, river_root: str | None = None):
        """
        Args:
            river_root: Path to phoenix-river/ directory.
                        Default: ~/phoenix-river or RIVER_ROOT env var.
        """

    def load_bars(
        self,
        pair: str,                    # e.g. "EURUSD"
        start_date: str,              # e.g. "2024-01-07"
        end_date: str,                # e.g. "2024-01-12"
        timeframe: str = "1m",        # base resolution
    ) -> pd.DataFrame:
        """
        Load bars from River parquet files.

        Returns DataFrame with columns:
            timestamp (datetime, UTC), open, high, low, close, volume,
            source, knowledge_time, bar_hash, is_ghost (bool)

        is_ghost derived from volume == 0.
        Bars sorted by timestamp ascending.
        """

    def load_and_aggregate(
        self,
        pair: str,
        start_date: str,
        end_date: str,
        timeframe: str,               # "5m", "15m", "1H", "4H", "1D"
    ) -> pd.DataFrame:
        """
        Load 1m bars and aggregate to target timeframe.
        Aggregation logic matches Phoenix tf_aggregator exactly.
        Ghost bars excluded from aggregation (a 5m bar with all ghosts = ghost).
        """

    def available_range(self, pair: str) -> tuple[str, str]:
        """Return (earliest_date, latest_date) for a pair."""

    def validate_integrity(
        self,
        pair: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """
        Quick integrity check: gap count, ghost count, bar count.
        Does NOT modify data. Returns diagnostic dict.
        """
```

## 4. TIMEFRAME AGGREGATION

The RA aggregates 1m bars to higher timeframes using the same logic as
Phoenix's River reader and the current `preprocess_data_v2.py`.

### Aggregation Rules

```python
def aggregate_bars(bars_1m: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    """
    Group 1m bars into tf_minutes-sized windows.

    Rules:
    - open  = first bar's open
    - high  = max of all bars' high
    - low   = min of all bars' low
    - close = last bar's close
    - volume = sum (ghost bars contribute 0)
    - timestamp = first bar's timestamp (window open)
    - is_ghost = True if ALL constituent bars are ghost

    Forex day boundary: 17:00 NY.
    Daily bars: 17:00 NY to 17:00 NY next day.
    Weekly bars: Sunday 17:00 NY to Friday 17:00 NY.
    """
```

### Alignment

| TF | Alignment | Notes |
|----|-----------|-------|
| 5m | Clock-aligned (00, 05, 10, ...) | Standard |
| 15m | Clock-aligned (00, 15, 30, 45) | Standard |
| 1H | Clock-aligned (00:00, 01:00, ...) | Standard |
| 4H | [17:00, 21:00, 01:00, 05:00, 09:00, 13:00] NY | Forex-day-aligned |
| 1D | 17:00 NY to 17:00 NY | Forex day |

## 5. SESSION TAGGING

After loading bars, the adapter tags each bar with session context.
This is computed from timestamp, not stored in River.

```python
# src/ra/data/session_tagger.py

def tag_sessions(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Add columns:
    - session: "asia" | "lokz" | "nyokz" | "other"
    - kill_zone: "lokz" | "nyokz" | None
    - ny_window: "a" | "b" | None
    - forex_day: date string (17:00 NY boundary)
    - pre_session: "pre_london" | "pre_ny" | None

    All times interpreted in NY timezone.
    """
```

### Session Definitions (from v0.5 constants)

| Session | NY Time | Note |
|---------|---------|------|
| Asia | 19:00-00:00 | Prior calendar day start |
| LOKZ | 02:00-05:00 | London Open Kill Zone |
| NYOKZ | 07:00-10:00 | NY Open Kill Zone |
| Pre-London | 00:00-02:00 | Gap between Asia and LOKZ |
| Pre-NY | 05:00-07:00 | Gap between LOKZ and NYOKZ |
| NY Window A | 08:00-09:00 | Reversal energy (inside NYOKZ) |
| NY Window B | 10:00-11:00 | Continuation energy (overlaps NYOKZ end) |

## 6. FALLBACK: CSV DATA LAYER

For the 5-day calibration dataset (which predates River ingestion for that
date range), the adapter supports direct CSV loading as a fallback:

```python
def load_from_csv(
    self,
    csv_path: str,                   # path to 1m CSV
    pair: str = "EURUSD",
) -> pd.DataFrame:
    """
    Load from CSV (current pipeline format).
    Returns same DataFrame schema as load_bars().
    Missing River-specific columns filled:
    - source: "csv_import"
    - knowledge_time: file mtime
    - bar_hash: computed on load
    - is_ghost: False (CSV has no ghosts)
    """
```

**This is critical for Phase 1:** The regression test uses the existing 5-day
CSV dataset. River integration for multi-month data comes in Phase 2+ when
data acquisition expands to 6-12 months.

## 7. BAR DATAFRAME CONTRACT

Every detection module receives bars as a pandas DataFrame with these columns:

| Column | Type | Always Present |
|--------|------|---------------|
| `timestamp` | datetime (UTC) | Yes |
| `timestamp_ny` | datetime (NY) | Yes (computed by adapter) |
| `open` | float64 | Yes |
| `high` | float64 | Yes |
| `low` | float64 | Yes |
| `close` | float64 | Yes |
| `volume` | int64 | Yes |
| `is_ghost` | bool | Yes |
| `session` | str | Yes |
| `kill_zone` | str \| None | Yes |
| `ny_window` | str \| None | Yes |
| `forex_day` | str | Yes |

**Index:** Integer (positional). Timestamp is a column, not the index.
This allows positional bar references (`bars[i-2]`) matching the v0.5 pseudocode.

**Guarantee:** Bars sorted by timestamp ascending. No duplicates. Continuous
1m series (ghosts fill gaps). Higher TFs have no ghosts within trading hours
(a 5m bar exists if any constituent 1m bar is real).

## 8. INVARIANTS

```yaml
INV-RA-RIVER-READONLY: "RA never writes to phoenix-river/. Read-only consumer."
INV-RA-SCHEMA-MATCH: "RA bar DataFrame matches River raw schema + computed columns."
INV-RA-GHOST-SKIP: "Ghost bars (is_ghost=True) never trigger detections."
INV-RA-TF-NATIVE: "Each TF's bars are independently aggregated. No projection."
INV-RA-NY-TIME: "All user-facing timestamps in NY time. UTC only in storage."
INV-RA-CSV-FALLBACK: "5-day CSV produces identical DataFrame to River parquet for same date range."
```

## 9. IMPLEMENTATION NOTES

### DuckDB Query (River path)

```python
import duckdb

def _load_parquet(self, pair: str, start: str, end: str) -> pd.DataFrame:
    query = f"""
        SELECT *
        FROM read_parquet('{self.river_root}/{pair}/*//*/**.parquet')
        WHERE timestamp >= '{start}'
          AND timestamp < '{end}'
        ORDER BY timestamp
    """
    return duckdb.sql(query).df()
```

DuckDB reads parquet files directly without loading into a database.
Glob pattern handles year/month/day partitioning automatically.

### Dependencies

```
pandas >= 2.0
duckdb >= 0.9
pyarrow >= 14.0   # parquet support
pytz              # timezone handling (or zoneinfo on 3.9+)
```

No Phoenix imports. No Dexter imports. No River Python module imports.
The adapter reads raw parquet files using standard data libraries.
