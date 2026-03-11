# Phase 2 Readiness Assessment
## a8ra Research Accelerator — Phase 1 → Phase 2 Transition

```yaml
date: 2026-03-08
assessor: Droid (automated assessment)
phase1_status: COMPLETE
test_suite: 378/378 PASS (50.59s)
branch: main (commit 81caf2e)
```

---

## 1. PHASE 2 SCOPE SUMMARY

Phase 2 is the **Evaluation Runner + Comparison Statistics** layer. Based on the build plan documents (`04_PHASE1_MISSION_BRIEF.md` §POST-MISSION, `01_RUNTIME_CONFIG_SCHEMA.yaml` §evaluation, `02_MODULE_MANIFEST.md` §Architecture):

### Phase 2 Deliverables

| Component | Description | Location (planned) |
|-----------|-------------|-------------------|
| **Evaluation Runner** | Run configs (locked vs. sweep candidates) against datasets | `src/ra/evaluation/runner.py` |
| **Pairwise Comparison** | Statistical comparison of detection sets between param configs | `src/ra/evaluation/comparison.py` |
| **Cascade Statistics** | Full funnel stats: detection_count, per_day, by_session, cascade_rate, cascade_completion | `src/ra/evaluation/cascade_stats.py` |
| **Structured Output** | Evaluation results export (JSON, charts) | `src/ra/output/results.py`, `json_export.py` |
| **Parameter Sweep** | Grid/sweep runner across `sweep_range` values without code changes | Part of runner |
| **Walk-Forward Validation** | Split dataset and validate stability | Part of runner |
| **River Adapter (full)** | Replace CSV stub with DuckDB parquet reader for 6–12 month data | `src/ra/data/river_adapter.py` |
| **Data Expansion** | Acquire 6–12 months EURUSD 1m from Dukascopy | External |

### Phase 2 Evaluation Metrics (from config)

```yaml
metrics:
  - detection_count
  - detections_per_day
  - by_session_distribution
  - cascade_rate          # e.g. displacement → MSS conversion rate
  - cascade_completion    # full chain from leaf to terminal
regime_slicing:
  enabled: false          # Phase 2+ when multi-month data available
  auto_tags: [atr_volatility, adx_trend_range, session]
```

---

## 2. FOUNDATION READINESS (What Phase 1 Delivered for Phase 2)

### ✅ Core Engine — READY

| Deliverable | Status | Evidence |
|------------|--------|----------|
| **PrimitiveDetector ABC** | ✅ Complete | `engine/base.py`: `detect(bars, params, upstream, context) → DetectionResult` |
| **Detection dataclass** | ✅ Complete | Includes `id`, `time`, `direction`, `type`, `price`, `properties`, `tags`, `upstream_refs` |
| **DetectionResult** | ✅ Complete | `primitive`, `variant`, `timeframe`, `detections`, `metadata`, `params_used` |
| **Deterministic IDs** | ✅ Complete | `{primitive}_{tf}_{timestamp_ny}_{direction}` via `make_detection_id()` |
| **CascadeEngine** | ✅ Complete | Topo-sort, upstream passing, cache, DAG invalidation via `on_param_change()` |
| **Registry** | ✅ Complete | Register by `(primitive_name, variant_name)`, lookup, has-check |
| **12 Detector Modules** | ✅ Complete | All 12 registered, 11 functional + 1 DEFERRED stub (equal_hl) |

### ✅ Config System — READY

| Deliverable | Status | Evidence |
|------------|--------|----------|
| **Pydantic v2 schema** | ✅ Complete | `config/schema.py`: `RAConfig` with `extra='forbid'` |
| **YAML loader** | ✅ Complete | `config/loader.py`: `load_config()`, `resolve_per_tf()`, `get_locked_params()` |
| **Locked baseline config** | ✅ Complete | `configs/locked_baseline.yaml` — full production params |
| **sweep_range fields** | ✅ Present in config | FVG floor, swing N/height, displacement ATR/body/close, session_liq gates, sweep wick_pct |
| **Per-TF overrides** | ✅ Complete | Swing N, height_filter_pips, displacement LTF/HTF, min_breach/reclaim_pips |
| **Dependency graph in config** | ✅ Complete | 14 nodes with upstream declarations |

### ✅ Data Layer — READY

| Deliverable | Status | Evidence |
|------------|--------|----------|
| **CSV loader** | ✅ Complete | `data/csv_loader.py` — loads 7,177 1m bars |
| **TF aggregator** | ✅ Complete | `data/tf_aggregator.py` — 1m → 5m/15m/1H/4H/1D |
| **Session tagger** | ✅ Complete | `data/session_tagger.py` — session, kill_zone, ny_window, forex_day |
| **River adapter stub** | ✅ Stub only | `data/river_adapter.py` — `NotImplementedError` on all River methods, `load_from_csv()` delegates |

### ✅ CLI Pipeline — READY

| Deliverable | Status | Evidence |
|------------|--------|----------|
| **run.py** | ✅ Complete | `--config`, `--data`, `--output`, `--timeframes`, JSON output per primitive per TF |
| **JSON export** | ✅ Complete | Per-detection JSON with full provenance (id, params_used, metadata) |

### ✅ Test Suite — GREEN

| Metric | Value |
|--------|-------|
| Total tests | 378 |
| Pass rate | 100% (378/378) |
| Runtime | 50.59s |
| Regression fixtures | 32 baseline JSON files |
| Coverage areas | All 12 detectors + cascade + config + data layer + regression |

---

## 3. GAPS AND RISKS

### 🔴 GAP: Evaluation Package — Empty Placeholder

**Location:** `src/ra/evaluation/__init__.py` (1 line: docstring only), `src/ra/output/__init__.py` (1 line)

**Impact:** Phase 2's primary deliverables (runner, comparison, cascade_stats) must be built from scratch. No existing code exists in these directories.

**Risk Level:** LOW — this is *expected*. These are Phase 2 deliverables. The Phase 1 foundation provides all necessary interfaces.

### 🟡 GAP: sweep_range Values Exist in Config but No Sweep Runner

**Detail:** The `locked_baseline.yaml` has `sweep_range` fields for every tunable parameter (FVG floor: `[0.0, 0.5, 1.0, 1.5, 2.0]`, displacement ATR multiplier: `[1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]`, etc.), but there is NO code to iterate over them. The `extract_locked_params_for_cascade()` function in `cascade.py` hardcodes locked values only.

**Impact:** Phase 2 must build the sweep extraction logic. The config schema already has the data; it needs a `extract_sweep_combos()` function.

**Risk Level:** LOW — straightforward to implement. Schema already supports it.

### 🟡 GAP: Config `get_locked_params()` Is Separate from Cascade's `extract_locked_params_for_cascade()`

**Detail:** There are two mechanisms for extracting params:
1. `config/loader.py` → `get_locked_params(config, primitive)` — generic, pydantic-aware
2. `engine/cascade.py` → `extract_locked_params_for_cascade(config)` — hardcoded per-primitive dict

The cascade function (`extract_locked_params_for_cascade`) has all 14 primitives' params hardcoded rather than dynamically extracting from the config object. This means any config schema change requires updating TWO places.

**Risk Level:** MEDIUM — Phase 2 sweep runner should use the generic `get_locked_params()` path, not the hardcoded cascade one. The hardcoded version works for locked baseline regression but is brittle for parameter exploration.

### 🟡 GAP: No `sweep_example.yaml` Config

**Detail:** The `02_MODULE_MANIFEST.md` architecture section lists `configs/sweep_example.yaml` as an expected file. It does not exist.

**Risk Level:** LOW — Phase 2 deliverable, easy to create from existing locked baseline.

### 🟢 River Adapter — Stub-Only by Design

**Detail:** `river_adapter.py` raises `NotImplementedError` on all River methods. Only `load_from_csv()` works (delegates to `csv_loader.load_csv()`).

**Impact:** Phase 2 data expansion (6–12 months) requires implementing the full River adapter with DuckDB parquet queries.

**Risk Level:** LOW — The interface is well-specified in `03_RIVER_ADAPTER_SPEC.md`. The spec covers:
- `load_bars()` via DuckDB glob parquet
- `load_and_aggregate()` with TF alignment
- `available_range()` for data discovery
- `validate_integrity()` for gap/ghost checks
- Session tagging (already exists in `session_tagger.py`)
- Ghost bar handling (already exists in all detectors)

### 🟢 Equal HL — DEFERRED by Design

**Detail:** `equal_hl.py` raises `NotImplementedError`. The cascade engine handles this gracefully (provides empty `DetectionResult`).

**Impact:** None for Phase 2 — this is a methodology decision. Liquidity sweep has `equal_hl: {enabled: false}` in its level_sources.

---

## 4. KNOWN DEFERRED ISSUES (from Phase 1)

### From BASELINE_MANIFEST.md

1. **Displacement count discrepancy**: Pipeline emits 4,170 candidates on 1m (all candidates including below-threshold), vs. v0.5's 2,277 (filtered). The regression fixtures capture the full candidate set with grade metadata — this is the correct behavior per advisory review (`cto_q2_displacement: "819 is correct. Full candidate set with grade metadata."`).

2. **Swing count divergence**: 267 on 5m (current) vs. 163 (PROJECT_STATE.md historical). Current pipeline output is ground truth. PROJECT_STATE.md is stale.

3. **OB count divergence**: 37 on 5m (current) vs. 106 (PROJECT_STATE.md historical). This is because v0.5 OB now requires MSS (not just displacement). Current pipeline is ground truth.

### From Advisory Synthesis

4. **Temporal gating table for sweep levels**: RESOLVED — canonical table documented in `05_ADVISORY_SYNTHESIS.yaml` §temporal_gates. Must be respected by any Phase 2 runner that evaluates sweep-level changes.

5. **Cluster-straddle timestamp handling (MSS)**: RESOLVED — displacement indexed by first bar of cluster. Verified in pipeline code.

6. **PWH/PWL hardcoded for 1-week dataset**: Pipeline uses hardcoded `2024-01-07T17:00:00` for the 5-day calibration dataset. Phase 2 River adapter must compute this dynamically for multi-week data.

### From Config Schema

7. **Regime slicing disabled**: `evaluation.regime_slicing.enabled: false` — requires multi-month data (Phase 2+ data expansion).

---

## 5. INTERFACE COMPATIBILITY ASSESSMENT

### PrimitiveDetector ↔ Evaluation Runner

The `PrimitiveDetector.detect(bars, params, upstream, context) → DetectionResult` interface is **fully compatible** with what Phase 2 needs:

- **Sweep runner** can call `detect()` with different `params` dicts (varying sweep_range values)
- **DetectionResult.params_used** provides provenance for comparison
- **DetectionResult.metadata** carries summary stats for aggregation
- **Detection.tags** carries session/kill_zone for by_session_distribution metric
- **Detection.upstream_refs** enables cascade_rate computation (tracing chains)

### CascadeEngine ↔ Evaluation Runner

The `CascadeEngine.run(bars_by_tf, params_by_primitive, timeframes)` API is **fully compatible**:

- `on_param_change()` + re-run enables efficient sweep (change one param, re-run only affected subtree)
- Cache serves unchanged upstream results (critical for sweep performance)
- Returns `dict[primitive][timeframe] → DetectionResult` — easy to diff between two runs

### Config Schema ↔ Sweep Runner

**Partially compatible:**
- `sweep_range` values are declared in config — ✅
- `locked` values serve as baseline — ✅
- No existing code to enumerate sweep combinations — ⚠️ Must build
- `extract_locked_params_for_cascade()` is hardcoded — ⚠️ Needs generic alternative

### River Adapter ↔ Data Expansion

**Interface-ready, implementation-pending:**
- River adapter spec fully documented (9 columns, ghost handling, TF alignment)
- CSV loader output already matches the Bar DataFrame contract
- Session tagger works on any DataFrame matching the contract
- TF aggregator works on any 1m DataFrame

---

## 6. ASSESSMENT

### Verdict: ✅ GO — Phase 1 Provides a Solid Foundation for Phase 2

### Justification

1. **All Phase 1 deliverables complete**: 12 detectors, cascade engine, config system, data layer, CLI, 378 green tests with regression fixtures.

2. **Interfaces are Phase 2-compatible**: `PrimitiveDetector.detect()` signature supports arbitrary params, `CascadeEngine.run()` supports param changes + cache invalidation, `DetectionResult` carries full provenance.

3. **Config schema already has sweep_range values**: No schema changes needed. Phase 2 needs only to build the runner that enumerates and executes sweep combinations.

4. **No architectural blockers**: The empty `evaluation/` and `output/` directories are intentional placeholders per the build plan.

5. **Test infrastructure is solid**: 378 tests with 32 golden-file regression fixtures provide a safety net for Phase 2 changes.

### Recommended Phase 2 Start Actions

1. **Build `evaluation/runner.py`** — iterate sweep_range combos, call `engine.run()`, collect DetectionResults
2. **Build `evaluation/comparison.py`** — pairwise diff of DetectionResult sets (count deltas, session distributions, etc.)
3. **Build `evaluation/cascade_stats.py`** — cascade_rate and cascade_completion from upstream_refs chains
4. **Build `output/results.py` + `output/json_export.py`** — structured output for review
5. **Refactor param extraction** — replace hardcoded `extract_locked_params_for_cascade()` with a generic `extract_params(config, mode='locked'|'sweep')` that reads dynamically from the pydantic model
6. **Create `configs/sweep_example.yaml`** — example sweep config per the module manifest
7. **River adapter** — implement when Dukascopy data acquisition is ready (can be parallel track)

### Pre-Conditions Already Met

- [x] Branch merge: phase1 → main (commit 81caf2e)
- [x] Regression suite green (378/378)
- [x] Advisory synthesis resolved all reviewer items
- [x] No known latent bugs in detection logic
- [x] Config schema supports sweep exploration
- [x] Cascade engine supports incremental re-run with caching

---

*Assessment generated 2026-03-08 by automated readiness review.*
