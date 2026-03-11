# A8RA RESEARCH ACCELERATOR SPEC — Audit Report
## Spec vs. Actual Codebase (as of 2026-03-09)

**Spec file:** `research_accelerator_refactor/A8RA_RESEARCH_ACCELERATOR_SPEC.md`  
**Spec version:** 0.1 PROPOSAL (2026-03-08)  
**Audit date:** 2026-03-09  
**Audit method:** Systematic comparison of each spec section against actual source files.

---

## Section-by-Section Audit

| Spec Section | Status | Key Discrepancies |
|---|---|---|
| §1 Executive Summary | **Partially Outdated** | The "problem" framing and 6-hour sweep session are historical context — still valid as motivation, but the RA *is now built*. The proposal language ("elevate calibration from a disposable tool") reads as if the system doesn't exist yet. |
| §2 Design Principles | **Accurate** | P1-P6 are faithfully implemented as architectural constraints. Config-over-code (P2) is enforced via YAML. Comparative-by-default (P3) is implemented in the comparison module. |
| §3.1 System Overview | **Accurate** | The 4-component architecture (Data Layer → Detection Engine → Evaluation Runner → Comparison Interface) matches the actual `src/ra/` package structure exactly. |
| §3.2 Data Layer | **Partially Accurate** | See detailed notes below. |
| §3.3 Detection Engine | **Mostly Accurate** | Interface matches closely; module table needs updating. See details below. |
| §3.4 Evaluation Runner | **Mostly Accurate** | Core is built; cascade evaluation and walk-forward implemented. See details below. |
| §3.5 Comparison Interface | **Significantly Different** | No FastAPI/WebSocket backend. Static files + Python HTTP server instead. See details below. |
| §4 Liquidity Sweep Case Study | **Still Aspirational** | The "instant re-computation" workflow described is not yet fully realized. The comparison interface loads pre-computed JSON, not real-time re-computation. |
| §5 Build Plan | **Outdated** | Phases 1-3 are complete. Timelines don't reflect actual build. Test count far exceeds spec expectations. |
| §6 What Carries Forward | **Partially Outdated** | `preprocess_data_v2.py` is referenced as the source — it's still mentioned in detector docstrings but the migration is complete. |
| §7 Long-Term Vision | **Accurate** | These are still future goals. |
| §8 Decision Requested | **Obsolete** | Decisions were made; this section is no longer actionable. |
| §9 Calibration Agenda | **Obsolete** | These were pre-build items. |
| Addendum A | **Mostly Built** | Ground truth, heatmap, walk-forward are all implemented. See details. |
| Addendum B | **Not Built** | Forensic Case Runner does not exist in codebase. |
| Addendum C | **Not Built** | Search Orchestrator / Micro-Search not implemented. |

---

## Detailed Section Findings

### §3.2 Data Layer

| Spec Claim | Actual Reality | Discrepancy |
|---|---|---|
| Storage: "Parquet or HDF5" local file store | **Parquet via DuckDB** (`RiverAdapter` reads `~/phoenix-river/{pair}/{year}/{mm}/{dd}.parquet`). Also CSV loader (`csv_loader.py`) for legacy data. | Spec was vague ("Parquet or HDF5") — actual is **Parquet only** via DuckDB. No HDF5. |
| Source: "Dukascopy 1m tick data" | Actual: **Phoenix River** parquet files (from IBKR via phoenix-river pipeline). Also CSV fallback. | Source is now IBKR/Phoenix River, not Dukascopy. Spec should be updated. |
| River adapter | **Built** — `src/ra/data/river_adapter.py`. DuckDB-backed, reads daily parquet files, normalizes Bangkok→UTC→NY timezone. Read-only invariant (`INV-RA-RIVER-READONLY`). | Spec doesn't mention River adapter by name — it was built as the primary data interface. |
| TF Aggregation | **Built** — `src/ra/data/tf_aggregator.py` + 4H forex-aligned in `RiverAdapter`. Supports 1m→5m/15m/1H/4H/1D. | Matches spec. 4H forex-day-aligned aggregation is an addition not in spec. |
| Regime tagging | **NOT BUILT** — `evaluation.regime_slicing.enabled: false` in config. Session tagging is built (`session_tagger.py`: session, kill_zone, ny_window, forex_day). No ATR/ADX regime classification. | Spec proposed automated ATR/ADX regime tagging + manual curation. Only session-level tagging exists. Regime slicing is disabled. |
| Session tagging | **Built** — 6 categories: asia, pre_london, lokz, pre_ny, nyokz, other. Kill zones: lokz, nyokz. NY windows: a (08-09), b (10-11). Forex day boundary: 17:00 NY. | Matches spec sessions. |

### §3.3 Detection Engine

**Base class interface:**

| Spec Interface | Actual Interface | Delta |
|---|---|---|
| `PrimitiveDetector` with `primitive_name`, `variant_name`, `version`, `source`, `source_reference` | `PrimitiveDetector` ABC with `primitive_name`, `variant_name`, `version`. **No** `source` or `source_reference` attributes. | Minor: `source` and `source_reference` fields not implemented. |
| `detect(bars, params, upstream, context)` → `DetectionResult` | Identical signature: `detect(bars, params, upstream, context)` → `DetectionResult` | ✅ Match |
| `DetectionResult` has `detections`, `metadata`, `params_used` | Actual has `primitive`, `variant`, `timeframe`, `detections`, `metadata`, `params_used` | Actual has **3 extra fields** (primitive, variant, timeframe) — more complete than spec. |
| `Detection` has `time`, `type`, `price`, `properties`, `tags`, `upstream_refs` | Actual has `id`, `time`, `direction`, `type`, `price`, `properties`, `tags`, `upstream_refs` | Actual has `id` (deterministic) and `direction` (separate from `type`). Spec's `type` field split into `type` + `direction`. |
| No `required_upstream()` method in spec | Actual has `required_upstream()` abstract method | Addition: detectors self-declare their upstream deps. |

**Module table (spec vs. actual):**

| Spec Module | Actual Module | Status |
|---|---|---|
| `SwingPointDetector` | `SwingPointDetector` (`swing_points.py`) | ✅ Built |
| `EqualHLDetector` | `EqualHLDetector` (`equal_hl.py`) | ⚠️ Built but DEFERRED status in config |
| `FVGDetector` | `FVGDetector` (`fvg.py`) | ✅ Built (handles FVG + IFVG + BPR as virtual sub-nodes) |
| `DisplacementDetector` | `DisplacementDetector` (`displacement.py`) | ✅ Built — significantly more complex than spec anticipated (clusters, decisive override, quality grades) |
| `MSSDetector` | `MSSDetector` (`mss.py`) | ✅ Built |
| `OrderBlockDetector` | `OrderBlockDetector` (`order_block.py`) | ✅ Built |
| `LiquiditySweepDetector` | `LiquiditySweepDetector` (`liquidity_sweep.py`) | ✅ Built — complex multi-source level pooling |
| `AsiaRangeDetector` | `AsiaRangeDetector` (`asia_range.py`) | ✅ Built |
| `OTEDetector` | `OTEDetector` (`ote.py`) | ✅ Built |
| `IFVGDetector` | Virtual node (handled by FVG detector) | Different: not a separate class, it's a state transition on FVG |
| `BPRDetector` | Virtual node (handled by FVG detector) | Different: not a separate class, geometric overlap computed by FVG |
| Not in spec | `SessionLiquidityDetector` (`session_liquidity.py`) | **New**: 4-gate efficiency model for session boxes (asia, pre-london, pre-ny) |
| Not in spec | `ReferenceLevelDetector` (`reference_levels.py`) | **New**: PDH/PDL, midnight open, equilibrium |
| Not in spec | `HTFLiquidityDetector` (`htf_liquidity.py`) | **New**: Higher-TF liquidity levels (EQH/EQL on 1H/4H/1D) |

**Cascade dependency graph:** The spec's cascade diagram is conceptually correct but the actual `dependency_graph` in `locked_baseline.yaml` is significantly more detailed with 14 nodes including session_liquidity, reference_levels, htf_liquidity, and the virtual ifvg/bpr nodes.

**`preprocess_data_v2.py` reference:** The spec says primitives are "migrated from `preprocess_data_v2.py`". The migration is **complete** — all detectors are standalone modules. `preprocess_data_v2.py` is still referenced in detector docstrings as the legacy source but is not imported or used by the RA.

**External algo integration:** **NOT BUILT**. No external variants exist. No PineScript transpilation infrastructure. All detectors are `a8ra_v1` variant only.

**Parameter configuration:** The spec shows a simple YAML config structure. Actual `locked_baseline.yaml` is **far more detailed** — includes sweep ranges, per-TF overrides, state machines, quality grades, evaluation order, and dependency graph. Significantly richer than spec anticipated.

### §3.4 Evaluation Runner

| Spec Feature | Actual Status | Notes |
|---|---|---|
| Statistical comparison engine | **Built** — `comparison.py`: `compute_stats()`, `compare_pairwise()`, `compare_multi()` | Per-primitive/TF stats, session distribution, direction distribution, pairwise agreement rates, divergence index |
| Cascade evaluation | **Built** — `cascade_stats.py`: `cascade_funnel()`, `cascade_completion()` | Multi-level funnel (leaf→composite→terminal), conversion rates, chain tracking |
| Walk-forward validation | **Built** — `walk_forward.py`: `WalkForwardRunner` with `generate_windows()`, verdicts (STABLE/CONDITIONALLY_STABLE/UNSTABLE) | Calendar-month windows, configurable train/test/step, multiple metrics |
| Parameter stability sweep | **Built** — `runner.py`: `run_sweep()`, `run_grid()` | 1D and 2D grid sweeps, cache-aware incremental re-runs via `on_param_change()` |
| Regime-sliced evaluation | **NOT BUILT** — `regime_slicing.enabled: false` | Framework exists in config schema but no actual regime tagging or slicing |
| Output format: YAML + CSV | **JSON** output only — `json_export.py` with Schemas 4A-4E | Spec said YAML+CSV; actual is structured JSON with well-defined schemas |
| CLI entry point | **Built** — `eval.py` with subcommands: `sweep`, `compare`, `walk-forward` | Also `run.py` for basic cascade execution |
| Divergence indexing | **Built** — per-detection diff list in `compare_pairwise()` | Timestamps where configs disagree |

### §3.5 Comparison Interface

| Spec Feature | Actual Status | Notes |
|---|---|---|
| "FastAPI backend + WebSocket" | **NOT BUILT** — Static HTML/JS files served via `http.server` (`serve.py`). No FastAPI, no WebSocket. | Spec's tech stack recommendation was not followed. Simpler Python stdlib HTTP server with POST endpoints. |
| Chart overlay (Lightweight Charts) | **Built** — `chart-tab.js` with Lightweight Charts v4.1.3 | Multi-config overlay, session bands, TF switching, day navigation, detection markers |
| Stats dashboard | **Built** — `stats-tab.js` | Per-primitive stats, session/direction distributions, cascade funnel visualization via Plotly |
| Parameter heatmap | **Built** — `heatmap-tab.js` | 2D Plotly heatmap from sweep data, lock marker, 1D degenerate support |
| Walk-forward tab | **Built** — `walkforward-tab.js` | Train vs test chart, verdict badge, summary stats, window detail panel |
| Ground truth annotation | **Built** — `ground-truth.js` (compare mode) + `validate-gt.js` (validation mode) | Click-to-label popover (CORRECT/NOISE/BORDERLINE), colored rings, persistence (localStorage in Mode 1, disk via serve.py in Mode 2) |
| Lock + provenance panel | **Built** — in `ground-truth.js` | Shows locked params, WF verdict, notes input, Record Lock button |
| "Instant re-computation" | **NOT BUILT** — Charts load pre-computed JSON; no real-time param change → re-run | Pre-computed via `eval.py` or `site/detect.py`, not live |
| Divergence navigator | **Built** — `divergence.js` | Filter by primitive/TF, click to jump to divergent detections |
| Tabs: Chart, Stats, Heatmap, Walk-Forward | **All 4 tabs built** | In `compare.html` |

### Phase 3.5 Validation Mode (NOT IN SPEC)

This is an **entire feature** built after the spec was written:

- `site/validate.html` — Detection browser for visual validation
- `site/detect.py` — CLI batch generator reading River data, running cascade, outputting per-week JSON
- `site/serve.py` — HTTP server with POST endpoints for label/lock-record persistence to disk
- `site/js/validate-app.js`, `validate-chart.js`, `validate-gt.js` — Full validation mode frontend
- Supports week-by-week navigation, detection filtering by threshold, ground truth labeling with disk persistence

### §5 Build Plan

| Spec Phase | Spec Estimate | Actual Status |
|---|---|---|
| Phase 1: Detection Engine + Data Layer | 2-3 days | **COMPLETE** — all 12 detectors built, cascade engine, data layer with River adapter, CSV loader, TF aggregator, session tagger |
| Phase 2: Evaluation Runner + Comparison Stats | 1-2 days (revised to 2-3 in Addendum) | **COMPLETE** — runner, comparison, cascade stats, walk-forward, param extraction, JSON export |
| Phase 3: Comparison Interface | 2-3 days | **COMPLETE** — 4-tab interface (chart, stats, heatmap, walk-forward), ground truth, lock panel, divergence navigator |
| Phase 3.5: Validation Mode | **Not in spec** | **COMPLETE** — batch detection generator, validation browser, disk-persisted labels |
| Phase 4: External Algo Integration | Ongoing | **NOT STARTED** |
| Phase 5: Production Monitoring | Future | **NOT STARTED** |
| Total spec estimate: 7-12 days for Phases 1-3 | — | Phases 1-3.5 are fully built. |
| Test count (spec: none specified) | — | **631 tests** across 26 test files |

### Addendum A

| Feature | Spec Status | Actual Status |
|---|---|---|
| Ground Truth Annotation Layer (A1) | IN — Phase 3 | **BUILT** — `ground-truth.js` + `validate-gt.js`. Click-to-label, 3 labels (CORRECT/NOISE/BORDERLINE), colored rings, persistence, export. Precision/recall/F1 computation from labels is **NOT built** (no scoring in evaluation runner). |
| Parameter Stability Surface (A2) | IN — Phase 2 | **BUILT** — `runner.run_grid()` for 2D sweeps, `heatmap-tab.js` for visualization. **Automated plateau detection is NOT built** — heatmap renders but no algorithmic plateau/cliff-edge identification. |
| Walk-Forward Validation (A3) | IN — Phase 2 | **BUILT** — `WalkForwardRunner`, verdicts (STABLE/CONDITIONALLY_STABLE/UNSTABLE), summary stats, per-window results, walkforward-tab.js visualization. **Regime diagnosis (cross-reference with regime tags) NOT built** due to no regime tagging. Walk-forward required field in lock record: **partially built** (lock panel shows WF verdict). |
| Signal Decay / Half-Life (A4) | Deferred — Phase 5+ | **NOT BUILT** |
| Event Concordance Matrix (A4) | Deferred — Phase 5+ | **NOT BUILT** |
| Monte Carlo Permutation (A5) | Not planned | **NOT BUILT** |
| Deflated Detection Rate (A5) | Not planned (provenance covers it) | **NOT BUILT** |

### Addendum B — Forensic Case Runner

**NOT BUILT.** No `cases/` directory, no event case files, no case replay engine, no cascade failure diagnostics, no near-miss analysis. Zero code related to this feature exists in the codebase.

### Addendum C — Search Orchestrator / Micro-Search

**NOT BUILT.** No search orchestrator, no multi-objective optimization, no Pareto frontier computation, no source pool exploration, no micro-search. Zero code related to this feature exists in the codebase.

---

## Critical Updates Needed

To make the spec reflect current reality, these changes are most important:

1. **Change spec status from "PROPOSAL" to "IMPLEMENTED (Phases 1-3.5)"** — The document reads as a proposal for something that doesn't exist. It does exist now.

2. **Update data layer section (§3.2):**
   - Data source: Phoenix River (IBKR parquet) via DuckDB, not Dukascopy
   - Storage: Parquet only (no HDF5)
   - Add River adapter details (`RiverAdapter` class)
   - Note regime tagging is NOT implemented (only session tagging)

3. **Update detection engine module table (§3.3):**
   - Add 3 new modules: `SessionLiquidityDetector`, `ReferenceLevelDetector`, `HTFLiquidityDetector`
   - Update IFVG/BPR as virtual nodes handled by FVG, not separate classes
   - Update `PrimitiveDetector` interface to include `required_upstream()`, `id` field on Detection, `direction` field
   - Note: external algo integration (§3.3.3) is NOT built

4. **Update comparison interface tech stack (§3.5):**
   - Replace "FastAPI + WebSocket" with "Python stdlib HTTP server (`http.server`) + static HTML/JS"
   - No real-time re-computation — pre-computed JSON loaded by frontend
   - `serve.py` handles POST for label/lock-record persistence

5. **Update output format (§3.4):**
   - Replace "YAML + CSV" with "JSON (Schemas 4A-4E)"

6. **Add Phase 3.5 Validation Mode section** — entirely missing from spec

7. **Update build plan timelines and test count** — 631 tests, all phases 1-3.5 complete

8. **Mark Addendum B (Forensic Case Runner) and C (Search Orchestrator) as NOT BUILT**

9. **Update §8 (Decision Requested) and §9 (Calibration Agenda)** — these are obsolete

---

## What's Built But Not In Spec

| Feature | Location | Description |
|---|---|---|
| **Phase 3.5 Validation Mode** | `site/validate.html`, `site/detect.py`, `site/serve.py`, `site/js/validate-*.js` | Full detection browser with week navigation, threshold filtering, ground truth labeling with disk persistence |
| **River Adapter** | `src/ra/data/river_adapter.py` | DuckDB-backed Phoenix River parquet reader with timezone normalization, 4H forex-aligned aggregation, integrity validation |
| **SessionLiquidityDetector** | `src/ra/detectors/session_liquidity.py` | 4-gate efficiency model for Asia/pre-London/pre-NY session boxes |
| **ReferenceLevelDetector** | `src/ra/detectors/reference_levels.py` | PDH/PDL, midnight open, equilibrium levels |
| **HTFLiquidityDetector** | `src/ra/detectors/htf_liquidity.py` | Higher-TF EQH/EQL with fractal detection, rotation requirements |
| **Deterministic Detection IDs** | `src/ra/engine/base.py` | `make_detection_id()` producing `{primitive}_{tf}_{timestamp_ny}_{direction}` format |
| **JSON export schemas (4A-4E)** | `src/ra/output/json_export.py` | 5 structured output schemas for evaluation runs, comparison, sweep, walk-forward |
| **Param extraction system** | `src/ra/evaluation/param_extraction.py` | `extract_params()`, `extract_sweep_combos()` — resolves locked/sweep modes from config |
| **Config schema + loader** | `src/ra/config/schema.py`, `src/ra/config/loader.py` | Pydantic-based config validation with `RAConfig` model |
| **Divergence navigator** | `site/js/divergence.js` | Detection-level divergence browsing between configs |
| **631 tests across 26 files** | `tests/` | Comprehensive test suite including regression fixtures |
| **Displacement quality grades** | In displacement detector + config | STRONG/VALID/WEAK grading, decisive override, cluster-2 detection — far beyond spec's simple ATR+body params |
| **OB state machine** | Config + detector | ACTIVE→MITIGATED→INVALIDATED→EXPIRED with fallback scan |
| **FVG state machine** | Config + detector | ACTIVE→CE_TOUCHED→BOUNDARY_CLOSED→IFVG transitions |

---

## What's In Spec But Not Built

| Spec Item | Section | Priority |
|---|---|---|
| **External algo integration** — PineScript transpilation, external variants, benchmarking | §3.3.3, Phase 4 | Deferred (spec Phase 4) |
| **Regime tagging** — ATR-based volatility, ADX-based trend/range, manual event tags | §3.2 | Important gap — affects walk-forward diagnosis |
| **Regime-sliced evaluation** — per-regime statistics and diagnosis | §3.4, §A3 | Blocked by no regime tagging |
| **Instant re-computation** — change param → chart updates without pipeline run | §3.5.2 | Not built; would require significant backend work |
| **Precision/recall/F1 from ground truth labels** — scoring in evaluation runner | Addendum A1 | Labels are collected but not fed into evaluation metrics |
| **Automated plateau detection** — algorithmic identification of stable regions in heatmaps | Addendum A2 | Heatmap renders but no plateau/cliff-edge auto-detection |
| **Walk-forward regime diagnosis** — cross-reference weak windows with regime tags | Addendum A3 | Blocked by no regime tagging |
| **Production monitoring** — live data ingestion, regime drift alerts | §5 Phase 5 | Future |
| **Forensic Case Runner** — event replay, cascade failure diagnosis, near-miss analysis | Addendum B | Not started |
| **Search Orchestrator** — automated parameter discovery, Pareto optimization | Addendum C | Not started |
| **Micro-Search** — event-centered local parameter exploration | Addendum C | Not started |
| **Signal decay / half-life analysis** | Addendum A4 | Deferred |
| **Event concordance matrix** | Addendum A4 | Deferred |
| **Lock provenance with walk-forward required field** (fully enforced) | Addendum A3 | Partially built — WF verdict shown in lock panel but not a hard gate |
| **Multi-instrument support** | §7 | Not started |
