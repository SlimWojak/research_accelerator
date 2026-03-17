# PROJECT_STATE.md — a8ra Research Accelerator
## Checkpoint: 2026-03-17

> **Purpose**: Immediate orientation for Claude CTO and Olya's advisor. Read this FIRST.

---

## 1. Project Identity

**a8ra Research Accelerator** — Institutional-grade calibration and validation platform for ICT primitive detection.

- **Repo (local)**: `/Users/echopeso/research_accelerator`
- **Repo (GitHub)**: `SlimWojak/ra-tools` (deployment target)
- **Public URL**: https://slimwojak.github.io/ra-tools/validate.html (read-only, no label persistence)
- **Python**: ≥3.12 — pandas, duckdb, pyarrow, pydantic v2, pyyaml
- **Spec source**: `SYNTHETIC_OLYA_METHOD_vLOCK.yaml`

---

## 2. Phase Status

| Phase | Status | Key Output |
|---|---|---|
| **Phase 1: Detection Engine** | ✅ COMPLETE | 12 PrimitiveDetector modules, CascadeEngine with topological sort, 378 tests |
| **Phase 2: Evaluation Runner** | ✅ COMPLETE | Comparison, sweep, walk-forward, cascade stats, JSON schemas 4A–4E, 253 tests |
| **Phase 3: Comparison Interface** | ✅ COMPLETE | `compare.html` — 4 tabs (Chart, Stats, Heatmap, Walk-Forward), ground truth, lock panel, divergence navigator |
| **Phase 3.5: Validation Mode** | ✅ COMPLETE | `validate.html` — week-by-week detection browser, 25 weeks EURUSD (Sep 2025–Feb 2026), disk-persisted ground truth |
| **Phase 4: Variant Comparison, Ground Truth Scoring & Parameter Search** | ✅ COMPLETE | LuxAlgo MSS/OB variants, P/R/F1 scoring pipeline, `search.py` parameter optimizer, 65 validation assertions |
| **Phase 5: Strategy Designer** | ✅ COMPLETE | `strategy.html` — chain composer, evaluator engine, chart overlays, template persistence, enriched detection output |
| **Phase 5.5: HTF + State Detection** | ✅ COMPLETE | 1D detection enabled, v2.1 state detection spec, 4-trade validation, compare.html HTF parity |
| **Phase 5.6: AutoResearch Harness** | ✅ COMPLETE | `tools/autoresearch/` — evaluate.py (v2.1 classifier + scoring), sweep.py (grid search), ground truth dataset (4 trades, 4/4 PASS) |
| **Phase 6: Production Monitoring** | ⬜ NOT STARTED | Live data, regime drift alerts |

**Total: 985+ tests across 4 milestones. AutoResearch harness verified: 4/4 trades PASS at default v2.1 thresholds.**

---

## 3. Architecture Summary

| Layer | Description |
|---|---|
| **Data Layer** | Phoenix River (IBKR parquet via DuckDB), TF aggregation (1m→5m/15m/1H/4H/1D), session tagging (Asia/LOKZ/NYOKZ/KZ/NY windows/forex day). 25 weeks EURUSD, 105,917 detections. |
| **Detection Engine** | 12 detectors implementing `PrimitiveDetector` ABC, `CascadeEngine` with 14-node dependency graph (topological sort) |
| **Evaluation Runner** | Statistical comparison, parameter sweep (1D/2D grid), walk-forward validation, cascade funnel — all emit JSON schemas 4A–4E |
| **Comparison Interface** | Static HTML/JS + Plotly 2.35.2 + Lightweight Charts v4.1.3, served on port 8100 |
| **Validation Mode** | CLI batch generator (`detect.py`) + minimal write server (`serve.py` on port 8200) |
| **Strategy Designer** | `strategy.html` — chain composer consuming enriched detection output (`detect.py --full`), client-side evaluator, template persistence via `serve.py` |
| **State Detection** | v2.1 spec (`research/STATE_DETECTION_LOGIC_v2.yaml`), 3-phase HTF classifier, 4-trade validation |
| **AutoResearch** | `tools/autoresearch/evaluate.py` + `sweep.py` — Karpathy autoresearch pattern adapted for classifier threshold tuning |

**Key interfaces:**
- `PrimitiveDetector.detect(bars, params, upstream, context) → DetectionResult`
- Each detector declares `required_upstream()` for automatic dependency resolution
- Deterministic detection IDs: `{primitive}_{tf}_{timestamp_ny}_{direction}`

---

## 4. Detector Module Inventory

| # | Module | File | Status | Key Locked Params |
|---|--------|------|--------|-------------------|
| 1 | **FVG** (+ IFVG, BPR) | `fvg.py` | LOCKED | `floor_threshold_pips: 0.5` |
| 2 | **SwingPoints** | `swing_points.py` | LOCKED | `N: {1m:5, 5m:3, 15m:2}`, `height_filter_pips: {1m:0.5, 5m:3.0, 15m:3.0}` |
| 3 | **Displacement** | `displacement.py` | LOCKED | `atr_multiplier: 1.50`, `body_ratio: 0.60`, `close_gate: 0.25`, `combination_mode: AND` |
| 4 | **SessionLiquidity** | `session_liquidity.py` | LOCKED | `efficiency_threshold: 0.60`, `mid_cross_min: 2`, `balance_score_min: 0.30` |
| 5 | **AsiaRange** | `asia_range.py` | LOCKED | `tight_below_pips: 10`, `mid_range_pips: [10, 20]`, `wide_above_pips: 20`, `max_cap_pips: 30` |
| 6 | **ReferenceLevels** | `reference_levels.py` | LOCKED | PDH/PDL (forex day boundary), midnight open, equilibrium midpoint |
| 7 | **EqualHL** | `equal_hl.py` | DEFERRED | `tolerance_pips: 2.0`, `atr_factor: 0.1` |
| 8 | **MSS** | `mss.py` | LOCKED | `displacement_required: true`, `close_beyond_swing: true`, `fvg_tag_only: true` |
| 9 | **OrderBlock** | `order_block.py` | LOCKED | `trigger: displacement_plus_mss`, `zone_type: body`, `min_displacement_grade: VALID` |
| 10 | **HTFLiquidity** | `htf_liquidity.py` | LOCKED | `min_touches: 2`, per-TF tolerance/rotation/lookback |
| 11 | **OTE** | `ote.py` | LOCKED | `fib: [0.50, 0.618, 0.705, 0.79]`, `kill_zone_gate: true`, `P/D: wick-to-wick 0.50` |
| 12 | **LiquiditySweep** | `liquidity_sweep.py` | LOCKED | `rejection_wick_pct: 0.40`, per-TF return windows, multi-source level pooling, probe exhaustion, sweep event levels, LTF scope restriction |
| 13 | **LuxAlgo MSS** *(variant)* | `luxalgo_mss.py` | VARIANT | BOS/CHoCH, no displacement gate — fires ~2× more than a8ra |
| 14 | **LuxAlgo OB** *(variant)* | `luxalgo_ob.py` | VARIANT | Wick-to-wick order block zones |

**Dependency graph** (14 nodes including virtual IFVG/BPR):
- Roots (no upstream): FVG, SwingPoints, Displacement, SessionLiquidity, AsiaRange, ReferenceLevels
- Mid-tier: IFVG←FVG, BPR←FVG, EqualHL←SwingPoints, HTFLiquidity←SwingPoints
- Composite: MSS←{SwingPoints, Displacement, FVG}, OrderBlock←{Displacement, MSS}, OTE←MSS
- Terminal: LiquiditySweep←{SessionLiquidity, ReferenceLevels, HTFLiquidity, SwingPoints, Displacement}

---

## 5. Locked Threshold Filtering (Recent Fix)

`detect.py` applies post-cascade filtering for validation mode to eliminate noise below locked thresholds:

| Primitive | Filter | Gate Logic |
|---|---|---|
| **Displacement** | `atr_multiple >= 1.5` AND `body_ratio >= 0.6` | Locked AND gate |
| **FVG** | `gap_pips >= 0.5` | Floor threshold |
| **Swing Points** | `height_pips >= per-TF threshold` | 1m=0.5, 5m=3.0, 15m=3.0 |

**Impact**: Reduced total detections from **222,266 → 97,834** across 25 weeks of EURUSD data.

Commit: `4822d6e` — "Filter detections to locked thresholds in detect.py"

---

## 6. Deployment

| Mode | Command | Port | Purpose |
|---|---|---|---|
| Comparison | `python3 -m http.server 8100 -d site` | 8100 | Static serving of `compare.html` + calibration charts |
| Validation | `python3 site/serve.py` | 8200 | `validate.html` with POST endpoint for label/lock persistence |
| Strategy | `python3 site/serve.py` | 8200 | `strategy.html` chain composer + template persistence (shares serve.py with validation) |
| Detection gen | `python3 detect.py --config configs/locked_baseline.yaml --river EURUSD --start ... --end ... --output site/eval/` | — | Batch cascade run, outputs per-week JSON |
| Detection gen (enriched) | `python3 site/detect.py --full --start ... --end ... --output site/data/` | — | Full detection output with all properties, tags, upstream_refs (for Strategy Designer) |
| Public | https://slimwojak.github.io/ra-tools/validate.html | — | Read-only GitHub Pages deployment (no label persistence) |

---

## 7. File Manifest (Key Files Only)

### `src/ra/` — Detection Engine Package

| Path | Description |
|---|---|
| `config/schema.py`, `config/loader.py` | Pydantic v2 config schema + YAML loader (`extra='forbid'`) |
| `data/csv_loader.py` | Legacy CSV data loader |
| `data/river_adapter.py` | DuckDB-backed Phoenix River parquet reader (BKK→UTC→NY tz) |
| `data/tf_aggregator.py` | 1m→5m/15m/1H/4H/1D aggregation (4H forex-day-aligned) |
| `data/session_tagger.py` | Session, kill zone, NY window, forex day tagging |
| `detectors/*.py` | 12 PrimitiveDetector modules (see §4) |
| `detectors/_common.py` | Shared detection utilities |
| `engine/base.py` | `PrimitiveDetector` ABC, `DetectionResult`, `make_detection_id()` |
| `engine/cascade.py` | `CascadeEngine` — topological sort, upstream injection |
| `engine/registry.py` | Auto-discovery of detector modules |
| `evaluation/runner.py` | `EvaluationRunner` — sweep (1D/2D grid), locked replay |
| `evaluation/comparison.py` | Pairwise/multi-config comparison stats |
| `evaluation/cascade_stats.py` | Cascade funnel, completion rates |
| `evaluation/walk_forward.py` | `WalkForwardRunner` — sliding-window train/test validation |
| `evaluation/param_extraction.py` | Config → param combos resolver |
| `evaluation/label_ingestion.py` | Ground truth label loading from disk/export |
| `evaluation/scoring.py` | Precision/recall/F1 computation per primitive/session/variant |
| `evaluation/perturbation.py` | Config perturbation engine (numeric ±10–20%, categorical, seed-reproducible) |
| `evaluation/fitness.py` | Fitness scoring (P+R) + walk-forward stability + provenance |
| `detectors/luxalgo_mss.py` | LuxAlgo MSS variant detector (BOS/CHoCH) |
| `detectors/luxalgo_ob.py` | LuxAlgo OB variant detector (wick-to-wick zones) |
| `output/json_export.py` | JSON export (schemas 4A–4E) |

### `site/` — Frontend

| Path | Description |
|---|---|
| `index.html` | Landing page → 6 calibration charts + compare + validate |
| `compare.html` | Phase 3 comparison interface (4 tabs) |
| `validate.html` | Phase 3.5 validation mode (week picker + chart + labels) |
| `strategy.html` | Phase 5 strategy designer (chain composer + evaluator + overlays) |
| `detect.py` | CLI batch generator — cascade over River data → per-week JSON. `--full` flag outputs enriched detections (all properties, tags, upstream_refs) for Strategy Designer |
| `serve.py` | HTTP server with POST for label/lock/strategy persistence, GET for strategy listing/loading |
| `generate_eval_data.sh` | Generate single-config evaluation fixture |
| `generate_comparison_fixture.py` | Generate 2-config comparison fixture |
| `js/chart-tab.js` | LC candlestick chart with multi-config overlay |
| `js/stats-tab.js` | Plotly bar charts, funnel, session distribution |
| `js/heatmap-tab.js` | Plotly 2D/1D parameter sweep heatmap |
| `js/walkforward-tab.js` | Walk-forward time series + verdict badges |
| `js/divergence.js` | A-only/B-only detection navigator |
| `js/ground-truth.js` | Compare-mode ground truth annotation |
| `js/validate-app.js` | Validation mode app controller |
| `js/validate-chart.js` | Validation mode chart rendering |
| `js/validate-gt.js` | Validation mode ground truth + lock panel |
| `js/strategy-app.js` | Strategy Designer state management, data loading, week/day/TF navigation |
| `js/strategy-chart.js` | Strategy Designer chart rendering, session bands, chain highlight overlays, drill-down |
| `js/strategy-chain.js` | Chain builder UI + evaluator engine (direction/constraint/timing matching, near-miss) |
| `js/strategy-templates.js` | Template save/load (POST/GET via serve.py) |
| `js/shared.js` | Shared utilities (color maps, TF helpers) |

### `configs/`

| Path | Description |
|---|---|
| `locked_baseline.yaml` | Single source of truth — all locked params, sweep ranges, dependency graph, per-TF overrides |
| `search_space.yaml` | Parameter search space definition for `search.py` |

### `tests/` — 631 Tests

| Path | Coverage |
|---|---|
| `test_fvg.py`, `test_swing_points.py`, `test_displacement.py`, `test_mss.py`, `test_order_block.py`, `test_ote.py`, `test_liquidity_sweep.py`, `test_htf_liquidity.py`, `test_asia_range.py`, `test_session_liquidity.py`, `test_reference_levels.py` | Per-detector unit tests |
| `test_engine_base.py`, `test_cascade.py` | Engine ABC + cascade orchestration |
| `test_config.py`, `test_data_layer.py`, `test_river_adapter.py` | Config validation, data layer, River adapter |
| `test_evaluation_runner.py`, `test_evaluation_comparison.py`, `test_evaluation_cascade_stats.py`, `test_evaluation_walk_forward.py`, `test_evaluation_param_extraction.py` | Evaluation engine modules |
| `test_output.py`, `test_cli_eval.py` | JSON export, CLI integration |
| `test_regression.py` | Master regression suite — replays locked baseline against 32 fixture files for bit-exact reproduction |
| `test_integration.py` | End-to-end integration |

### Root

| Path | Description |
|---|---|
| `run.py` | CLI entry point for cascade pipeline (Phase 1) |
| `eval.py` | CLI entry point for evaluation engine — `sweep`, `compare`, `walk-forward` + `--variant-a/b`, `--labels` (Phase 2+4) |
| `search.py` | CLI entry point for parameter search — `--search-space`, `--iterations`, `--export-winner` (Phase 4) |
| `detect.py` | CLI entry point for validation data generation (Phase 3.5) |
| `serve.py` | HTTP server with label persistence (Phase 3.5) |
| `pyproject.toml` | Package metadata (Python ≥3.12, deps) |
| `configs/locked_baseline.yaml` | Production config |

---

## 8. Operating Rules (Carried Forward)

| Rule | Detail |
|---|---|
| **QUALITY > SPEED** | Take time, do it properly. No shortcuts. |
| **INV-OLYA-ABSOLUTE** | Olya's visual judgment is the final gate on all methodology decisions. Her word overrides all advisors. |
| **NY TIME everywhere** | EST (UTC−5). Never UTC in user-facing output. Forex day boundary: 17:00 NY. |
| **L1/L1.5/L2 separation** | L1=geometric detection (locked), L1.5=parameter thresholds (calibrating), L2=strategy interpretation (Olya's domain). |
| **Native per-TF detection** | All detection runs natively on each TF's aggregated bars. Never project 1m detections to higher timeframes. |
| **Config-over-code** | All params in YAML. `extra='forbid'` catches typos instantly. |
| **Deterministic IDs** | `{primitive}_{tf}_{timestamp_ny}_{direction}` — reproducible across runs. |
| **32-fixture regression** | Any engine change must pass the locked baseline regression suite. |

---

## 9. Calibration Status (as of 2026-03-13)

### State Detection Logic: v2.1

- **Spec**: `research/STATE_DETECTION_LOGIC_v2.yaml` — 3-phase event-cycle model (EXPANSION/RETRACE/RANGE)
- **Validation**: 4/4 trades classified correctly (reports/v2_trade_validation_2026-03-15.yaml)
- **HTF parameters**: PROPOSED (displacement body_ratio=0.65, swing N=2, height_filter per-TF)
- **AutoResearch**: evaluate.py 4/4 PASS at default thresholds. Sweep deferred until 10+ trades.
- **Ground truth**: 4 annotated trades in `research/ground_truth/annotated_trades.yaml`
- **1D detection**: Enabled in pipeline. Daily primitives visible in all tools.

### Primitive Lock Status: 13/13 LOCKED

| Status | Count | Primitives |
|--------|-------|------------|
| **LOCKED** | 13 | FVG, Swing Points, Displacement (LTF), MSS, Order Block, Session Liquidity, HTF EQH/EQL, Liquidity Sweep, Asia Range, NY Windows, HTF Displacement, HTF MSS, OTE |
| **DEFERRED** | 1 | Equal HL |

### Mechanisms Added During 2026-03-12 Calibration Session

| Mechanism | Description |
|-----------|-------------|
| **Pass-through consumption** | When a sweep breaches a level, all same-side levels in the bar's range are consumed |
| **Temporal guard** | `level.valid_from <= bar.time` prevents future-dated levels being consumed |
| **Sweep event levels** | After qualified sweep, the sweep extreme enters pool as SWEEP_EVENT (max depth=2, max age=3 sessions) |
| **Probe exhaustion** | 5 unresolved breaches without sweep confirmation -> PROBE_EXHAUSTED (resets after 3 bars without breach) |
| **Merge partitioning** | `_merge_levels()` partitions by `(side, forex_day)` — levels from different days never collapse |
| **LTF sweep scope** | PROMOTED_SWING excluded from 5m/1m pool (three-tier: M15 detect, M5 execute, M2 entry) |
| **Cross-TF cascade boundary** | L1 detects independently per TF; cross-TF signal flow is L2 strategy (annotated in YAML) |

### Sprint 64 Gate Status

Gate 3 (vLOCK methodology Olya-lock) COMPLETE — all 13 primitives LOCKED as of 2026-03-13.

Walk-forward stability: **PASS** — 25 weeks EURUSD (Sep 2025 – Feb 2026), all 39 active primitive/TF combos stable. Report: `reports/walk_forward_stability_2025-09_2026-02.yaml`.

## 10. What's Next

- **Walk-forward stability** — COMPLETE (PASS verdict, commit b641375)
- **Strategy Designer** — COMPLETE (Phase 5, commits 8376ac3–9393ab4)
- **1D Detection + HTF** — COMPLETE (detect.py, 7 JS files, compare.html fixes)
- **State Detection v2.1** — COMPLETE (spec, 4-trade validation, forensic analysis)
- **AutoResearch Harness** — COMPLETE (evaluate.py, sweep.py, ground truth dataset)
- **Documentation Refresh** — COMPLETE (ARCHITECTURE.md, TOOL_GUIDE.md, research/README.md)
- **Next**: Grow ground truth to 10+ trades → run sweep → Olya HTF calibration session → Production monitoring (Phase 6)

---

## 11. Recent Git History

```
(pending) AutoResearch harness + docs refresh + ground truth dataset
765f19b Fix compare.html HTF: week picker preserves all-weeks data + primitive markers on 1D
9f8fa1a V2.1 refinements + 1D detection enabled + 4-trade validation
9393ab4 Template save/load persistence — serve.py + strategy-templates.js
c9ddbf7 Chart overlays + drill-down panel — visual feedback layer
c66e6c4 Chain evaluator engine — core Strategy Designer logic
42e3a26 Strategy Designer scaffold — strategy.html + 4 JS modules + enriched data
8376ac3 detect.py: add --full flag for enriched Strategy Designer output
cc7f34a Rename SYNTHETIC_OLYA_METHOD_v0.6 → vLOCK, update all docs
b641375 Walk-forward stability run — 25-week EURUSD evaluation
8da6f3e OTE LOCKED — body-based OTE + wick-based P/D, 13/13 primitives complete
```

---

*Last updated: 2026-03-17*
