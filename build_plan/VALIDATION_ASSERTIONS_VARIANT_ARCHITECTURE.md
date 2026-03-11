# Phase 4 Milestone 1 — Validation Contract Assertions
# Scope: Variant Engine + LuxAlgo MSS + LuxAlgo OB + Variant Eval + Variant UI

---

## Area: Variant Engine (VAL-VENG-xxx)

### VAL-VENG-001: CascadeEngine accepts variant_by_primitive dict
**Behavioral description:** `CascadeEngine.__init__()` accepts an optional `variant_by_primitive` parameter — a `dict[str, str]` mapping primitive names to variant names (e.g., `{"mss": "luxalgo_v1", "order_block": "luxalgo_v1"}`). When provided, the engine uses the specified variant for each listed primitive instead of the global default. Construction completes without errors and `engine.variant_by_primitive` (or equivalent accessor) returns the supplied mapping. Pass if: `CascadeEngine(registry, dep_graph, variant_by_primitive={"mss": "luxalgo_v1"})` constructs successfully and the mapping is retrievable.
**Evidence:** Unit test output showing successful construction; `repr(engine)` or attribute access confirming the per-primitive variant mapping is stored.

### VAL-VENG-002: Registry holds multiple variants for same primitive
**Behavioral description:** After calling `registry.register(MSSDetector)` (variant `a8ra_v1`) and `registry.register(LuxAlgoMSSDetector)` (variant `luxalgo_v1`), `registry.list_registered()` contains both `("mss", "a8ra_v1")` and `("mss", "luxalgo_v1")`. `registry.get("mss", "a8ra_v1")` returns an `MSSDetector` instance and `registry.get("mss", "luxalgo_v1")` returns a `LuxAlgoMSSDetector` instance. No `RegistryError` is raised. Pass if: both variants are listed, both are retrievable, and they are distinct class instances.
**Evidence:** Terminal output of `registry.list_registered()` showing both entries; `type(registry.get("mss", "a8ra_v1")).__name__` → `"MSSDetector"`, `type(registry.get("mss", "luxalgo_v1")).__name__` → `"LuxAlgoMSSDetector"`.

### VAL-VENG-003: Running with luxalgo_v1 MSS produces different detections than a8ra_v1
**Behavioral description:** Given identical OHLC bar data and identical upstream swing_points/displacement results, running `CascadeEngine` with `variant_by_primitive={"mss": "luxalgo_v1"}` produces a different set of MSS `Detection` objects than running with the default `a8ra_v1` MSS. The detection counts differ, and/or the detection timestamps differ. The luxalgo_v1 MSS is expected to fire more structure breaks (no displacement gate, right-side pivots only). Pass if: `len(results_luxalgo["mss"]["5m"].detections) != len(results_a8ra["mss"]["5m"].detections)` on the same dataset, and at least some detection IDs are present in one but not the other.
**Evidence:** Terminal output comparing detection counts for both variants on the reference dataset (e.g., `a8ra: 12 MSS, luxalgo: 28 MSS on 5m`); list of divergent detection timestamps.

### VAL-VENG-004: Mixed-variant cascade runs without errors
**Behavioral description:** `CascadeEngine` is constructed with `variant_by_primitive={"mss": "luxalgo_v1"}` while all other primitives (fvg, displacement, swing_points, order_block, liquidity_sweep, etc.) use the default `a8ra_v1`. The full cascade `engine.run(bars_by_tf, params)` completes without raising any exception. All primitives produce `DetectionResult` objects. The `order_block` detector (still `a8ra_v1`) consumes the luxalgo MSS upstream correctly — its upstream dict contains `DetectionResult` objects with `variant="luxalgo_v1"` for the MSS key. Pass if: `engine.run()` returns results for all primitives; no `RegistryError`, `CascadeError`, or `TypeError` is raised.
**Evidence:** Terminal output showing successful cascade completion with detection counts per primitive; log lines confirming `order_block` consumed MSS upstream from `luxalgo_v1`.

### VAL-VENG-005: Default behavior unchanged when no variant override specified
**Behavioral description:** When `CascadeEngine` is constructed without `variant_by_primitive` (or with an empty dict), all detectors resolve to `a8ra_v1` exactly as they do today. Running the cascade produces identical detection counts and identical detection IDs as the current baseline. No regression in existing behavior. Pass if: `engine.run()` output matches a saved baseline fixture bit-for-bit (same detection IDs, same counts, same metadata) when no variant overrides are specified.
**Evidence:** Diff of detection results (JSON-serialized) against the existing baseline fixture showing zero differences; pytest assertion output confirming equality.

### VAL-VENG-006: Config variant field drives detector selection
**Behavioral description:** The YAML config schema supports a `variant_by_primitive` key under the cascade section (e.g., `cascade: { variant_by_primitive: { mss: luxalgo_v1 } }`). When `eval.py` or `run.py` loads this config, the `CascadeEngine` is constructed with the correct per-primitive variant mapping derived from the config file. Changing the config YAML and re-running uses the newly specified variant. Pass if: modifying `variant_by_primitive.mss` from `a8ra_v1` to `luxalgo_v1` in the config YAML and re-running produces different MSS detections matching VAL-VENG-003.
**Evidence:** Two terminal runs with different config YAML showing different MSS detection counts; config file diff confirming only the variant field changed.

---

## Area: LuxAlgo MSS Detector (VAL-LMSS-xxx)

### VAL-LMSS-001: Detects BOS (continuation) and CHoCH (reversal) correctly
**Behavioral description:** The `LuxAlgoMSSDetector` classifies each structure break as either BOS (Break of Structure — continuation of existing trend) or CHoCH (Change of Character — trend reversal). Given a known uptrend followed by a bearish break below a swing low, the detector produces a detection with `properties.break_type == "CHoCH"`. Given a continued uptrend breaking above a swing high, it produces `properties.break_type == "BOS"`. Pass if: on a synthetic fixture with known trend sequence, at least one BOS and one CHoCH are correctly classified.
**Evidence:** Test output listing detections with their `break_type` field; fixture data showing the expected trend transitions and corresponding break classifications.

### VAL-LMSS-002: Uses right-side N-bar pivot swings (not a8ra's left+right)
**Behavioral description:** The LuxAlgo MSS detector identifies swing highs/lows using only N bars to the right of the pivot (right-side confirmation), not the a8ra method of requiring N bars on both left and right sides. This means the LuxAlgo detector confirms swings sooner (N bars after the pivot, not 2N bars). On a test dataset, the LuxAlgo detector's internal swing points have timestamps that are N bars closer to real-time than a8ra swings. Pass if: comparison of swing confirmation timestamps shows luxalgo swings are confirmed earlier by exactly N bars on average.
**Evidence:** Terminal output listing swing point timestamps for both methods on the same data, showing the right-side-only pivots confirm earlier.

### VAL-LMSS-003: No displacement gate — fires on close beyond swing only
**Behavioral description:** Unlike the a8ra MSS detector which requires a displacement candle within a confirmation window, the LuxAlgo MSS detector fires on any close beyond the prior swing level — no displacement check. Given a dataset where a bar closes beyond a swing high/low but no displacement-grade candle exists nearby, the LuxAlgo detector fires an MSS while the a8ra detector does not. Pass if: on a crafted fixture with swing break but no displacement, `luxalgo_mss.detections` has entries and `a8ra_mss.detections` is empty or missing that break.
**Evidence:** Test output showing luxalgo MSS fired at timestamp T where a8ra MSS did not; inspection of the bar at T confirming close beyond swing but ATR ratio below displacement threshold.

### VAL-LMSS-004: Fires more structure breaks than a8ra_v1 MSS on same data
**Behavioral description:** On the project's reference OHLC dataset (same bars, same timeframes), the LuxAlgo MSS detector produces strictly more detections than the a8ra MSS detector. This follows from the relaxed gating (no displacement required, right-side-only pivots). Pass if: `len(luxalgo_results["mss"][tf].detections) > len(a8ra_results["mss"][tf].detections)` for all tested timeframes (1m, 5m, 15m).
**Evidence:** Terminal output table showing detection counts per TF for both variants: e.g., `5m: a8ra=12, luxalgo=28`.

### VAL-LMSS-005: Two structure levels — internal (5-bar) and swing (configurable)
**Behavioral description:** The LuxAlgo MSS detector operates with two structure levels: (1) internal structure using a fixed 5-bar pivot lookback, and (2) swing structure using a configurable N-bar lookback (default from params, e.g., N=50). Detections include a `properties.structure_level` field set to either `"internal"` or `"swing"`. Both levels are present in the output when the data contains structure breaks at both scales. Pass if: running on reference data produces detections with `structure_level == "internal"` AND detections with `structure_level == "swing"`.
**Evidence:** Terminal output filtering detections by `structure_level` showing non-zero counts for both `"internal"` and `"swing"`.

### VAL-LMSS-006: Trend state tracks correctly (flips on CHoCH, persists on BOS)
**Behavioral description:** The LuxAlgo MSS detector maintains an internal trend state (bullish or bearish). A BOS detection does not change the trend state (it confirms continuation). A CHoCH detection flips the trend state. The trend state at each detection is recorded in `properties.trend_state`. Given a sequence: initial bullish trend → bullish BOS → bearish CHoCH → bearish BOS, the trend states are: bullish → bullish → bearish → bearish. Pass if: detection sequence on a fixture with known alternations shows trend_state flipping only on CHoCH events.
**Evidence:** Ordered list of detections showing `(timestamp, break_type, trend_state)` tuples confirming flip-on-CHoCH / persist-on-BOS.

### VAL-LMSS-007: Produces valid Detection objects with correct schema
**Behavioral description:** Every detection produced by `LuxAlgoMSSDetector.detect()` is a valid `Detection` dataclass instance with all required fields populated: `id` follows the `{primitive}_{tf}_{timestamp}_{direction}` format, `time` is a datetime, `direction` is `"bullish"` or `"bearish"`, `type` is `"mss"`, `price` is a positive float, `properties` is a dict containing at minimum `break_type` and `structure_level`, `tags` is a dict. The wrapping `DetectionResult` has `primitive="mss"`, `variant="luxalgo_v1"`, and correct `timeframe`. Pass if: iterating all detections and checking field types/formats yields zero violations.
**Evidence:** Unit test output with assertion checks on every Detection field; `DetectionResult.variant` confirmed as `"luxalgo_v1"`.

### VAL-LMSS-008: Upstream dependency — swing_points (or inline swings)
**Behavioral description:** `LuxAlgoMSSDetector.required_upstream()` returns a list that includes `"swing_points"` (if consuming external swing upstream) or returns an empty list (if computing swings inline). Either way, calling `detect()` without the declared upstream raises a clear error or produces zero detections with a warning — it does not crash with an unhandled `KeyError` or `TypeError`. Pass if: `required_upstream()` returns a consistent list; calling `detect()` with missing upstream either raises `ValueError`/`KeyError` with a descriptive message or logs a warning and returns an empty `DetectionResult`.
**Evidence:** Terminal output of `LuxAlgoMSSDetector().required_upstream()`; test with missing upstream showing graceful error/warning behavior.

---

## Area: LuxAlgo OB Detector (VAL-LOB-xxx)

### VAL-LOB-001: Creates OB zones on BOS/CHoCH events
**Behavioral description:** The `LuxAlgoOBDetector` creates an order block zone for each BOS or CHoCH event from the upstream LuxAlgo MSS detections. Each MSS detection in the upstream results in at most one OB detection. The OB detection's `upstream_refs` list contains the ID of the triggering MSS detection. Pass if: the number of OB detections is ≤ the number of upstream MSS detections, and every OB's `upstream_refs[0]` matches an MSS detection ID.
**Evidence:** Terminal output showing OB count ≤ MSS count; cross-reference of `upstream_refs` confirming all reference valid MSS IDs.

### VAL-LOB-002: Anchor selection uses extreme candle with ATR filter
**Behavioral description:** For each OB zone, the anchor candle is selected as the candle with the most extreme price (highest high for bearish OB, lowest low for bullish OB) within the structure interval preceding the break. An ATR-based filter is applied: the anchor candle's range must meet a minimum threshold relative to the ATR. If no candle passes the ATR filter, no OB is created for that break. The selected anchor bar index is stored in `properties.anchor_bar_index`. Pass if: on a fixture with known candle ranges, the selected anchor matches the expected extreme candle that passes ATR filter; a break with no qualifying candle produces no OB.
**Evidence:** Test output showing anchor bar selection for each OB with the candle's range and ATR comparison; test case with sub-ATR candles producing zero OB.

### VAL-LOB-003: Zone uses full candle range (wick-to-wick)
**Behavioral description:** Unlike the a8ra OB detector which uses body-only zones (`zone_type: "body"`), the LuxAlgo OB detector uses the full candle range from wick low to wick high. Each OB detection has `properties.zone_high` equal to the anchor candle's `high` and `properties.zone_low` equal to the anchor candle's `low`. The zone width (`zone_high - zone_low`) equals the full candle range, not just the body. Pass if: for every OB detection, `properties.zone_high == anchor_candle.high` and `properties.zone_low == anchor_candle.low`.
**Evidence:** Terminal output comparing `zone_high/zone_low` with anchor candle OHLC values; comparison with a8ra OB zones on same data showing wider zones.

### VAL-LOB-004: Mitigation tracking (price touches zone)
**Behavioral description:** After an OB zone is created, the detector tracks subsequent bars for mitigation — when price enters the zone (bar's low ≤ zone_high for bullish OB, or bar's high ≥ zone_low for bearish OB). On first touch, the OB state transitions to `MITIGATED`. The detection's `properties.state` is set to `"MITIGATED"`, and `properties.mitigation_bar_index` records the bar where mitigation occurred. Pass if: on a fixture where price re-enters the OB zone, the detection shows `state == "MITIGATED"` with the correct mitigation bar index.
**Evidence:** Test output showing OB state transition from `"ACTIVE"` to `"MITIGATED"` at the expected bar; price data confirming the touch.

### VAL-LOB-005: Invalidation on close through opposite side
**Behavioral description:** An OB zone is invalidated when a bar closes through the opposite side of the zone — for a bullish OB, a close below `zone_low`; for a bearish OB, a close above `zone_high`. On invalidation, `properties.state` is set to `"INVALIDATED"` and `properties.invalidation_bar_index` records the bar. An invalidated OB cannot subsequently be mitigated. Pass if: on a fixture where price closes through the zone, the detection shows `state == "INVALIDATED"` with the correct bar index; no subsequent `MITIGATED` state override occurs.
**Evidence:** Test output showing state transition to `"INVALIDATED"`; follow-up bars entering zone do not change state back to `"MITIGATED"`.

### VAL-LOB-006: Produces valid Detection objects
**Behavioral description:** Every detection produced by `LuxAlgoOBDetector.detect()` is a valid `Detection` dataclass instance. Required fields: `id` in `{primitive}_{tf}_{timestamp}_{direction}` format, `type == "order_block"`, `direction` is `"bullish"` or `"bearish"`, `price` is a positive float (zone midpoint or entry level). Required `properties` keys: `zone_high` (float), `zone_low` (float), `state` (one of `"ACTIVE"`, `"MITIGATED"`, `"INVALIDATED"`, `"EXPIRED"`), `anchor_bar_index` (int). The wrapping `DetectionResult` has `primitive="order_block"`, `variant="luxalgo_v1"`. Pass if: iterating all detections and checking field types/formats yields zero violations.
**Evidence:** Unit test output validating every Detection field; `DetectionResult.variant` confirmed as `"luxalgo_v1"`.

---

## Area: Variant Eval (VAL-VEVAL-xxx)

### VAL-VEVAL-001: eval.py compare supports variant-a and variant-b flags
**Behavioral description:** Running `python eval.py compare --variant-a a8ra_v1 --variant-b luxalgo_v1 --config <config.yaml> --data <data_dir>` executes successfully. The script constructs two `CascadeEngine` instances (or one with variant overrides) and produces comparison output for the two variants. If either `--variant-a` or `--variant-b` is omitted, the default `a8ra_v1` is used. Passing an unregistered variant name (e.g., `--variant-a nonexistent_v9`) produces a clear error message referencing available variants. Pass if: the command runs to completion with valid variant names; invalid variant name produces `RegistryError` with available variant list.
**Evidence:** Terminal output of successful comparison run; terminal output of error case showing descriptive error message.

### VAL-VEVAL-002: Comparison output includes variant name in JSON
**Behavioral description:** The JSON output from `eval.py compare` (Schema 4A envelope) includes a `variant` field in each config entry under `configs[]`. For variant-aware runs, `configs[0].variant == "a8ra_v1"` and `configs[1].variant == "luxalgo_v1"` (or as specified by flags). The `per_config` keys incorporate the variant name (e.g., `"mss_a8ra_v1"` and `"mss_luxalgo_v1"`, or `"config_a8ra"` and `"config_luxalgo"`). Schema 4B `DetectionResult` objects have the correct `variant` field. Pass if: parsing the output JSON shows variant names in config entries and per-config keys; `jq '.configs[].variant'` returns the expected variant strings.
**Evidence:** JSON output excerpt showing `configs` array with variant fields; `per_config` keys showing variant differentiation.

### VAL-VEVAL-003: Pairwise stats computed correctly between different variants
**Behavioral description:** The `compare_pairwise()` function (or its variant-aware equivalent) correctly computes agreement_rate, only_in_a, only_in_b, and divergence_index between a8ra and luxalgo detections of the same primitive. Because luxalgo MSS fires more detections (per VAL-LMSS-004), `only_in_b` (luxalgo-only) should be greater than zero. The `agreement_rate` should be less than 100% given the different detection logic. All `divergence_index` entries have valid `time`, `in_a`, `in_b`, and `primitive` fields. Pass if: pairwise output shows `agreement_rate < 100.0`, `only_in_b > 0`, and all divergence_index entries are structurally valid.
**Evidence:** Terminal output of pairwise stats showing agreement_rate, only_in_a, only_in_b values; sample divergence_index entries with all required fields.

### VAL-VEVAL-004: Divergence index shows where variants disagree
**Behavioral description:** The `divergence_index` array in Schema 4C contains one entry for each detection that exists in one variant but not the other (or at a different timestamp). Each entry has: `time` (ISO 8601), `primitive` (string), `in_a` (boolean), `in_b` (boolean), and `direction` (string). Entries where `in_a=true, in_b=false` represent a8ra-only detections; `in_a=false, in_b=true` represent luxalgo-only detections. The array is sorted by time. The total entries equal `only_in_a + only_in_b` from the pairwise stats. Pass if: divergence_index length equals `only_in_a + only_in_b`; entries are time-sorted; all required fields present; boolean flags consistent with source variant.
**Evidence:** Terminal output showing divergence_index length matches `only_in_a + only_in_b`; first and last 3 entries printed with all fields; sort-order verification.

---

## Area: Variant UI (VAL-VUI-xxx)

### VAL-VUI-001: Variant selector dropdown visible in compare.html config panel
**Behavioral description:** Opening `compare.html` in a browser shows a dropdown (or equivalent selector control) in the configuration panel labeled "Variant" or "Detector Variant". The dropdown lists at least two options: `a8ra_v1` and `luxalgo_v1`. The dropdown is styled consistently with the existing dark theme (background `--surface`, border `--border`, text `--text`, font IBM Plex Sans). The default selected value is `a8ra_v1` or is determined by the loaded JSON data's variant field. Pass if: the dropdown is visible, lists both variants, and matches the design system styling.
**Evidence:** Screenshot of the config panel showing the variant selector dropdown with both options listed; computed style inspection confirming dark theme tokens.

### VAL-VUI-002: Selecting luxalgo_v1 reloads chart with different detection markers
**Behavioral description:** On the Chart tab, user selects `luxalgo_v1` from the variant dropdown. The chart reloads detection markers using the luxalgo variant's data from the comparison JSON. The marker positions change visibly (different timestamps, different counts per VAL-LMSS-004). A loading indicator is shown during data switch if applicable. After switching, the detection count summary updates to reflect the luxalgo variant's counts. Switching back to `a8ra_v1` restores the original markers. Pass if: selecting `luxalgo_v1` changes visible markers on the chart; detection counts in the summary differ from `a8ra_v1`; switching back restores original markers.
**Evidence:** Screenshot with `a8ra_v1` selected showing N markers; screenshot with `luxalgo_v1` selected showing M markers (M ≠ N); screenshot after switching back showing N markers again.

### VAL-VUI-003: Stats dashboard shows variant name in headers
**Behavioral description:** On the Stats tab, when viewing variant comparison data, the section headers or column labels include the variant name (e.g., "MSS (a8ra_v1)" vs "MSS (luxalgo_v1)"). The variant name is visually distinguishable — rendered in `--text-muted` color or as a badge/tag alongside the primitive name. When a single variant is selected, only that variant's name appears. When comparing two variants, both names are visible in side-by-side columns. Pass if: variant names are visible in stats headers; switching variants updates the displayed name.
**Evidence:** Screenshot of Stats tab showing variant names in column/section headers for both compared variants.

### VAL-VUI-004: Marker labels indicate which variant produced the detection
**Behavioral description:** When both variants are displayed simultaneously on the chart, each detection marker includes a visual indicator of its source variant. This can be: (a) a text label suffix (e.g., "MSS [lux]" vs "MSS [a8ra]"), (b) distinct marker shapes per variant, or (c) tooltip text on hover showing `variant: luxalgo_v1`. The indicator is readable at the default chart zoom level. Pass if: hovering or visually inspecting markers reveals which variant produced each detection; the variant origin is unambiguous.
**Evidence:** Screenshot showing markers with variant indicators; screenshot of tooltip (if hover-based) showing variant name.

### VAL-VUI-005: Both variants visible simultaneously on chart (teal/amber colors)
**Behavioral description:** When variant comparison mode is active, the chart displays detections from both variants at the same time. Variant A (a8ra_v1) markers use the existing teal color set (`#26a69a` family). Variant B (luxalgo_v1) markers use an amber/orange color set (`#FF9800` or `#FFB74D` family). The two color sets are visually distinct and accessible (sufficient contrast against the dark background `#0a0e17`). A legend identifies which color corresponds to which variant. Pass if: both variant markers are visible simultaneously with distinct teal/amber coloring; a legend maps colors to variant names.
**Evidence:** Screenshot of chart showing teal markers (a8ra) and amber markers (luxalgo) overlaid on the same candle data; screenshot of the legend identifying color-to-variant mapping.

---

_Total assertions: 6 Variant Engine + 8 LuxAlgo MSS + 6 LuxAlgo OB + 4 Variant Eval + 5 Variant UI = 29 assertions_
