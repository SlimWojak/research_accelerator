# Validation Assertions: Param Extraction & River Adapter

Generated: 2026-03-08
Status: Phase 2 testable behavioral assertions

---

## AREA 1: PARAM EXTRACTION

### VAL-PARAM-001
**Title:** extract_params locked mode returns same values as hardcoded function
**Behavioral description:** `extract_params(config, "fvg", mode="locked")` returns `{"floor_threshold_pips": 0.5}`, identical to the value currently hardcoded in `extract_locked_params_for_cascade()`. Test for every primitive.
**Pass condition:** Dict equality between new dynamic extraction and current hardcoded output for all 14 primitives.
**Evidence:** pytest assertion comparing `extract_params(config, primitive, mode="locked")` vs `extract_locked_params_for_cascade(config)[primitive]` for each primitive.

### VAL-PARAM-002
**Title:** extract_params sweep mode returns all sweep_range values for FVG
**Behavioral description:** `extract_params(config, "fvg", mode="sweep")` returns `{"floor_threshold_pips": [0.0, 0.5, 1.0, 1.5, 2.0]}` — the full sweep_range list from config.
**Pass condition:** Returned dict contains sweep_range list matching YAML values exactly.
**Evidence:** pytest assertion; compare against hardcoded expected list from locked_baseline.yaml line 72.

### VAL-PARAM-003
**Title:** extract_params sweep mode returns sweep_range for displacement LTF params
**Behavioral description:** `extract_params(config, "displacement", mode="sweep")` returns sweep ranges for nested LTF params: `atr_multiplier: [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]`, `body_ratio: [0.50, ..., 0.80]`, `close_gate: [0.10, ..., 0.30]`.
**Pass condition:** All three nested LTF sweep_range lists present and correct.
**Evidence:** pytest; verify `result["ltf"]["atr_multiplier"]` etc. match YAML.

### VAL-PARAM-004
**Title:** extract_params sweep mode returns sweep_range for displacement HTF params
**Behavioral description:** Same as VAL-PARAM-003 but for HTF sub-params: `atr_multiplier: [1.0, 1.25, 1.5, 1.75, 2.0]`, `body_ratio: [0.55, ..., 0.75]`, `close_gate: [0.10, ..., 0.30]`.
**Pass condition:** All three nested HTF sweep_range lists present and correct.
**Evidence:** pytest assertion.

### VAL-PARAM-005
**Title:** extract_params sweep mode for swing_points N returns global and per-TF sweep ranges
**Behavioral description:** `extract_params(config, "swing_points", mode="sweep")` returns `N.sweep_range: [2, 3, 4, 5, 6, 7, 8, 10]` (global sweep) and per-TF locked values `{1m: 5, 5m: 3, 15m: 2}`.
**Pass condition:** Both the sweep_range list and per_tf locked values are correctly extracted.
**Evidence:** pytest; verify structure matches YAML lines 104-108.

### VAL-PARAM-006
**Title:** extract_params sweep mode for swing_points height_filter_pips returns per-TF sweep ranges
**Behavioral description:** height_filter_pips has per-TF sweep ranges (unlike N which has a single global range): `1m: [0.5, 1.0, ..., 4.0]`, `5m: [2.0, 3.0, ..., 15.0]`, `15m: [3.0, 5.0, ..., 20.0]`.
**Pass condition:** Per-TF sweep_range dicts match YAML lines 112-116.
**Evidence:** pytest assertion.

### VAL-PARAM-007
**Title:** extract_sweep_combos generates correct Cartesian product for single-param primitive
**Behavioral description:** `extract_sweep_combos(config, "fvg")` generates 5 parameter combinations (one per sweep_range value): `[{floor_threshold_pips: 0.0}, {floor_threshold_pips: 0.5}, ..., {floor_threshold_pips: 2.0}]`.
**Pass condition:** len(combos) == 5; each combo is a valid param dict.
**Evidence:** pytest; enumerate and count combos.

### VAL-PARAM-008
**Title:** extract_sweep_combos generates correct Cartesian product for multi-param primitive
**Behavioral description:** `extract_sweep_combos(config, "displacement")` generates the Cartesian product of LTF `atr_multiplier` (7) × `body_ratio` (7) × `close_gate` (5) = 245 combinations (for LTF alone). With HTF params: 5 × 5 × 5 = 125. Total depends on combination strategy (LTF-only, HTF-only, or joint).
**Pass condition:** Number of combos matches expected Cartesian product size; each combo is a valid param dict passable to the detector.
**Evidence:** pytest; `len(combos)` assertion + spot-check first/last combo values.

### VAL-PARAM-009
**Title:** extract_sweep_combos for session_liquidity produces correct multi-gate combinations
**Behavioral description:** session_liquidity has 3 sweepable params: `efficiency_threshold` (6 values) × `mid_cross_min` (4 values) × `balance_score_min` (5 values) = 120 combinations.
**Pass condition:** len(combos) == 120; each combo has all three params correctly set.
**Evidence:** pytest assertion.

### VAL-PARAM-010
**Title:** Per-TF override resolution works in locked mode
**Behavioral description:** `extract_params(config, "swing_points", mode="locked")` returns `N` as `{1m: 5, 5m: 3, 15m: 2}` (per-TF locked values resolved from the per_tf structure).
**Pass condition:** Per-TF dict matches exactly; no raw `{locked: X}` wrappers leak through.
**Evidence:** pytest; verify `result["N"] == {"1m": 5, "5m": 3, "15m": 2}`.

### VAL-PARAM-011
**Title:** Per-TF override resolution works in sweep mode for height_filter_pips
**Behavioral description:** In sweep mode, swing_points `height_filter_pips` returns per-TF sweep ranges rather than per-TF locked values. Each timeframe gets its own sweep list.
**Pass condition:** `result["height_filter_pips"]["sweep_range"]["1m"] == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]`; similar for 5m and 15m.
**Evidence:** pytest assertion with per-TF granularity.

### VAL-PARAM-012
**Title:** Unknown primitive name raises descriptive error
**Behavioral description:** `extract_params(config, "nonexistent_primitive", mode="locked")` raises `ConfigError` (or `KeyError`/`AttributeError`) with a message containing the bad primitive name.
**Pass condition:** Exception raised; error message includes "nonexistent_primitive".
**Evidence:** pytest `with pytest.raises(...)` assertion.

### VAL-PARAM-013
**Title:** Unknown primitive in extract_sweep_combos raises error
**Behavioral description:** `extract_sweep_combos(config, "fake_module")` raises an appropriate error.
**Pass condition:** Exception raised with descriptive message.
**Evidence:** pytest `with pytest.raises(...)`.

### VAL-PARAM-014
**Title:** All 14 primitives produce valid param dicts in locked mode
**Behavioral description:** Iterating over all 14 primitives (`fvg`, `ifvg`, `bpr`, `swing_points`, `displacement`, `session_liquidity`, `asia_range`, `mss`, `order_block`, `liquidity_sweep`, `htf_liquidity`, `ote`, `reference_levels`, `equal_hl`), `extract_params(config, name, mode="locked")` returns a dict (not None, not error) for each.
**Pass condition:** 14 non-empty or valid dicts returned (ifvg, bpr, equal_hl may return empty `{}`).
**Evidence:** pytest parametrized test over all 14 names.

### VAL-PARAM-015
**Title:** All 14 primitives produce valid param dicts in sweep mode
**Behavioral description:** Same as VAL-PARAM-014 but with `mode="sweep"`. Primitives without sweep_range fields return their locked values unchanged.
**Pass condition:** 14 dicts returned without error. Primitives with no sweep_range return locked values.
**Evidence:** pytest parametrized test.

### VAL-PARAM-016
**Title:** Round-trip: extracted locked params through CascadeEngine produce identical results
**Behavioral description:** Run CascadeEngine with params from `extract_params(config, ..., mode="locked")` for all primitives, and compare detection results to running with current `extract_locked_params_for_cascade(config)`. Outputs must be identical.
**Pass condition:** For every primitive and timeframe, `DetectionResult.detections` lists are identical (same count, same detection IDs, same coordinates).
**Evidence:** pytest; load 5-day CSV data, run cascade both ways, deep-compare all DetectionResult objects. Total detection count matches known baseline (9784).

### VAL-PARAM-017
**Title:** Locked extraction for displacement includes quality_grades and evaluation_order
**Behavioral description:** `extract_params(config, "displacement", mode="locked")` includes `quality_grades` (with STRONG/VALID/WEAK atr_ratio_min values) and `evaluation_order` list, matching the current hardcoded dict.
**Pass condition:** `result["quality_grades"]["STRONG"]["atr_ratio_min"] == 2.0`; `result["evaluation_order"] == ["check_cluster_2", "check_single_atr", "check_single_override"]`.
**Evidence:** pytest assertion.

### VAL-PARAM-018
**Title:** Locked extraction for session_liquidity resolves nested locked wrappers
**Behavioral description:** Config has `efficiency_threshold: {locked: 0.60, sweep_range: [...]}`. In locked mode, extraction returns the unwrapped value `0.60`, not the dict wrapper.
**Pass condition:** `result["four_gate_model"]["efficiency_threshold"] == 0.60` (float, not dict).
**Evidence:** pytest assertion verifying no `{locked: ...}` wrappers remain.

### VAL-PARAM-019
**Title:** Locked extraction for BPR handles null locked value
**Behavioral description:** BPR's `min_overlap_pips` has `locked: null`. `extract_params(config, "bpr", mode="locked")` returns `{"min_overlap_pips": None}`.
**Pass condition:** `result["min_overlap_pips"] is None`.
**Evidence:** pytest assertion.

### VAL-PARAM-020
**Title:** Sweep extraction for BPR returns sweep_range alongside null locked
**Behavioral description:** `extract_params(config, "bpr", mode="sweep")` returns `{"min_overlap_pips": {"locked": None, "sweep_range": [0.0, 0.5, 1.0, 2.0]}}` or equivalent structure exposing the sweep values.
**Pass condition:** sweep_range list `[0.0, 0.5, 1.0, 2.0]` is present and correct.
**Evidence:** pytest assertion.

### VAL-PARAM-021
**Title:** Locked extraction for order_block includes per_tf expiration_bars
**Behavioral description:** order_block `expiration_bars.per_tf` has 6 TF entries. Locked extraction preserves the full per_tf map: `{1m: 10, 5m: 10, 15m: 10, 1H: 15, 4H: 20, 1D: 20}`.
**Pass condition:** Dict with 6 TF keys and correct integer values.
**Evidence:** pytest assertion.

### VAL-PARAM-022
**Title:** Locked extraction for liquidity_sweep preserves nested level_sources structure
**Behavioral description:** liquidity_sweep has deeply nested `level_sources` with per-source enable flags and sub-params (e.g., `promoted_swing.strength_min: 10`). Extraction preserves full structure.
**Pass condition:** `result["level_sources"]["promoted_swing"]["strength_min"] == 10`; `result["level_sources"]["pdh_pdl"]["enabled"] == True`.
**Evidence:** pytest deep-equality assertion against current hardcoded dict.

### VAL-PARAM-023
**Title:** Sweep extraction for rejection_wick_pct returns range
**Behavioral description:** liquidity_sweep `rejection_wick_pct` has `locked: 0.40, sweep_range: [0.30, 0.35, 0.40, 0.45, 0.50]`. Sweep mode exposes the 5-value range.
**Pass condition:** sweep_range list present with 5 values.
**Evidence:** pytest assertion.

### VAL-PARAM-024
**Title:** Displacement combination_mode locked extraction returns string not dict
**Behavioral description:** Config has `combination_mode: {locked: AND, options: [AND, OR]}`. Locked extraction returns the string `"AND"`, not the dict. Sweep mode returns `["AND", "OR"]` (the options list as sweep values).
**Pass condition:** Locked: `result["combination_mode"] == "AND"`; Sweep: result includes `["AND", "OR"]`.
**Evidence:** pytest assertions for both modes.

---

## AREA 2: RIVER ADAPTER

### VAL-RIVER-001
**Title:** load_bars reads parquet data and returns correct column set
**Behavioral description:** `RiverAdapter(river_root).load_bars("EURUSD", "2024-01-08", "2024-01-08")` returns a DataFrame with all 9 raw columns (`timestamp`, `open`, `high`, `low`, `close`, `volume`, `source`, `knowledge_time`, `bar_hash`) plus computed columns (`is_ghost`, `timestamp_ny`).
**Pass condition:** All expected columns present; no extra unexpected columns; DataFrame is non-empty.
**Evidence:** pytest; `set(df.columns) >= expected_columns`.

### VAL-RIVER-002
**Title:** Timezone normalization: Asia/Bangkok → UTC
**Behavioral description:** Raw parquet timestamps are `Asia/Bangkok` (UTC+7). After load_bars(), `timestamp` column is UTC (`datetime64[ns, UTC]`). First bar of 2024-01-08 raw is `07:00+07:00` → should be `00:00 UTC`.
**Pass condition:** `df["timestamp"].iloc[0] == pd.Timestamp("2024-01-08 00:00:00", tz="UTC")`.
**Evidence:** pytest assertion on first row timestamp.

### VAL-RIVER-003
**Title:** timestamp_ny column computed correctly from UTC
**Behavioral description:** After timezone normalization to UTC, `timestamp_ny` is computed as `America/New_York`. For 2024-01-08 00:00 UTC (EST, UTC-5), NY time is `2024-01-07 19:00 NY`.
**Pass condition:** `df["timestamp_ny"].iloc[0].hour == 19` and date is `2024-01-07`.
**Evidence:** pytest assertion.

### VAL-RIVER-004
**Title:** Date range filtering — single day
**Behavioral description:** `load_bars("EURUSD", "2024-01-08", "2024-01-08")` returns exactly 1440 bars (one full day of 1m bars).
**Pass condition:** `len(df) == 1440`.
**Evidence:** pytest assertion; known from parquet inspection (COUNT(*) = 1440).

### VAL-RIVER-005
**Title:** Date range filtering — multi-day span
**Behavioral description:** `load_bars("EURUSD", "2024-01-08", "2024-01-10")` returns bars for 3 trading days. Expected: 3 × 1440 = 4320 bars.
**Pass condition:** `len(df) == 4320`; bars span from Jan 8 00:00 UTC to Jan 10 23:59 UTC.
**Evidence:** pytest; verify min/max timestamp and row count.

### VAL-RIVER-006
**Title:** Date range filtering — weekend gap handled
**Behavioral description:** `load_bars("EURUSD", "2024-01-05", "2024-01-08")` loads Friday Jan 5 and Monday Jan 8 (no files for Jan 6-7 Saturday/Sunday). Returns 2 × 1440 = 2880 bars without error.
**Pass condition:** `len(df) == 2880`; no bars with Saturday/Sunday dates; no error raised.
**Evidence:** pytest assertion.

### VAL-RIVER-007
**Title:** Volume semantics preserved — float values from Dukascopy
**Behavioral description:** Raw parquet has volume as float64 (Dukascopy tick count can be fractional). Adapter preserves volume values without type coercion to int.
**Pass condition:** `df["volume"].dtype` is float64 or compatible numeric type; values match raw parquet.
**Evidence:** pytest; compare sample volume values against known parquet content.

### VAL-RIVER-008
**Title:** Ghost bar identification — volume == 0
**Behavioral description:** Bars with `volume == 0` get `is_ghost = True`. All other bars get `is_ghost = False`. (Current EURUSD 2024 data has no ghosts, so test should also use synthetic data.)
**Pass condition:** `df[df["volume"] == 0]["is_ghost"].all() == True`; `df[df["volume"] > 0]["is_ghost"].all() == False`.
**Evidence:** pytest; for real data verify no ghosts. Synthetic test: inject a volume=0 row and verify is_ghost=True.

### VAL-RIVER-009
**Title:** Ghost bar edge case — volume == -1 (IBKR) is NOT ghost
**Behavioral description:** IBKR midpoint bars have `volume == -1`. These are real bars, NOT ghosts. `is_ghost` should be `False` for volume=-1.
**Pass condition:** Synthetic test: inject volume=-1 row → `is_ghost == False`.
**Evidence:** pytest with synthetic data.

### VAL-RIVER-010
**Title:** load_and_aggregate produces correct 5m bars
**Behavioral description:** `load_and_aggregate("EURUSD", "2024-01-08", "2024-01-08", "5m")` aggregates 1440 1m bars into 288 5m bars. OHLC aggregation: open=first, high=max, low=min, close=last. Volume=sum.
**Pass condition:** `len(df) == 288`; spot-check first 5m bar: open matches bar[0].open, high matches max(bar[0:5].high), close matches bar[4].close.
**Evidence:** pytest; compute expected values manually from raw 1m bars and compare.

### VAL-RIVER-011
**Title:** load_and_aggregate produces correct 15m bars
**Behavioral description:** 1440 1m bars → 96 15m bars. Same aggregation rules as 5m.
**Pass condition:** `len(df) == 96`; OHLCV spot-check passes.
**Evidence:** pytest assertion.

### VAL-RIVER-012
**Title:** load_and_aggregate produces correct 1H bars
**Behavioral description:** 1440 1m bars → 24 1H bars. Timestamps clock-aligned at :00.
**Pass condition:** `len(df) == 24`; timestamps are on the hour; OHLCV aggregation correct.
**Evidence:** pytest assertion.

### VAL-RIVER-013
**Title:** load_and_aggregate ghost bar handling in aggregation
**Behavioral description:** If all 5 constituent 1m bars of a 5m window are ghost (volume=0), the resulting 5m bar is also ghost (`is_ghost=True`). If any constituent is real, the 5m bar is real.
**Pass condition:** Synthetic test: 5 ghost 1m bars → ghost 5m bar; 4 ghost + 1 real → real 5m bar with volume=real_volume.
**Evidence:** pytest with synthetic ghost data.

### VAL-RIVER-014
**Title:** available_range returns correct date bounds
**Behavioral description:** `available_range("EURUSD")` scans the `phoenix-river/EURUSD/` directory tree and returns `("2024-01-01", "2024-12-31")` (or actual min/max dates found).
**Pass condition:** Returned tuple `(earliest, latest)` matches the actual filesystem. January has files from 01 to 31; December exists.
**Evidence:** pytest; compare against `ls` of parquet directory.

### VAL-RIVER-015
**Title:** available_range for non-existent pair raises error
**Behavioral description:** `available_range("XYZABC")` raises `FileNotFoundError` or similar when no parquet files exist for the pair.
**Pass condition:** Exception raised with descriptive message.
**Evidence:** pytest `with pytest.raises(...)`.

### VAL-RIVER-016
**Title:** validate_integrity detects no gaps for complete day
**Behavioral description:** `validate_integrity("EURUSD", "2024-01-08", "2024-01-08")` returns a dict with `gap_count: 0` and `bar_count: 1440` for a day with no missing minutes.
**Pass condition:** `result["gap_count"] == 0`; `result["bar_count"] == 1440`.
**Evidence:** pytest assertion.

### VAL-RIVER-017
**Title:** validate_integrity reports ghost bar counts
**Behavioral description:** Integrity report includes `ghost_count` field showing number of volume==0 bars. For current EURUSD Jan 2024 data: `ghost_count == 0`.
**Pass condition:** `result["ghost_count"] == 0` for known clean data. Synthetic test confirms ghost counting.
**Evidence:** pytest assertion.

### VAL-RIVER-018
**Title:** validate_integrity detects missing file gaps
**Behavioral description:** If a weekday parquet file is missing (e.g., file for Jan 9 deleted), validate_integrity for Jan 8-10 should report a gap.
**Pass condition:** `result["gap_count"] >= 1` or `result["missing_dates"]` includes the missing date.
**Evidence:** pytest with mocked/temp filesystem (don't modify real data).

### VAL-RIVER-019
**Title:** CSV fallback still works — backward compatibility
**Behavioral description:** `RiverAdapter().load_from_csv(csv_path)` continues to work, returning a DataFrame with the bar contract columns. The Phase 1 CSV path must remain functional.
**Pass condition:** Returns valid DataFrame with columns: timestamp, open, high, low, close, volume (at minimum). No exception raised.
**Evidence:** pytest using existing 5-day calibration CSV.

### VAL-RIVER-020
**Title:** CSV fallback produces same schema as River load
**Behavioral description:** DataFrame from `load_from_csv()` has the same column set as `load_bars()` output (with synthetic fills for River-only columns: `source="csv_import"`, `knowledge_time=file_mtime`, `bar_hash=computed`, `is_ghost=False`).
**Pass condition:** Column sets are identical between CSV and River DataFrame outputs.
**Evidence:** pytest; compare `set(csv_df.columns) == set(river_df.columns)`.

### VAL-RIVER-021
**Title:** Bar count matches expected for known date ranges — full month
**Behavioral description:** `load_bars("EURUSD", "2024-01-01", "2024-01-31")` returns bars for all 23 trading days in January 2024. Expected: 23 × 1440 = 33,120 bars.
**Pass condition:** `len(df) == 33120`.
**Evidence:** pytest assertion; confirmed by DuckDB count over `01/*.parquet`.

### VAL-RIVER-022
**Title:** Raw schema has all 9 expected columns
**Behavioral description:** Every parquet file contains exactly 9 columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `source`, `knowledge_time`, `bar_hash`.
**Pass condition:** Column set matches exactly (no missing, no extra).
**Evidence:** pytest or inline Python; read one parquet file, assert columns.

### VAL-RIVER-023
**Title:** Processed output has all contract columns
**Behavioral description:** After full processing (load + tag), output DataFrame has all bar contract columns: `timestamp` (UTC), `timestamp_ny`, `open`, `high`, `low`, `close`, `volume`, `is_ghost`, `session`, `kill_zone`, `ny_window`, `forex_day` (12 columns minimum).
**Pass condition:** All 12 columns present with correct types.
**Evidence:** pytest; check column names and dtypes.

### VAL-RIVER-024
**Title:** Bars sorted by timestamp ascending, no duplicates
**Behavioral description:** Output DataFrame from load_bars() is sorted by timestamp ascending with no duplicate timestamps.
**Pass condition:** `df["timestamp"].is_monotonic_increasing == True`; `df["timestamp"].duplicated().sum() == 0`.
**Evidence:** pytest assertion.

### VAL-RIVER-025
**Title:** RIVER_ROOT environment variable override
**Behavioral description:** When `RIVER_ROOT` env var is set, `RiverAdapter()` (no explicit river_root arg) uses it. When not set, defaults to `~/phoenix-river`.
**Pass condition:** Adapter correctly reads from env-var-specified path; default fallback works.
**Evidence:** pytest with `monkeypatch.setenv("RIVER_ROOT", tmp_path)`.

### VAL-RIVER-026
**Title:** Parquet volume type handling — float64 to expected type
**Behavioral description:** Raw parquet volume is float64 (Dukascopy fractional ticks). The spec says int64 but actual data is float. Adapter must handle this gracefully — either preserve float64 or explicitly cast (spec reconciliation needed).
**Pass condition:** No TypeError or data loss; volume values are numeric and usable for ghost detection.
**Evidence:** pytest; verify `df["volume"].dtype` is numeric; ghost detection works with float volume.

### VAL-RIVER-027
**Title:** DuckDB glob pattern correctly traverses year/month/day partitions
**Behavioral description:** Internal DuckDB query using glob pattern `{river_root}/{pair}/*/*/**.parquet` correctly discovers and reads files across the `{year}/{mm}/{dd}.parquet` directory structure.
**Pass condition:** Multi-month query returns data from all relevant months; no files missed.
**Evidence:** pytest; `load_bars("EURUSD", "2024-01-08", "2024-02-08")` returns bars spanning both January and February.

### VAL-RIVER-028
**Title:** Integer positional index (not timestamp index)
**Behavioral description:** Output DataFrame uses integer positional index, not timestamp as index. This allows `bars.iloc[i-2]` style access matching v0.5 pseudocode.
**Pass condition:** `df.index.dtype` is integer; `df.index[0] == 0`; timestamp is a column.
**Evidence:** pytest assertion on index type and values.

### VAL-RIVER-029
**Title:** 4H bar alignment follows forex day boundary
**Behavioral description:** `load_and_aggregate(..., "4H")` produces 4H bars aligned to forex day boundary: `[17:00, 21:00, 01:00, 05:00, 09:00, 13:00]` NY time (6 bars per forex day).
**Pass condition:** 4H bar timestamps (converted to NY) fall exactly on these boundaries.
**Evidence:** pytest; load 1 forex day, aggregate to 4H, check NY-time hours.

### VAL-RIVER-030
**Title:** Daily bar uses forex day boundary (17:00 NY to 17:00 NY)
**Behavioral description:** `load_and_aggregate(..., "1D")` produces daily bars where each bar spans 17:00 NY to 17:00 NY (next day), not midnight to midnight.
**Pass condition:** Daily bar timestamps align to 17:00 NY; each bar covers 24h from that boundary.
**Evidence:** pytest; verify bar timestamps and constituent minute counts.

---

## SUMMARY

| Area | Assertion Count | ID Range |
|------|----------------|----------|
| Param Extraction | 24 | VAL-PARAM-001 to VAL-PARAM-024 |
| River Adapter | 30 | VAL-RIVER-001 to VAL-RIVER-030 |
| **Total** | **54** | |

### Key Data Facts (from parquet inspection)
- Raw parquet timezone: `Asia/Bangkok` (UTC+7) — normalization to UTC required
- Raw column count: 9 (timestamp, open, high, low, close, volume, source, knowledge_time, bar_hash)
- Volume dtype: float64 (not int64 as spec states — needs reconciliation)
- Bars per day: 1440 (full 24h × 60min)
- Ghost bars in current data: 0 (need synthetic tests)
- Trading days in Jan 2024: 23 (total bars: 33,120)
- Full year 2024 available (12 months)
- Source: exclusively "dukascopy" in current data
