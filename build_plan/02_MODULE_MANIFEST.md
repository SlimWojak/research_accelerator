# a8ra Research Accelerator — Module Manifest

```yaml
purpose: One entry per detection module. Defines interface, source, and regression expectations.
status: DRAFT
source_spec: SYNTHETIC_OLYA_METHOD_v0.5.yaml
source_pipeline: pipeline/preprocess_data_v2.py (2,816 lines — extraction source)
date: 2026-03-08
```

## Architecture

```
research_accelerator/
  src/
    ra/
      __init__.py
      config/
        __init__.py
        loader.py              # Parse runtime config YAML
        schema.py              # Validate config against schema
      data/
        __init__.py
        river_adapter.py       # Read-only River/parquet consumer
        bar_types.py           # Bar DataFrame contract
        tf_aggregator.py       # 1m → 5m/15m/1H/4H/1D aggregation
        session_tagger.py      # Tag bars with session/kill zone/forex day
      engine/
        __init__.py
        base.py                # PrimitiveDetector ABC + DetectionResult
        cascade.py             # Dependency resolver + cascade runner
        registry.py            # Module registration + variant lookup
      detectors/
        __init__.py
        fvg.py                 # FVG + IFVG + BPR
        swing_points.py        # Swing point detection
        displacement.py        # Displacement (single + cluster + override)
        session_liquidity.py   # Session boxes + four-gate classification
        asia_range.py          # Asia range classification
        mss.py                 # Market Structure Shift (composite)
        order_block.py         # Order Block (composite)
        liquidity_sweep.py     # Liquidity Sweep (multi-source composite)
        htf_liquidity.py       # HTF EQH/EQL structural pools
        ote.py                 # Optimal Trade Entry zones
        reference_levels.py    # PDH/PDL, MO, EQ
        equal_hl.py            # Equal HL (DEFERRED — stub only)
      evaluation/
        __init__.py
        runner.py              # Run configs against datasets
        comparison.py          # Pairwise statistical comparison
        cascade_stats.py       # Full cascade funnel statistics
      output/
        __init__.py
        results.py             # Structured evaluation output
        json_export.py         # JSON for chart consumption
    run.py                     # CLI entry point
  configs/
    locked_baseline.yaml       # Current locked params (regression reference)
    sweep_example.yaml         # Example sweep config for RA exploration
  tests/
    test_regression.py         # Byte-level regression against current pipeline
    test_cascade.py            # Cascade dependency resolution
    conftest.py                # Shared fixtures (5-day dataset)
```

---

## Base Interface

All detectors implement this interface (defined in `engine/base.py`):

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import pandas as pd

@dataclass
class Detection:
    time: datetime
    direction: str              # "bullish" | "bearish" | "neutral"
    type: str                   # primitive-specific subtype
    price: float
    properties: dict            # primitive-specific data
    tags: dict                  # session, kill_zone, forex_day, etc.
    upstream_refs: list[str]    # IDs of consumed upstream detections

@dataclass
class DetectionResult:
    primitive: str              # e.g. "fvg", "displacement"
    variant: str                # e.g. "a8ra_v1"
    timeframe: str              # e.g. "5m"
    detections: list[Detection]
    metadata: dict              # counts, distributions, algo-specific
    params_used: dict           # echo of config for provenance

class PrimitiveDetector(ABC):
    primitive_name: str
    variant_name: str
    version: str

    @abstractmethod
    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Deterministic: same inputs → same outputs."""
        ...

    @abstractmethod
    def required_upstream(self) -> list[str]:
        """Declare upstream primitive dependencies."""
        ...
```

---

## Module Specifications

### 1. FVG (`detectors/fvg.py`)

| Field | Value |
|-------|-------|
| Class | `FVGDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `FVG` (lines ~105-225) |
| Pipeline Source | `preprocess_data_v2.py` — `detect_fvg()` function |
| Upstream | None (leaf node) |
| Downstream | IFVG, BPR, MSS (fvg_created tag) |
| Status | LOCKED (L1 + L1.5) |

**Config consumed:**
- `floor_threshold_pips`

**Detection logic (from v0.5 L1):**
- Bullish: `bars[i].low > bars[i-2].high`
- Bearish: `bars[i].high < bars[i-2].low`
- Gap size in pips, filtered by floor
- Anchor time at candle A (bars[i-2])

**State machine:** ACTIVE → CE_TOUCHED → BOUNDARY_CLOSED → IFVG
- Tracked per detection across subsequent bars

**Tags emitted:** session, displacement_present, bpr_zone, swing_proximity

**Also implements:** IFVG (state transition on closed FVG) + BPR (geometric overlap)

**Regression expectations (5-day dataset, locked params):**

| TF | FVG Count | Source |
|----|-----------|--------|
| 1m | 2,017 | PROJECT_STATE.md |
| 5m | 345 | PROJECT_STATE.md / v0.5 |
| 15m | ~90 | PROJECT_STATE.md |

---

### 2. Swing Points (`detectors/swing_points.py`)

| Field | Value |
|-------|-------|
| Class | `SwingPointDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `SWING_POINTS` (lines ~230-390) |
| Pipeline Source | `preprocess_data_v2.py` — `detect_swings()` function |
| Upstream | None (leaf node) |
| Downstream | MSS, HTF Liquidity, Liquidity Sweep (promoted), Equal HL |
| Status | LOCKED (L1 + L1.5) |

**Config consumed:**
- `N` (per TF: 1m=5, 5m=3, 15m=2)
- `height_filter_pips` (per TF: 1m=0.5, 5m=3.0, 15m=3.0)
- `strength_cap` (20)
- `strength_as_gate` (false — tag only)

**Detection logic (from v0.5 L1):**
- N-bar pivot: `>= left, > right` (equality fix from v0.4)
- Height: max excursion from surrounding bars
- Strength: bars held beyond N, capped at 20

**Tags emitted:** session, is_equal_high, is_equal_low, strength_grade (dim/mid/vivid)

**Regression expectations:**

| TF | Swing Count | Source |
|----|-------------|--------|
| 1m | 833 | PROJECT_STATE.md |
| 5m | 163 | PROJECT_STATE.md |
| 15m | ~45 | PROJECT_STATE.md |

---

### 3. Displacement (`detectors/displacement.py`)

| Field | Value |
|-------|-------|
| Class | `DisplacementDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `DISPLACEMENT` (lines ~600-1100) |
| Pipeline Source | `preprocess_data_v2.py` — `detect_displacement()` function |
| Upstream | None (leaf node) |
| Downstream | MSS, Order Block |
| Status | LOCKED (LTF), PROPOSED (HTF) |

**Config consumed:**
- `atr_period`, `combination_mode`, `ltf.*`, `htf.*`
- `decisive_override.*`, `cluster.*`
- `quality_grades`

**Detection logic (from v0.5 L1):**
- Single bar: ATR ratio + body ratio + close gate (AND mode)
- Cluster 2: 4 filters (net_eff, overlap, progression, close_strength)
- Decisive override: body >= 0.75, close <= 0.10, pip floor
- Evaluation order: cluster_2 → single_atr → single_override

**Tags emitted:** session, created_fvg, ny_window, atr_ratio, body_pct,
displacement_type, close_location_pass, quality_grade, qualification_path

**Regression expectations:**

| TF | ATR Count | Override Count | Total | Source |
|----|-----------|----------------|-------|--------|
| 1m | 2,264 | 13 | 2,277 | v0.5 calibration_data |
| 5m | 454 | 6 | 460 | v0.5 calibration_data |
| 15m | 143 | 5 | 148 | v0.5 calibration_data |

---

### 4. Session Liquidity (`detectors/session_liquidity.py`)

| Field | Value |
|-------|-------|
| Class | `SessionLiquidityDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `SESSION_LIQUIDITY` (lines ~395-600) |
| Pipeline Source | `preprocess_data_v2.py` — session box logic |
| Upstream | None (leaf node) |
| Downstream | Liquidity Sweep (level source) |
| Status | PROPOSED |

**Config consumed:**
- `four_gate_model.*` (efficiency, mid_cross, balance)
- `box_objects.*` (asia, pre_london, pre_ny windows + range caps)

**Detection logic (from v0.5 L1):**
- Four-gate classifier: range + efficiency + mid_cross + balance
- CONSOLIDATION_BOX if all 4 pass, TREND_OR_EXPANSION if any fails
- Interaction tracking per level (traded_above/below, closed_above/below)

**Regression expectations (from v0.5 calibration_data):**

| Day | Asia | PreLondon | PreNY |
|-----|------|-----------|-------|
| Jan 8 | CONSOL (22.4p) | TREND_UP (14.7p) | TREND_UP (16.4p) |
| Jan 9 | CONSOL (17.0p) | TREND_DN (8.2p) | TREND_DN (19.4p) |
| Jan 10 | CONSOL (10.3p) | TREND_DN (10.4p) | CONSOL (13.7p) |
| Jan 11 | CONSOL (11.7p) | TREND_UP (14.0p) | TREND_UP (23.8p) |
| Jan 12 | CONSOL (12.7p) | CONSOL (7.2p) | TREND_DN (17.5p) |

---

### 5. Asia Range (`detectors/asia_range.py`)

| Field | Value |
|-------|-------|
| Class | `AsiaRangeDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `ASIA_RANGE` |
| Pipeline Source | `preprocess_data_v2.py` — Asia range logic |
| Upstream | None (leaf node) |
| Downstream | Context tag for other primitives |
| Status | PROPOSED (classification thresholds) |

**Config consumed:**
- `classification` (tight/mid/wide boundaries)
- `max_cap_pips`

**Regression expectations (from v0.5 calibration_data):**

| Day | Range Pips | Classification |
|-----|-----------|---------------|
| Mon (Jan 8) | 20.7 | WIDE |
| Tue (Jan 9) | 17.7 | MID |
| Wed (Jan 10) | 10.3 | TIGHT |
| Thu (Jan 11) | 12.0 | MID |
| Fri (Jan 12) | 22.2 | WIDE |

---

### 6. MSS (`detectors/mss.py`)

| Field | Value |
|-------|-------|
| Class | `MSSDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `MSS` |
| Pipeline Source | `preprocess_data_v2.py` — `detect_mss()` function |
| Upstream | `swing_points`, `displacement`, `fvg` |
| Downstream | Order Block, OTE |
| Status | LOCKED (LTF) |

**Config consumed:**
- `ltf.*` / `htf.*` (confirmation window, suppression rules)
- `fvg_tag_only`, `break_classification`, `swing_consumption`

**Detection logic (from v0.5 L1):**
- Close beyond prior swing WITH displacement on break bar (or within confirmation window)
- Confirmation window: 3 bars (LTF), 1 bar (HTF)
- Impulse suppression: pullback/opposite_disp/new_day resets
- Break classified REVERSAL or CONTINUATION (internal tag, not displayed)

**Regression expectations (from v0.5 calibration_data, post-fixes):**

| TF | Total | Reversal | Continuation | FVG Tagged | FVG % |
|----|-------|----------|--------------|------------|-------|
| 1m | 179 | 88 | 91 | 129 | 72% |
| 5m | 44 | 20 | 24 | 35 | 80% |
| 15m | 20 | 10 | 10 | 17 | 85% |

---

### 7. Order Block (`detectors/order_block.py`)

| Field | Value |
|-------|-------|
| Class | `OrderBlockDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `ORDER_BLOCK` |
| Pipeline Source | `preprocess_data_v2.py` — `detect_ob()` function |
| Upstream | `displacement`, `mss` |
| Downstream | None (terminal for detection; OTE uses MSS, not OB directly) |
| Status | LOCKED |

**Config consumed:**
- `trigger`, `zone_type`, `thin_candle_filter`, `fallback_scan`, `expiration_bars`

**Detection logic (from v0.5 L1):**
- Last opposing candle before displacement that caused MSS
- Body-only execution zone, full OHLC for invalidation
- Thin candle filter (body_pct >= 0.10)
- Conditional fallback scan (3 bars back)
- State machine: ACTIVE → MITIGATED/INVALIDATED/EXPIRED

**Regression expectations:**

| TF | OB Count | Source |
|----|----------|--------|
| 1m | 601 | PROJECT_STATE.md (at default thresholds) |
| 5m | 106 | PROJECT_STATE.md |
| 15m | ~30 | PROJECT_STATE.md |

**NOTE:** These counts are from the PROJECT_STATE.md default thresholds, which may
predate some of the v0.5 fixes (confirmation window, suppression). The regression
test should verify against the CURRENT pipeline output, not these historical numbers.
Run the current pipeline once, capture output, that becomes the regression fixture.

---

### 8. Liquidity Sweep (`detectors/liquidity_sweep.py`)

| Field | Value |
|-------|-------|
| Class | `LiquiditySweepDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `LIQUIDITY_SWEEP` |
| Pipeline Source | `preprocess_data_v2.py` — sweep detection logic |
| Upstream | `session_liquidity`, `reference_levels`, `htf_liquidity`, `swing_points` |
| Downstream | None (terminal) |
| Status | LOCKED |

**Config consumed:**
- `return_window_bars`, `rejection_wick_pct`, `min_breach_pips`, `min_reclaim_pips`
- `max_sweep_size_atr_mult`, `level_sources.*`, `qualified_sweep.*`, `delayed_sweep.*`

**Detection logic (from v0.5 L1):**
- Curated pool: PDH/PDL, Asia H/L, London H/L, LTF box, HTF EQH/EQL, PWH/PWL, promoted swings
- Breach + close back + rejection wick >= 40%
- Continuation classification at 1.5x ATR
- Qualified sweep: displacement before (10 bars) or after (5 bars)
- Delayed sweep: bar+1 reclaim

**Regression expectations (from v0.5 calibration_data, curated pool rebuild):**

| TF | Base (1-bar) | Qualified | Delayed | Continuation |
|----|-------------|-----------|---------|--------------|
| 5m | 14 | 11 | 15 | 10 |
| 15m | 11 | 10 | 15 | 14 |

---

### 9. HTF Liquidity (`detectors/htf_liquidity.py`)

| Field | Value |
|-------|-------|
| Class | `HTFLiquidityDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `HTF_LIQUIDITY_MODEL` |
| Upstream | `swing_points` (fractal left=2, right=2) |
| Status | LOCKED |

**Regression expectations (from v0.5 calibration_data):**

| TF | Swings | Pools | Untouched | Taken |
|----|--------|-------|-----------|-------|
| H1 | 34 | 3 | 2 | 1 |
| H4 | 9 | 1 | 1 | 0 |

---

### 10. OTE (`detectors/ote.py`)

| Field | Value |
|-------|-------|
| Class | `OTEDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `OTE` |
| Upstream | `mss` |
| Status | PROPOSED |

**Config consumed:**
- `fib_levels` (0.618, 0.705, 0.79)
- `anchor_rule`, `kill_zone_gate`

**Regression:** No locked regression numbers yet. Validate by visual inspection
against MSS anchor points on 5-day dataset.

---

### 11. Reference Levels (`detectors/reference_levels.py`)

| Field | Value |
|-------|-------|
| Class | `ReferenceLevelDetector` |
| Variant | `a8ra_v1` |
| v0.5 Section | `REFERENCE_LEVELS` |
| Upstream | None |
| Status | LOCKED |

**Deterministic computation:** PDH/PDL, Midnight Open, Equilibrium.
Regression = exact price match on 5-day dataset.

---

### 12. Equal HL (`detectors/equal_hl.py`) — STUB

| Field | Value |
|-------|-------|
| Status | DEFERRED |

Stub module that raises `NotImplementedError`. Included in registry so the
dependency graph accounts for it. Build when EQL/EQH detection is finalized.

---

## Regression Strategy

### Ground Truth Capture

Before ANY module extraction begins:

1. Run current `preprocess_data_v2.py` on the 5-day dataset
2. Capture ALL JSON output files from `site/` directory
3. Store as `tests/fixtures/baseline_output/`
4. This is the regression fixture — the RA must reproduce it exactly at locked params

### Per-Module Regression

Each detector module gets a test:

```python
def test_fvg_regression(five_day_bars_5m, baseline_fvg_5m):
    detector = FVGDetector()
    result = detector.detect(five_day_bars_5m, locked_params)
    assert len(result.detections) == len(baseline_fvg_5m)
    for ra_det, baseline_det in zip(result.detections, baseline_fvg_5m):
        assert ra_det.time == baseline_det["time"]
        assert ra_det.price == pytest.approx(baseline_det["price"], abs=1e-6)
```

### Cascade Regression

Full cascade test: run ALL detectors with locked params, verify terminal
counts match current pipeline output. This catches wiring bugs between modules.

### Regression Gate Rule

**No merge to main without regression PASS.** This is the quality gate
that protects locked calibration decisions.
