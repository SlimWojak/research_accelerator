# a8ra Research Accelerator — Phase 1 Mission Brief
## Detection Engine + Data Layer

```yaml
mission: RA_PHASE_1_DETECTION_ENGINE
type: Droid Mission Control — autonomous build
estimated_sessions: 3-4
model_allocation:
  planning_review: Opus (verify each deliverable against spec)
  implementation: Sonnet 4 / Codex (module extraction + tests)
repo: https://github.com/SlimWojak/research_accelerator
branch: phase1/detection-engine
base: main
```

---

## MISSION OBJECTIVE

Extract the monolithic `preprocess_data_v2.py` (2,816 lines) into a modular
detection engine where every primitive is a standalone module implementing
`PrimitiveDetector`, wired by a cascade dependency resolver, configured by
YAML — not code.

**Success criterion:** Running all locked configs on the 5-day dataset produces
identical detection output to the current pipeline. Byte-level regression PASS.

---

## PRE-MISSION SETUP (Human — before launching Mission Control)

### 1. Capture Regression Baseline

```bash
cd research_accelerator/pipeline
python preprocess_data_v2.py
# This regenerates all JSON in site/
# Copy the output as regression fixtures:
mkdir -p ../tests/fixtures/baseline_output
cp ../site/*_data_*.json ../tests/fixtures/baseline_output/
cp ../site/swing_data.json ../tests/fixtures/baseline_output/
cp ../site/displacement_data.json ../tests/fixtures/baseline_output/
cp ../site/ob_data.json ../tests/fixtures/baseline_output/
cp ../site/session_boundaries.json ../tests/fixtures/baseline_output/
cp ../site/metadata.json ../tests/fixtures/baseline_output/
```

### 2. Verify Dataset

```bash
ls -la research_accelerator/data/
# Should contain: eurusd_1m_2024-01-07_to_2024-01-12.csv (7,177 bars)
```

### 3. Create Branch

```bash
cd research_accelerator
git checkout -b phase1/detection-engine
```

---

## DELIVERABLES (Ordered)

Each deliverable is a discrete unit of work. Mission Control should complete
and verify each before moving to the next. Each deliverable has an explicit
verification step.

### D1: Project Scaffolding + Config Loader

**Files created:**
```
src/ra/__init__.py
src/ra/config/__init__.py
src/ra/config/loader.py
src/ra/config/schema.py
src/ra/data/__init__.py
src/ra/data/bar_types.py
src/ra/engine/__init__.py
src/ra/engine/base.py
src/ra/engine/registry.py
src/ra/detectors/__init__.py
configs/locked_baseline.yaml    (copy of locked params from 01_RUNTIME_CONFIG_SCHEMA)
tests/conftest.py               (shared fixtures — load 5-day CSV as DataFrame)
pyproject.toml                  (or setup.py — project metadata + deps)
requirements.txt                (pandas, duckdb, pyarrow, pyyaml, pytest)
```

**Config loader:**
- Parse YAML config file
- Validate against schema (reject unknown params)
- Resolve per_tf overrides
- Return typed config dict per primitive

**Engine base:**
- `PrimitiveDetector` ABC (as defined in 02_MODULE_MANIFEST)
- `Detection` and `DetectionResult` dataclasses
- Module registry (register by primitive_name + variant_name)

**Verification:**
```bash
pytest tests/ -v  # Config loads, schema validates, base classes instantiate
```

---

### D2: Data Layer (CSV Fallback + TF Aggregation + Session Tagging)

**Files created:**
```
src/ra/data/csv_loader.py       (load 5-day CSV into standard DataFrame)
src/ra/data/tf_aggregator.py    (1m → 5m/15m aggregation)
src/ra/data/session_tagger.py   (tag session/kill_zone/ny_window/forex_day)
src/ra/data/river_adapter.py    (stub — River path for Phase 2)
tests/test_data_layer.py
```

**CSV loader:**
- Read CSV, parse timestamps, convert to NY time
- Produce DataFrame matching Bar contract (03_RIVER_ADAPTER_SPEC)
- Add `is_ghost: False`, `source: "csv_import"` columns

**TF aggregator:**
- Group 1m bars into 5m/15m windows (clock-aligned)
- OHLCV aggregation rules (open=first, high=max, low=min, close=last)
- Ghost handling (all-ghost window → ghost bar)
- Forex day boundary alignment

**Session tagger:**
- Tag every bar with session, kill_zone, ny_window, forex_day
- NY timezone conversion
- Pre-session window tags

**Verification:**
```bash
pytest tests/test_data_layer.py -v
# Verify: 7,177 1m bars loaded
# Verify: 5m aggregation produces correct bar count
# Verify: 15m aggregation produces correct bar count
# Verify: Session tags match known session times
# Verify: Forex day boundaries at 17:00 NY
```

---

### D3: Leaf Detectors (FVG, Swing Points, Displacement)

These three have no upstream dependencies and are the most critical
to get right — everything downstream depends on them.

**Files created:**
```
src/ra/detectors/fvg.py
src/ra/detectors/swing_points.py
src/ra/detectors/displacement.py
tests/test_fvg.py
tests/test_swing_points.py
tests/test_displacement.py
```

**Extraction approach:**

For each detector:
1. Read the v0.5 YAML L1 pseudocode (canonical specification)
2. Read the corresponding function in `preprocess_data_v2.py` (reference implementation)
3. Implement as `PrimitiveDetector` subclass
4. Accept params from config (not hardcoded)
5. Return `DetectionResult` with `Detection` objects
6. Run regression test against baseline fixture

**FVG regression gate:**

| TF | Expected Count | Tolerance |
|----|---------------|-----------|
| 1m | 2,017 | exact |
| 5m | 345 | exact |
| 15m | ~90 | ±2 (verify against actual baseline fixture) |

**Swing Points regression gate:**

| TF | Expected Count | Tolerance |
|----|---------------|-----------|
| 1m | 833 | exact |
| 5m | 163 | exact |
| 15m | ~45 | ±2 (verify against actual baseline fixture) |

**Displacement regression gate:**

| TF | Expected Total | Tolerance |
|----|---------------|-----------|
| 1m | 2,277 (2264 ATR + 13 OVR) | exact |
| 5m | 460 (454 ATR + 6 OVR) | exact |
| 15m | 148 (143 ATR + 5 OVR) | exact |

**Verification:**
```bash
pytest tests/test_fvg.py tests/test_swing_points.py tests/test_displacement.py -v
# All counts match baseline. Zero tolerance on leaf detectors.
```

---

### D4: Supporting Leaf Detectors

**Files created:**
```
src/ra/detectors/session_liquidity.py
src/ra/detectors/asia_range.py
src/ra/detectors/reference_levels.py
src/ra/detectors/equal_hl.py        (STUB — NotImplementedError)
tests/test_session_liquidity.py
tests/test_asia_range.py
tests/test_reference_levels.py
```

**Session Liquidity regression:** Four-gate classification matches v0.5
calibration table (5 days × 3 boxes = 15 classifications).

**Asia Range regression:** 5 days × classification matches v0.5 table.

**Reference Levels regression:** PDH/PDL prices match baseline exactly.

**Verification:**
```bash
pytest tests/test_session_liquidity.py tests/test_asia_range.py tests/test_reference_levels.py -v
```

---

### D5: Composite Detectors (MSS, Order Block)

**Files created:**
```
src/ra/detectors/mss.py
src/ra/detectors/order_block.py
tests/test_mss.py
tests/test_order_block.py
```

**These consume upstream:** MSS needs swing_points + displacement + fvg.
OB needs displacement + mss.

**MSS regression gate:**

| TF | Total | Rev | Cont | FVG % |
|----|-------|-----|------|-------|
| 5m | 44 | 20 | 24 | 80% |
| 15m | 20 | 10 | 10 | 85% |

**OB regression gate:** Verify against baseline fixture (not PROJECT_STATE
numbers, which may predate v0.5 fixes).

**Verification:**
```bash
pytest tests/test_mss.py tests/test_order_block.py -v
```

---

### D6: Multi-Source Composites (HTF Liquidity, Liquidity Sweep, OTE)

**Files created:**
```
src/ra/detectors/htf_liquidity.py
src/ra/detectors/liquidity_sweep.py
src/ra/detectors/ote.py
tests/test_htf_liquidity.py
tests/test_liquidity_sweep.py
tests/test_ote.py
```

**HTF Liquidity regression:** H1: 3 pools (2 untouched, 1 taken). H4: 1 pool.

**Liquidity Sweep regression:** 5m: 14 base, 11 qualified, 15 delayed, 10 cont.

**OTE:** No locked regression. Verify MSS anchor produces valid fib zones.

**Verification:**
```bash
pytest tests/test_htf_liquidity.py tests/test_liquidity_sweep.py tests/test_ote.py -v
```

---

### D7: Cascade Engine + Full Integration Test

**Files created:**
```
src/ra/engine/cascade.py
tests/test_cascade.py
tests/test_regression.py     (full pipeline regression — the master gate)
run.py                       (CLI entry point)
```

**Cascade engine:**
- Parse dependency_graph from config
- Topological sort to determine execution order
- Run detectors in order, passing upstream results to downstream
- When a param changes, re-run affected detector + all downstream
- Cache unchanged upstream results

**CLI:**
```bash
python run.py --config configs/locked_baseline.yaml \
              --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \
              --output results/
```

**Full regression test:**
```python
def test_full_cascade_regression(five_day_dataset, baseline_output):
    """
    Run entire cascade with locked params.
    Compare every detection in every primitive against baseline.
    This is the master gate — if this passes, the extraction is correct.
    """
    engine = CascadeEngine(config=locked_baseline_config)
    results = engine.run_all(five_day_dataset)

    for primitive_name, result in results.items():
        baseline = baseline_output[primitive_name]
        assert_detections_match(result.detections, baseline)
```

**Verification:**
```bash
pytest tests/test_regression.py -v
# MUST PASS before merge. This is the quality gate.
```

---

## MISSION CONTROL EXECUTION STRATEGY

### Session Allocation

| Session | Deliverables | Model | Focus |
|---------|-------------|-------|-------|
| 1 | D1 + D2 | Sonnet | Scaffolding, data layer, tests green |
| 2 | D3 | Sonnet/Opus | Leaf detectors — highest precision required |
| 3 | D4 + D5 | Sonnet | Supporting leaves + composites |
| 4 | D6 + D7 | Sonnet/Opus | Multi-source + cascade + full regression |

### Quality Gates Between Sessions

After each session, verify:
1. All new tests pass (`pytest -v`)
2. No regressions in previously passing tests
3. Code follows existing patterns (dataclass results, config-driven params)
4. No hardcoded params (everything from config YAML)

### Risk Mitigation

**Highest risk:** D3 (leaf detectors). These must be pixel-perfect against
the baseline. If displacement count is off by 1, something is wrong.
Recommend Opus review of D3 before proceeding to D5/D6.

**Second risk:** D5 (MSS). The confirmation window + impulse suppression +
swing consumption logic is the most complex state machine in the system.
The v0.5 YAML has detailed pseudocode — follow it exactly.

**Third risk:** D6 (Liquidity Sweep). Multi-source level pool assembly is
the feature that caused the original 6-hour pain. The curated pool architecture
is now locked in v0.5, but the wiring of multiple upstream sources is complex.

---

## POST-MISSION (Phase 2 Setup)

Once Phase 1 is complete and regression passes:

1. **Branch merge:** `phase1/detection-engine` → `main`
2. **Tag:** `v0.1-detection-engine`
3. **Phase 2 prep:** Evaluation Runner + Comparison Stats
   - Statistical comparison engine
   - Cascade evaluation (full funnel stats)
   - Parameter stability sweep
   - Walk-forward validation
4. **Data expansion:** Acquire 6-12 months EURUSD 1m from Dukascopy,
   activate River adapter (replace CSV fallback)

---

## REFERENCE DOCUMENTS

| Document | Location | Purpose |
|----------|----------|---------|
| v0.5 YAML | `SYNTHETIC_OLYA_METHOD_v0.5.yaml` | Canonical primitive spec |
| Runtime Config | `build_plan/01_RUNTIME_CONFIG_SCHEMA.yaml` | Machine-parseable config |
| Module Manifest | `build_plan/02_MODULE_MANIFEST.md` | Per-module spec + regression |
| River Adapter | `build_plan/03_RIVER_ADAPTER_SPEC.md` | Data layer contract |
| Current Pipeline | `pipeline/preprocess_data_v2.py` | Reference implementation |
| Project State | `PROJECT_STATE.md` | Historical context + counts |
| RA Spec | `research_accelerator_refactor/A8RA_RESEARCH_ACCELERATOR_SPEC.md` | Vision + addenda |
