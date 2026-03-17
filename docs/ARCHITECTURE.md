# a8ra Research Accelerator — System Architecture

Dense M2M reference. A fresh session reads this and orients without briefing.

---

## 1. System Overview

**Purpose**: Research platform for calibrating and validating ICT primitive detection against expert annotations.

**Relationship to core a8ra**: RA proves detection quality → core consumes locked parameters for production. RA is the research arm; core is the deployment arm.

**Design Principles**:
- Quality > speed — every lock requires Olya visual confirmation
- Olya as oracle — her visual judgment is the final gate (INV-OLYA-ABSOLUTE)
- L1/L2 separation — detection engine (L1) is independent from strategy interpretation (L2)
- Fitness function: precision/recall against Olya's annotations, never trading metrics

---

## 2. Detection Engine

### CascadeEngine
14-node dependency graph, resolved by topological sort. TF-agnostic — same detector runs on 1m through 1D.

**Entry points**:
- `detect.py` — CLI. `--full` emits enriched output (all properties, tags, upstream_refs). `--pair EURUSD`.
- `run.py` — Phase 1 pipeline entry.
- `eval.py` — Evaluation engine entry (sweep, compare, walk-forward).

**Dependency graph** (roots → terminals):
```
FVG, SwingPoints, Displacement, SessionLiquidity, AsiaRange, ReferenceLevels
  ├─ IFVG ← FVG
  ├─ BPR ← FVG
  ├─ EqualHL ← SwingPoints (DEFERRED)
  ├─ HTFLiquidity ← SwingPoints
  ├─ MSS ← {SwingPoints, Displacement, FVG}
  ├─ OrderBlock ← {Displacement, MSS}
  ├─ OTE ← MSS
  └─ LiquiditySweep ← {SessionLiquidity, ReferenceLevels, HTFLiquidity, SwingPoints, Displacement}
```

### Locked L1 Primitives: 13/13

All primitive detectors LOCKED per `SYNTHETIC_OLYA_METHOD_vLOCK.yaml`. No parameter changes without Olya calibration session.

### L1.5 Parameters

- **LTF (1m/5m/15m)**: LOCKED — displacement body_ratio=0.60, atr_multiplier=1.50, MSS confirmation_window=3, swing N per-TF.
- **HTF (1H/4H/1D)**: PROPOSED — displacement body_ratio=0.65, MSS confirmation_window=1/2, swing N=2, height_filter 3/8/15 pip. Derived from forensic analysis of 4 trades. Pending Olya visual confirmation.

### Detection Output Format

Enriched JSON per detection:
```yaml
id: displacement_4H_2025-09-24T00:00:00_bear
time: "2025-09-24T00:00:00"
direction: bearish
type: displacement
price: 0.00585
properties: {body_ratio, atr_multiple, quality_grade, ...}
tags: {session, forex_day}
upstream_refs: []
```

---

## 3. Data Architecture

### `site/data/candles/`
Per-week candle files (`2025-W36.json` through `2026-W08.json`). Each file contains candles keyed by TF: `{1m, 5m, 15m, 1H, 4H, 1D}`. 25 weeks EURUSD, Sep 2025 – Feb 2026.

### `site/data/detections/`
Per-week enriched detection files. Each contains `detections_by_primitive` → per-TF detection arrays. 105,917 total detections across all weeks and TFs.

### `site/data/sessions/`
Session classification data per week.

### `site/data/strategies/`
Saved strategy templates (JSON). Persisted via `serve.py`.

### `site/data/labels/`
Ground truth labels from validation mode (CORRECT/NOISE/BORDERLINE per detection).

### `site/data/lock-records/`
Primitive lock decision records with provenance.

### `site/data/weeks.json`
Manifest: week ID, date range, forex days, detection counts, bar counts per TF.

### `research/ground_truth/annotated_trades.yaml`
Olya's trade-level annotations (4 trades). Schema: id, date, pair, execution_time, kill_zone, direction, expected_state, execution_chain, htf_context, strategy_type.

---

## 4. Tool Suite

### 4a. Calibration Pages — `localhost:8100`

Six per-primitive charts: FVG, Swings, Displacement, OB, NY Windows, Asia Range. Plus HTF Liquidity page. All TFs including 1H/4H/1D.

**Serve**: `cd site && python3 -m http.server 8100`

### 4b. Comparison Interface — `localhost:8200/compare.html`

Multi-config overlay (Chart, Stats, Heatmap, Walk-Forward tabs). TF selector (1m–1D), week picker. Fixture mode + detection mode. Divergence navigator. Ground truth annotation. Continuous scrolling on HTF.

### 4c. Validation Mode — `localhost:8200/validate.html`

Ground truth labeling, lock panel, primitive toggles. TF selector (1m–1D), 25-week picker. Continuous scrolling, all-weeks HTF view. Disk persistence (`serve.py`) + localStorage fallback.

### 4d. Strategy Designer — `localhost:8200/strategy.html`

Chain composer (direction, steps with per-step TF, gates). Chain evaluator (direction/constraint/timing matching, near-miss). Chart overlays (green/amber bands, numbered step markers). Drill-down panel, convergence funnel. Cross-TF chains, template save/load, export/import.

### 4e. AutoResearch Harness — `tools/autoresearch/`

- `evaluate.py` — Run annotated trades through v2.1 phase classifier, score against ground truth, output structured diagnostics. Accepts `--param-overrides` for threshold tuning.
- `sweep.py` — Grid search over 6 classifier thresholds (5,120 combinations). `--dry-run` to preview.
- Ground truth: `research/ground_truth/annotated_trades.yaml`

**Serve**: `python3 site/serve.py` (port 8200 — validation, strategy, comparison all share this server)

---

## 5. State Detection Model (v2.1)

Reference: `research/STATE_DETECTION_LOGIC_v2.yaml`

### Three HTF Phases

| Phase | Detection | Direction Permission |
|-------|-----------|---------------------|
| **EXPANSION** | Daily MSS active + h1 aligned | WITH_EXPANSION only |
| **RETRACE** | Daily MSS active + h1 counter (swing-primary) | COUNTER_ALLOWED |
| **RANGE** | No daily MSS / key level + stall | BOTH (4H/1H authority) |

### Universal Event Cycle

Same 6-phase cycle on all TFs: LIQUIDITY_BUILD → RAID → CONFIRMATION → EXPANSION → RETRACE → POST_MOVE. HTF cycle provides direction permission. LTF cycle provides execution timing.

### Classifier Thresholds (tunable by AutoResearch)

| Parameter | Default | Sweep Range |
|-----------|---------|-------------|
| `h1_counter_persistence_bars` | 3 | 2–5 |
| `momentum_stall_window_daily_bars` | 3 | 2–5 |
| `key_level_tolerance_atr_factor` | 0.5 | 0.3–0.7 |
| `transition_lockout_h1_bars` | 2 | 1–4 |
| `retrace_to_range_daily_bars` | 3 | 2–5 |
| `kill_zone_realignment_lookback_hours` | 2 | 1–4 |

### Key v2.1 Refinements

- **h1_alignment**: swing structure primary, MSS confirming. Displacement-quality gate (body_ratio >= 0.60, grade >= VALID) prevents noise.
- **Kill zone realignment**: within LOKZ/NYOKZ, 15m/5m MSS in daily direction can restore ALIGNED when 1H counter has gone quiet (no opposing MSS in 2h).
- **4H MSS as daily proxy**: requires daily-scale displacement confirmation (2+ directional daily bars with body_ratio >= 0.60). Prevents local 4H events from establishing false daily direction.

---

## 6. Serving & Deployment

| Mode | Command | Port | Purpose |
|------|---------|------|---------|
| Static | `python3 -m http.server 8100 -d site` | 8100 | Calibration pages |
| Full | `python3 site/serve.py` | 8200 | Validation + Strategy + Compare (with persistence) |
| Detection | `python3 site/detect.py --full` | — | Regenerate detection data |
| AutoResearch | `python3 tools/autoresearch/evaluate.py` | — | Run trade evaluation |
| GitHub Pages | https://slimwojak.github.io/ra-tools/ | — | Static hosting, localStorage fallback |

---

## 7. Configuration

| File | Purpose |
|------|---------|
| `configs/locked_baseline.yaml` | LOCKED LTF + PROPOSED HTF parameters. Sweep ranges. Dependency graph. Per-TF overrides. |
| `SYNTHETIC_OLYA_METHOD_vLOCK.yaml` | Canonical L1 specification. DO NOT MODIFY. |
| `research/STATE_DETECTION_LOGIC_v2.yaml` | v2.1 state detection model (phase classifier rules). |

---

## 8. Key Constraints

- **L1/L2 boundary**: Strategy Designer consumes detection output, never modifies detection logic.
- **vLOCK immutable**: no primitive algorithm changes without Olya calibration session.
- **Fitness function**: precision/recall against Olya's annotations. Never trading metrics (P&L, Sharpe, RR).
- **Quality > speed**: every lock requires visual confirmation.
- **NY time everywhere**: EST (UTC-5). Forex day boundary: 17:00 NY.
- **Deterministic IDs**: `{primitive}_{tf}_{timestamp_ny}_{direction}` — reproducible across runs.
- **32-fixture regression**: any engine change must pass locked baseline regression suite.
- **AutoResearch scope**: tunes classifier thresholds ONLY, not L1.5 visual params.
