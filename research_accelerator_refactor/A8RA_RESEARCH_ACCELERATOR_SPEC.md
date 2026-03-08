# a8ra RESEARCH ACCELERATOR
## Architecture Specification — Calibration as Core Capability

**Version:** 0.1 PROPOSAL  
**Date:** 2026-03-08  
**Author:** CTO (Craig) + Claude (Architecture Synthesis)  
**Status:** PROPOSAL — For review by CTO Claude (Opus) and Olya's Advisor  
**Classification:** a8ra Core Infrastructure  

---

## 1. EXECUTIVE SUMMARY

### The Problem

The current calibration tool was designed as a disposable visual aid for one-at-a-time parameter locking. It served its purpose — FVG, displacement, MSS, OB, and sweep architecture are now locked — but the tool has hit a hard ceiling.

**Concrete failure mode:** The Liquidity Sweep session on 2026-03-07 consumed ~6 hours of iteration across four agents (Claude, Opus, Perplexity, Olya's Advisor). The root cause was not conceptual — the detection architecture was sound within the first hour. The remaining five hours were spent in a code-edit → pipeline-run → visual-check loop trying different level pool configurations. Each hypothesis required Opus to rewrite pool logic in Python, re-run the pipeline, and regenerate chart data. The tool could not separate "which levels should we monitor?" (a configuration question) from "how do we detect a sweep?" (an algorithm question).

This is not an isolated incident. Every calibration session has the same structural bottleneck: testing a hypothesis requires code changes.

### The Proposal

Elevate calibration from a disposable tool to a **core a8ra capability** — a Research Accelerator that treats algorithm variants and parameter configurations as data, not code.

### Why This Is Strategic

The algo design underpinning a8ra's detection layer is the system's primary moat. The moat is not any particular set of locked parameters — it is the **capacity to rigorously derive, validate, and evolve parameters** for any strategy Olya conceives, on any instrument, in any market regime. A Research Accelerator makes that capacity institutional rather than ad-hoc.

**Implications:**
- New strategy onboarding becomes systematic (weeks → days)
- Parameter confidence becomes evidence-based (not "looked good on Tuesday")
- External algo benchmarking becomes routine (not a research project)
- Regime drift becomes detectable before it costs capital
- The entire calibration history becomes institutional knowledge with provenance

---

## 2. DESIGN PRINCIPLES

These are non-negotiable architectural constraints. They carry forward from the existing a8ra architecture and extend it.

### P1: L1 / L1.5 / L2 Separation (INHERITED — LOCKED)
- **L1** = Detection algorithm. Deterministic. Geometric/mathematical.
- **L1.5** = Parameters. Configurable per pair/regime/timeframe.
- **L2** = Strategy interpretation. Lives in Olya's head.
- L2 never rewrites L1. L1.5 is the tuning surface.
- The Research Accelerator operates exclusively on L1 and L1.5. L2 is out of scope.

### P2: Configuration Over Code
- No code changes to test a parameter hypothesis.
- No code changes to swap an algorithm variant.
- No code changes to add a new dataset or regime slice.
- If you're editing Python to explore, the system has failed.

### P3: Comparative by Default
- Every evaluation produces comparison output: this config vs that config, this algo vs that algo, this regime vs that regime.
- Single-config evaluation is a degenerate case of comparison (config A vs nothing).
- Olya never sees a single option in isolation — she sees candidates ranked by evidence.

### P4: External Algos Are First-Class Citizens
- An indicator ported from TradingView has the same interface as a native a8ra primitive.
- External algos can be benchmarked against a8ra algos on identical data.
- The system does not privilege its own implementations — it privileges the best-performing ones.

### P5: Olya Is the Final Gate, Not the Discovery Engine
- The system surfaces candidates through statistical evaluation.
- Olya validates the top candidates visually.
- This inverts the current model (Olya discovers through visual review, system records her decision).

### P6: Provenance Is Mandatory
- Every locked parameter records: what alternatives were tested, what data it was tested on, what the comparison statistics were, when Olya confirmed it, and what the regime conditions were.
- This is not documentation overhead — it is the institutional knowledge that makes the moat defensible.

---

## 3. ARCHITECTURE

### 3.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     RESEARCH ACCELERATOR                            │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  DATA LAYER  │──▶│ DETECTION ENGINE  │──▶│ EVALUATION RUNNER  │  │
│  │              │   │                  │   │                    │  │
│  │ Multi-pair   │   │ Native a8ra      │   │ Statistical        │  │
│  │ Multi-regime │   │ algos            │   │ comparison         │  │
│  │ Regime-tagged│   │ +                │   │ Regime-sliced      │  │
│  │ Session-aware│   │ External/ported  │   │ Cascade-aware      │  │
│  │              │   │ algos            │   │                    │  │
│  └──────────────┘   │ +                │   └────────┬───────────┘  │
│                     │ Parameter configs │            │              │
│                     └──────────────────┘            │              │
│                                                      ▼              │
│                                          ┌────────────────────────┐ │
│                                          │  COMPARISON INTERFACE  │ │
│                                          │                        │ │
│                                          │  Full-stack chart      │ │
│                                          │  Side-by-side configs  │ │
│                                          │  Stats dashboard       │ │
│                                          │  Lock + provenance     │ │
│                                          └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component 1: Data Layer

**Purpose:** Ingest, store, and serve OHLCV data across multiple instruments, timeframes, and date ranges, with regime and session tagging.

**Data Sources:**
- Primary: Dukascopy 1m tick data (already used for current dataset)
- Expansion: 6-12 months minimum per instrument for statistical validity
- Initial instruments: EURUSD (primary), expand post-calibration

**Storage Format:**
```yaml
dataset:
  instrument: EURUSD
  source: dukascopy
  resolution: 1m  # base resolution — higher TFs aggregated on demand
  range: 2024-01-01 to 2024-12-31
  bars: ~370,000
  
  # Regime tags (computed or manual)
  regime_tags:
    - { start: "2024-01-02", end: "2024-01-19", regime: "ranging", vol: "low" }
    - { start: "2024-01-22", end: "2024-02-09", regime: "trending_up", vol: "medium" }
    - { start: "2024-03-06", end: "2024-03-08", regime: "nfp_week", vol: "high" }
    # ... auto-generated + manually curated
  
  # Session boundaries (computed from timezone rules)
  sessions:
    asia: { start: "19:00 NY", end: "00:00 NY" }
    lokz: { start: "02:00 NY", end: "05:00 NY" }
    nyokz: { start: "07:00 NY", end: "10:00 NY" }
    forex_day: "17:00 NY"
```

**Regime Tagging Approach:**
- Phase 1 (automated): ATR-based volatility classification, ADX-based trend/range classification, session-based slicing
- Phase 2 (curated): Manual tags for key event types — NFP, FOMC, CPI, low-liquidity holiday periods
- Regime tags are metadata on the dataset, not part of detection logic
- Evaluation runner slices by regime for per-regime statistics

**TF Aggregation:**
- 1m data stored as base resolution
- 5m, 15m, 1H, 4H, Daily aggregated on demand (same logic as current pipeline)
- Native TF detection principle preserved — 5m primitives run on 5m bars

**Key Design Decision:** Data layer is a local file store (Parquet or HDF5), not a database. Keeps infrastructure simple. A year of 1m EURUSD is ~50MB in Parquet — trivially fits in memory.

### 3.3 Component 2: Detection Engine

**Purpose:** Run any combination of primitive detection algorithms with any parameter configuration, producing standardised output.

#### 3.3.1 Primitive Module Interface

Every primitive — native a8ra or external — implements the same interface:

```python
class PrimitiveDetector:
    """Base interface for all detection modules."""
    
    primitive_name: str          # e.g. "displacement"
    variant_name: str            # e.g. "a8ra_v1", "tradingfinder_port", "luxalgo_port"
    version: str                 # semver
    source: str                  # "native" | "ported_pinescript" | "ported_academic" | "ported_mt5"
    source_reference: str        # URL or citation
    
    def detect(
        self,
        bars: DataFrame,          # OHLCV bars for a single TF
        params: dict,             # L1.5 parameters
        upstream: dict = None,    # Outputs from upstream primitives (for composites)
        context: dict = None      # Session boundaries, reference levels, etc.
    ) -> DetectionResult:
        """
        Returns standardised detection output.
        Must be deterministic: same inputs → same outputs.
        """
        ...

class DetectionResult:
    detections: list[Detection]   # Individual detection events
    metadata: dict                # Algo-specific metadata (counts, distributions, etc.)
    params_used: dict             # Echo of params for provenance
    
class Detection:
    time: datetime                # Detection timestamp
    type: str                     # Primitive-specific type (e.g., "bullish", "bearish")
    price: float                  # Reference price
    properties: dict              # Primitive-specific properties
    tags: dict                    # Context tags (session, regime, quality markers)
    upstream_refs: list[str]      # IDs of upstream detections consumed (for composites)
```

#### 3.3.2 Native a8ra Primitives (Migrated from Current Pipeline)

Each existing primitive in `preprocess_data_v2.py` becomes a module:

| Module | Current Status | Migration Complexity |
|--------|---------------|---------------------|
| `SwingPointDetector` | Algorithm locked, L1.5 locked per TF | Low — extract function, parameterise N and height thresholds |
| `EqualHLDetector` | Algorithm defined, L1.5 proposed | Low — extract, parameterise tolerance + min_separation |
| `FVGDetector` | Fully locked (L1 + L1.5) | Low — extract, params already defined |
| `DisplacementDetector` | L1 locked, L1.5 locked | Low — extract, parameterise ATR mult, body ratio, combine mode |
| `MSSDetector` | Composite — consumes swings + displacement | Medium — wire upstream consumption |
| `OrderBlockDetector` | Fully locked | Medium — consumes displacement + MSS |
| `LiquiditySweepDetector` | Architecture locked, sources pending | Medium — separate detection logic from level pool config |
| `AsiaRangeDetector` | L1 locked, L1.5 proposed | Low |
| `OTEDetector` | Fib levels locked, anchor rule proposed | Low |
| `IFVGDetector` | L1 locked, inherits FVG | Low |
| `BPRDetector` | L1 locked | Low |

**Cascade Dependency Graph (enforced by engine):**
```
SwingPoints ──┬──▶ MSS ──┬──▶ OrderBlock
              │          │
Displacement ─┘          └──▶ OTE
              
FVG ──────────────▶ MSS (tag: fvg_created)
              
SwingPoints ──┬──▶ EqualHL ──▶ LiquiditySweep (level source)
              │
              └──▶ LiquiditySweep (level source: swing)

AsiaRange ────────▶ LiquiditySweep (level source: session H/L)
```

The engine resolves this graph automatically. When you change a displacement parameter, MSS and OB re-run. No manual cascade management.

#### 3.3.3 External Algo Integration

**Ingestion workflow:**
```
PineScript / MT5 / Academic Paper
        │
        ▼
   AI-Assisted Transpilation (Claude/Opus)
        │
        ▼
   Python module implementing PrimitiveDetector interface
        │
        ▼
   Validation: run on reference dataset, compare output format
        │
        ▼
   Registered as variant: displacement/tradingfinder_v1
```

**Initial Target Externals (Phase 1):**

| Primitive | External Source | Reference | Priority |
|-----------|---------------|-----------|----------|
| Displacement | TradingFinder ICT indicator | TV open source | HIGH — most variants available |
| Swing Points | LuxAlgo Smart Money Concepts | TV open source | HIGH — alternative N-bar logic |
| FVG | Multiple TV implementations | Research Pack refs | MEDIUM — already locked, useful for validation |
| MSS / CHoCH | GrandAlgo implementation | TV open source | HIGH — tests composite logic |
| Order Block | TradingFinder OB detector | TV open source | MEDIUM |
| OTE | GrandAlgo fib implementation | TV open source | LOW — fib levels are standard |

**PineScript Transpilation Guide:**

PineScript v5 maps to Python/pandas cleanly for most ICT indicators:

| PineScript | Python/Pandas Equivalent |
|------------|-------------------------|
| `ta.atr(14)` | `bars['tr'].rolling(14).mean()` (where tr = true range) |
| `ta.sma(close, 20)` | `bars['close'].rolling(20).mean()` |
| `ta.highest(high, N)` | `bars['high'].rolling(N).max()` |
| `ta.crossover(a, b)` | `(a > b) & (a.shift(1) <= b.shift(1))` |
| `close[1]` | `bars['close'].shift(1)` |
| `bar_index` | `bars.index` (integer position) |
| `ta.valuewhen(cond, src, N)` | Custom: track Nth occurrence where cond is True |
| `request.security(sym, tf, expr)` | Use aggregated TF bars from data layer |

**Transpilation is not a blocker.** Most ICT PineScript indicators are 50-200 lines and use a small subset of Pine's built-ins. AI-assisted transpilation produces working Python in 15-30 minutes per indicator. A formal transpiler is Phase 2.

#### 3.3.4 Parameter Configuration Schema

Configurations are YAML, not code:

```yaml
# Example: two displacement configs to compare
configs:
  - name: "current_locked"
    description: "Locked 2026-03-06 — ATR 1.5x AND body 0.60"
    primitives:
      displacement:
        variant: "a8ra_v1"
        params:
          atr_multiplier: 1.5
          body_ratio: 0.60
          combine_mode: "AND"
          atr_period: 14
  
  - name: "candidate_relaxed"
    description: "Testing OR mode with higher ATR threshold"
    primitives:
      displacement:
        variant: "a8ra_v1"
        params:
          atr_multiplier: 2.0
          body_ratio: 0.60
          combine_mode: "OR"
          atr_period: 14

  - name: "tradingfinder_benchmark"
    description: "TradingFinder port — external benchmark"
    primitives:
      displacement:
        variant: "tradingfinder_v1"
        params:
          sensitivity: "medium"  # TradingFinder's own param schema
```

**Key principle:** Each config can mix native and external variants. You could run a8ra swing points feeding into TradingFinder's MSS detection to isolate which component explains a performance difference.

### 3.4 Component 3: Evaluation Runner

**Purpose:** Run detection configs across datasets and produce statistical comparison output.

#### 3.4.1 Evaluation Output Schema

```yaml
evaluation:
  run_id: "eval_2026-03-09_001"
  dataset: "EURUSD_2024_full"
  configs_compared: ["current_locked", "candidate_relaxed", "tradingfinder_benchmark"]
  
  per_config:
    current_locked:
      displacement:
        total_detections: 1847
        per_day_mean: 7.4
        per_day_std: 2.1
        by_session:
          asia: { count: 312, pct: 16.9 }
          lokz: { count: 441, pct: 23.9 }
          nyokz: { count: 623, pct: 33.7 }
          other: { count: 471, pct: 25.5 }
        by_regime:
          trending: { per_day: 9.2, cascade_to_mss: 0.78 }
          ranging: { per_day: 5.1, cascade_to_mss: 0.62 }
          high_vol: { per_day: 12.4, cascade_to_mss: 0.71 }
        cascade_rates:
          displacement_to_mss: 0.72
          mss_to_ob: 0.85
          mss_with_fvg: 0.81
  
  pairwise_comparison:
    current_locked_vs_candidate_relaxed:
      agreement_rate: 0.68       # % of detections both configs fire
      only_in_current: 142       # current fires, candidate doesn't
      only_in_candidate: 387     # candidate fires, current doesn't
      regime_divergence:         # where do they disagree most?
        trending: { agreement: 0.74 }
        ranging: { agreement: 0.55 }  # ← biggest divergence
```

#### 3.4.2 Cascade Evaluation (Critical Differentiator)

The current tool evaluates primitives in isolation. The Research Accelerator evaluates the **full cascade**:

```
Displacement config A → MSS count → OB count → Setups in kill zone → Olya's universe
```

**This answers the real question:** "If I change displacement, how many *tradeable setups* does Olya see per week?" — not "how many displacements fire?"

The cascade evaluation runs the full dependency graph and reports at each level:

```yaml
cascade_report:
  config: "current_locked"
  dataset: "EURUSD_2024_Q1"
  
  L1_primitives:
    swing_points_5m: { total: 4200, structural: 890 }  # strength >= 10
    displacement_5m: { total: 1847 }
    fvg_5m: { total: 3102 }
  
  L1_composites:
    mss_5m: { total: 1330, fvg_tagged: 1077, reversal: 612, continuation: 718 }
    order_blocks_5m: { total: 1130, active_avg_lifespan: 4.2_bars }
    liquidity_sweeps_5m: { total: 234, by_source: { session_hl: 89, equal_hl: 67, swing: 78 } }
  
  L1_convergence:
    mss_with_ob_in_ote: { total: 312, per_day: 5.0 }
    above_in_kill_zone: { total: 187, per_day: 3.0 }  # ← Olya's approximate universe
```

### 3.5 Component 4: Comparison Interface

**Purpose:** Visual layer for Olya to validate candidates surfaced by the evaluation runner.

#### 3.5.1 Chart Layer

- Full-stack primitive overlay on a single chart (toggleable per primitive)
- Multi-config rendering: Config A markers in colour set 1, Config B in colour set 2
- TF switching: same chart, switch between 1m/5m/15m/1H
- Date range navigation: jump to specific regime slices, specific sessions, specific dates
- Carries forward the rendering approach from current tool (Lightweight Charts + custom overlays)

#### 3.5.2 Configuration Panel

- Per-primitive parameter controls (sliders, dropdowns, toggles)
- Variant selector per primitive (a8ra_v1, tradingfinder_v1, etc.)
- Preset configs: "current locked", "candidate A", "candidate B"
- **Instant re-computation** — change a param, chart updates. No pipeline run.

#### 3.5.3 Statistics Dashboard

- Side-by-side stats for compared configs
- Per-regime breakdown
- Cascade conversion funnel
- Divergence highlighter: "click to jump to a detection where configs disagree"

#### 3.5.4 Lock + Provenance Panel

When Olya is ready to lock:
```yaml
lock_record:
  primitive: displacement
  variant: a8ra_v1
  params_locked: { atr_multiplier: 1.5, body_ratio: 0.60, combine_mode: AND }
  locked_by: Olya
  locked_date: "2026-03-10T14:30:00"
  dataset_evaluated: "EURUSD_2024_Q1"
  configs_compared: ["current", "candidate_relaxed", "tradingfinder_benchmark"]
  comparison_summary:
    current_vs_relaxed: "Current has 32% fewer detections but 16% higher MSS cascade rate"
    current_vs_tradingfinder: "89% agreement rate — validates approach"
  olya_notes: "Current feels right — relaxed catches noise in Asia, TF benchmark confirms we're in line"
```

---

## 4. LIQUIDITY SWEEP: CASE STUDY OF NEW SYSTEM

To make this concrete, here's how the 6-hour sweep session would have gone with the Research Accelerator:

**Step 1 (5 min):** Open tool. Load 15m chart. Sweep detection is active with current architecture (breach + reclaim logic already locked).

**Step 2 (10 min):** Open level source configuration panel. Checkboxes for each pool type:
- ☑ Previous session H/L
- ☑ Asia session H/L
- ☑ Equal highs/lows
- ☐ Raw previous swings
- ☐ Pre-London box H/L
- ☐ Promoted HTF swings

Toggle sources on/off. Chart updates instantly. Count panel shows: "Config A (all sources): 8.2 sweeps/day. Config B (session + equal only): 2.1 sweeps/day."

**Step 3 (15 min):** Olya reviews Config B on the chart. "That one at 14:30 on Jan 9 — that's not a real sweep, it's noise." Click the detection, see which level source generated it. Toggle that source off or adjust the quality gate. Chart updates.

**Step 4 (10 min):** Load an external sweep detection indicator (ported from TV) as a benchmark. Orange markers appear alongside blue. "The external catches the same 3 key sweeps per day but misses the one at 09:15 that Olya wants." Confirms a8ra's approach is capturing the right events.

**Step 5 (5 min):** Run evaluation across full Q1 dataset. Stats show: 1.8 base sweeps/day, stable across regimes, 70% occur in kill zones. Olya locks.

**Total: ~45 minutes. No code changes. Full provenance recorded.**

---

## 5. BUILD PLAN

### Phase 1: Detection Engine + Data Layer (2-3 days)

**Deliverables:**
- Parameterised primitive modules migrated from current pipeline
- Cascade dependency resolver (auto-runs downstream when upstream changes)
- Dataset loader supporting multi-month 1m data with TF aggregation
- YAML-based configuration loading
- CLI runner: `python run.py --config config_a.yaml --dataset eurusd_2024 --output results/`

**Data acquisition:** Download 6-12 months EURUSD 1m from Dukascopy (same source as current dataset). Tag with automated regime classification.

**Validation:** Run locked configs on current 5-day dataset, verify output matches existing tool exactly. This is the regression gate.

### Phase 2: Evaluation Runner + Comparison Stats (1-2 days)

**Deliverables:**
- Statistical comparison engine: per-config stats, pairwise comparison, regime-sliced
- Cascade evaluation: full dependency graph stats
- Output format: YAML + CSV for dashboard consumption
- Divergence indexing: list of timestamps where configs disagree (for visual review)

### Phase 3: Comparison Interface (2-3 days)

**Deliverables:**
- Full-stack chart with toggleable primitive layers
- Multi-config overlay (colour-coded by config)
- Parameter control panel (real-time re-computation)
- Statistics dashboard (side-by-side)
- Lock + provenance recording

**Tech stack:** Python backend (FastAPI) + existing Lightweight Charts frontend, connected via WebSocket or REST for instant re-computation feedback.

### Phase 4: External Algo Integration (Ongoing)

**Deliverables:**
- First 3 external indicators ported (displacement, swings, MSS)
- Benchmark comparison against a8ra locked configs
- Transpilation guide + template for future ports

**Ongoing:** Each time Perplexity or research surfaces a promising external implementation, it gets ported and benchmarked. Library grows over time.

### Phase 5: Production Monitoring (Future)

**Deliverables:**
- Live data ingestion (from IBKR or broker feed)
- Regime drift detection: alert when detection rates deviate from calibration baseline
- Parameter re-evaluation triggers: "displacement cascade rate dropped 30% this month — review recommended"

---

## 6. WHAT CARRIES FORWARD

| Existing Asset | Role in Research Accelerator |
|---|---|
| `SYNTHETIC_OLYA_METHOD_v0.5.yaml` | Becomes the **runtime configuration schema** — engine reads it directly |
| `preprocess_data_v2.py` primitive algos | Refactored into **detection modules** with PrimitiveDetector interface |
| `calibration_data_export.yaml` | Becomes the **reference dataset** for regression testing |
| Chart rendering code (Lightweight Charts + overlays) | Foundation for **comparison interface** |
| L1/L1.5/L2 architecture | **Core organising principle** — elevated from documentation to enforcement |
| Cascade dependency map (from facilitator briefs) | Encoded in **engine dependency resolver** |
| Research Pack (ICT_PRIMITIVES_RESEARCH_PACK.md) | Becomes the **external algo sourcing reference** |
| All locked parameter decisions + provenance | **Baseline configs** that the new system validates or improves |

**Nothing is thrown away.** The current system's intellectual output becomes the seed for an institutional-grade capability.

---

## 7. WHAT THIS MAKES POSSIBLE (LONG-TERM)

### New Strategy Onboarding
Olya develops a new setup type or wants to trade a new instrument. Instead of months of manual calibration: load the data, define the primitive stack, run the evaluation, port any relevant external benchmarks, Olya validates the top candidates. Days, not months.

### Multi-Instrument Expansion
Point the engine at GBPUSD, USDJPY, NQ, ES. Same primitives, different L1.5 parameters per instrument. The Research Accelerator finds the right parameters for each. Olya validates.

### Continuous Validation
Parameters locked in January 2024's regime may not be optimal in August 2024's regime. The system continuously evaluates locked configs against incoming data and flags drift before it becomes a P&L problem.

### Algo Evolution
When ICT methodology evolves, when academic research surfaces better detection approaches, when Olya's own understanding deepens — the Research Accelerator can absorb new algo variants and rigorously compare them against the current baseline. The system improves over time, with evidence.

---

## 8. DECISION REQUESTED

### For CTO Claude (Opus):
- Review the module interface design (§3.3.1). Does the PrimitiveDetector interface support all current primitive patterns, including composites with upstream consumption?
- Review the cascade dependency graph (§3.3.2). Confirm the engine can resolve this automatically from YAML config.
- Flag any migration risks in extracting current pipeline code into modules.

### For Olya's Advisor:
- Review the Olya experience described in §4 (Liquidity Sweep case study) and §3.5 (Comparison Interface). Does this match how Olya would want to work?
- Review the provenance model (§3.5.4). Is this sufficient to build confidence in locked parameters?
- Input on which external algo sources would be highest value to port first.

### For Craig (CTO / Builder):
- Confirm build commitment: ~7-10 days for Phases 1-3, with Phase 4 ongoing.
- Confirm data acquisition: 6-12 months EURUSD 1m from Dukascopy.
- Tech stack decision: FastAPI + Lightweight Charts (recommended) vs alternatives.
- Repo decision: Fresh repo (recommended) vs extend existing.

---

## 9. RELATIONSHIP TO EXISTING CALIBRATION AGENDA

The following items remain from the current calibration pass. Recommendation: complete these with the existing tool (they are fast locks or preference questions), then build the Research Accelerator for validation and future work.

| Item | Estimated Lock Effort | Recommendation |
|---|---|---|
| Liquidity Sweep — Level Sources | 1 session with clean Opus brief | Lock with current tool, re-validate with RA |
| OTE — 70.5% vs band, kill zone gate | Fast lock (fib levels already locked) | Lock with current tool |
| NY Windows — A vs B preference | Preference question, not parameter | Lock with current tool |
| Asia Range — three-tier thresholds | Fast classification lock | Lock with current tool |
| HTF Visual Session | DEFERRED — needs longer TF data | **Do with Research Accelerator** (needs multi-month data anyway) |

---

*This specification is a proposal for elevating a8ra's calibration capability from a disposable tool to a core institutional competence. The moat is not the parameters — it is the rigorous, repeatable, evidence-based process for deriving them.*

*a8ra project — Research Accelerator — 2026-03-08 — PROPOSAL*

ADDENDUM by OPUS

# a8ra RESEARCH ACCELERATOR — ADDENDUM A
## Blue-Sky Analytical Capabilities (Filtered)

**Version:** 0.1 ADDENDUM  
**Date:** 2026-03-08  
**Companion to:** A8RA_RESEARCH_ACCELERATOR_SPEC.md (same date)  
**Context:** Lateral review surfaced 7 analytical capabilities from production quant research platforms. This addendum documents the CTO filter: what's in, what's deferred, where each integrates into the base spec.

---

## FILTER SUMMARY

| Capability | Verdict | Integrates Into | Build Phase |
|---|---|---|---|
| Ground Truth Annotation | **IN — highest value** | Phase 3: Comparison Interface (§3.5) | P3 |
| Parameter Stability Surface | **IN — critical** | Phase 2: Evaluation Runner (§3.4) | P2 |
| Walk-Forward Validation | **IN — required lock gate** | Phase 2: Evaluation Runner (§3.4) | P2 |
| Signal Decay / Half-Life | Deferred — valuable refinement | Phase 5+ (§7 Long-Term) | Future |
| Event Concordance Matrix | Deferred — L2 territory | Phase 5+ (§7 Long-Term) | Future |
| Monte Carlo Permutation | Not built — available ad-hoc | Engine supports it, no UI | — |
| Deflated Detection Rate | Not built — design mitigates need | Provenance covers it | — |

---

## A1. GROUND TRUTH ANNOTATION LAYER

### Integration Point
Base spec §3.5 (Comparison Interface) — new subsection §3.5.5.

### What It Is
A persistent labelling system where Olya marks individual detection events as **CORRECT**, **NOISE**, or **BORDERLINE**. These labels become a scored dataset that transforms every subsequent evaluation from counting (how many detections) to scoring (what precision/recall against expert ground truth).

### Why It's the Highest-Value Addition
Every calibration session currently produces a binary outcome: Olya says "lock" or "adjust." Her per-detection judgments — "that one's real, that one's noise, that one I'm not sure about" — evaporate after the session. They live in facilitator notes at best.

Ground truth labels make those judgments permanent, queryable, and compounding. Each session Olya does grows the label set. Each future config evaluation becomes more precise.

### Interface Design

**On the chart:**
- Click any detection marker → label popover appears
- Three options: ✓ CORRECT | ✗ NOISE | ? BORDERLINE
- Label persists visually (green ring = correct, red ring = noise, amber ring = borderline)
- Labels are per-primitive, per-timeframe, per-detection — not global

**Label dataset schema:**
```yaml
ground_truth_labels:
  - detection_id: "disp_5m_2024-01-08T09:35"
    primitive: displacement
    timeframe: 5m
    label: CORRECT
    labelled_by: Olya
    labelled_date: "2026-03-10T14:32:00"
    notes: ""  # optional — Olya can add a note explaining why
  
  - detection_id: "sweep_15m_2024-01-09T08:15"
    primitive: liquidity_sweep
    timeframe: 15m
    label: NOISE
    labelled_by: Olya
    labelled_date: "2026-03-10T14:35:00"
    notes: "Not a real sweep — level was already mitigated"
```

**Evaluation runner integration:**

When ground truth labels exist for a dataset, the evaluation runner automatically computes:

```yaml
scored_evaluation:
  config: "current_locked"
  primitive: displacement
  dataset: "EURUSD_2024_Q1"
  labels_available: 127  # Olya has labelled 127 displacement events
  
  precision: 0.91        # 91% of detections Olya labelled CORRECT
  recall: 0.78           # 78% of events Olya would mark were detected
  f1: 0.84
  
  borderline_rate: 0.06  # 6% labelled BORDERLINE — ambiguous zone
  
  # Breakdown by context
  by_session:
    nyokz: { precision: 0.94, recall: 0.82 }
    lokz: { precision: 0.88, recall: 0.75 }
    asia: { precision: 0.79, recall: 0.71 }  # ← weakest in Asia
```

**Comparison mode with labels:**

When comparing Config A vs Config B, the output shifts from:
```
Config A: 44 detections/day
Config B: 31 detections/day
```
To:
```
Config A: 44 detections/day — precision 0.78, recall 0.91
Config B: 31 detections/day — precision 0.93, recall 0.82
```

Olya's question becomes: "Do I want the wider net (A) or the cleaner signal (B)?" — which is a strategy question she can answer in seconds, not a visual review question that takes hours.

### Labelling Workflow — Practical

Olya does not need to label every detection. The system is useful with sparse labels. Recommended workflow:

1. **Initial labelling session (30 min):** Pick a single day from the reference dataset. Olya labels all detections for one primitive on that day. ~20-40 labels depending on primitive. This is enough for a meaningful precision/recall baseline.

2. **Incremental labelling:** During normal calibration sessions, Olya labels detections as she reviews them. Labels accumulate session over session.

3. **Targeted labelling:** When the evaluation runner shows a config change affects specific detections, Olya labels only the affected ones — "these 8 detections are new in Config B — are they real?"

4. **Cross-regime labelling:** When walk-forward validation flags a weak regime window, Olya labels a sample from that window to diagnose whether the issue is false positives (precision drop) or missed events (recall drop).

### Moat Argument
The label dataset is Olya's expertise made permanent and quantifiable. It doesn't leave with any team member. It survives strategy evolution. It makes the system measurably better over time. No external competitor can replicate it — it requires thousands of expert judgments accumulated over months.

---

## A2. PARAMETER STABILITY SURFACE

### Integration Point
Base spec §3.4 (Evaluation Runner) — new subsection §3.4.3.

### What It Is
A systematic parameter sweep that maps the "performance landscape" for a primitive's L1.5 parameters. Instead of testing a handful of candidate configs, the runner sweeps a grid across the parameter space and visualises where stable plateaus exist vs where cliff edges drop off.

### Why It's Critical
The displacement session locked ATR 1.5x / body 0.60 based on a 4×4 heatmap. That's 16 data points across a continuous parameter space. We have no idea if 1.5x sits on a plateau (robust — survives regime shift) or a peak (fragile — breaks if anything changes).

A parameter locked on a plateau is worth fundamentally more than a parameter locked on a peak. The stability surface is how you tell the difference.

### Sweep Configuration

```yaml
stability_sweep:
  primitive: displacement
  variant: a8ra_v1
  dataset: "EURUSD_2024_full"
  
  sweep_axes:
    atr_multiplier:
      range: [0.5, 3.0]
      step: 0.1
      # 26 values
    body_ratio:
      range: [0.30, 0.90]
      step: 0.05
      # 13 values
  
  fixed_params:
    combine_mode: "AND"
    atr_period: 14
  
  # Total grid: 26 × 13 = 338 config evaluations
  
  metric: "cascade_to_mss_rate"  # What to plot on the surface
  # Alternative metrics: detection_count, precision (if labels exist),
  # walk_forward_stability, per_session_variance
```

### Output: Stability Heatmap

```
         body_ratio →
         0.30  0.40  0.50  0.60  0.70  0.80  0.90
atr  0.5  ░░░   ░░░   ░░░   ▒▒▒   ▒▒▒   ░░░   ░░░
     1.0  ░░░   ▒▒▒   ▒▒▒   ▓▓▓   ▓▓▓   ▒▒▒   ░░░
     1.5  ░░░   ▒▒▒   ▓▓▓   ███   ▓▓▓   ▒▒▒   ░░░   ← CURRENT LOCK
     2.0  ░░░   ▒▒▒   ▓▓▓   ▓▓▓   ▓▓▓   ▒▒▒   ░░░
     2.5  ░░░   ░░░   ▒▒▒   ▒▒▒   ▒▒▒   ░░░   ░░░
     3.0  ░░░   ░░░   ░░░   ░░░   ░░░   ░░░   ░░░

     ░ = low cascade rate   ▒ = moderate   ▓ = good   █ = best
     
     Reading: ATR 1.0–2.0 × body 0.50–0.70 is a PLATEAU.
     The locked value (1.5, 0.60) sits in the middle of it. ROBUST.
```

### Plateau Detection (Automated)

The runner doesn't just render the heatmap — it identifies plateau regions:

```yaml
stability_analysis:
  primitive: displacement
  metric: cascade_to_mss_rate
  
  plateau_detected: true
  plateau_region:
    atr_multiplier: [1.0, 2.0]   # stable range
    body_ratio: [0.50, 0.70]     # stable range
    metric_variance_within_plateau: 0.03  # very stable
    metric_mean_within_plateau: 0.74
  
  current_lock_position: "CENTER of plateau"  # ← this is what you want to see
  # vs "EDGE of plateau" or "OUTSIDE plateau" — both are warnings
  
  cliff_edges:
    - { axis: "atr_multiplier", direction: "below 0.8", drop: "cascade rate falls from 0.72 to 0.31" }
    - { axis: "body_ratio", direction: "above 0.80", drop: "cascade rate falls from 0.70 to 0.38" }
```

### Presentation to Olya

The heatmap renders in the comparison interface. The current locked value is marked. The plateau region is outlined. Olya sees immediately: "My locked value is in the safe zone" or "My locked value is near the edge — should we shift to centre?"

This replaces the question "does 1.5x look right?" with "1.5x is in the middle of a stable region from 1.0 to 2.0 — it's a safe lock."

### Compute Cost
338 config evaluations × ~370,000 bars = significant but feasible as a batch job. On a single core, each primitive evaluation is <1 second for simple primitives, <5 seconds for composites. Full sweep: 5-30 minutes. Run overnight or on-demand during sessions. Not real-time, but fast enough.

---

## A3. WALK-FORWARD VALIDATION

### Integration Point
Base spec §3.4 (Evaluation Runner) — new subsection §3.4.4.
Base spec §3.5.4 (Lock + Provenance) — new required field.

### What It Is
A rolling out-of-sample test that answers: "If we had locked this config on Month 3, would it have held through Month 4, 5, 6, ...?"

This is the institutional standard for distinguishing real signal from in-sample overfitting. It's the single most important validation gate before deploying capital on a locked parameter.

### Protocol

```yaml
walk_forward:
  config: "current_locked"
  dataset: "EURUSD_2024_full"  # 12 months
  
  window:
    train_months: 3           # calibration window
    test_months: 1            # out-of-sample window
    step_months: 1            # slide forward by 1 month
    
  # This produces 9 train/test splits:
  # Train Jan-Mar  → Test Apr
  # Train Feb-Apr  → Test May
  # Train Mar-May  → Test Jun
  # Train Apr-Jun  → Test Jul
  # Train May-Jul  → Test Aug
  # Train Jun-Aug  → Test Sep
  # Train Jul-Sep  → Test Oct
  # Train Aug-Oct  → Test Nov
  # Train Sep-Nov  → Test Dec
```

### Output

```yaml
walk_forward_results:
  config: "current_locked"
  primitive: displacement
  metric: cascade_to_mss_rate
  
  per_window:
    - { train: "Jan-Mar", test: "Apr", train_metric: 0.74, test_metric: 0.71, delta: -0.03 }
    - { train: "Feb-Apr", test: "May", train_metric: 0.72, test_metric: 0.69, delta: -0.03 }
    - { train: "Mar-May", test: "Jun", train_metric: 0.73, test_metric: 0.68, delta: -0.05 }
    - { train: "Apr-Jun", test: "Jul", train_metric: 0.71, test_metric: 0.42, delta: -0.29 }  # ← REGIME BREAK
    - { train: "May-Jul", test: "Aug", train_metric: 0.65, test_metric: 0.61, delta: -0.04 }
    - { train: "Jun-Aug", test: "Sep", train_metric: 0.68, test_metric: 0.70, delta: +0.02 }
    # ...
  
  summary:
    mean_test_metric: 0.66
    std_test_metric: 0.09
    worst_window: { test: "Jul", metric: 0.42, regime: "low_vol_summer" }
    degradation_flag: true  # at least one window dropped >20% from train
    
  verdict: "CONDITIONALLY STABLE — holds in 8/9 windows. July degradation 
            correlates with summer low-volatility regime. Investigate whether 
            regime-adaptive parameters are needed or whether degradation is 
            acceptable given the regime is low-opportunity."
```

### Integration with Lock Workflow

The lock record from §3.5.4 gains a required field:

```yaml
lock_record:
  primitive: displacement
  variant: a8ra_v1
  params_locked: { atr_multiplier: 1.5, body_ratio: 0.60, combine_mode: AND }
  
  # ... existing fields ...
  
  # NEW — REQUIRED
  walk_forward_validation:
    status: PASSED            # PASSED | CONDITIONALLY_PASSED | FAILED
    windows_tested: 9
    windows_passed: 8         # test metric within 15% of train metric
    windows_failed: 1
    failure_diagnosis: "July 2024 — low-vol summer regime, cascade rate dropped to 0.42"
    olya_decision: "Acceptable — July is low-opportunity month, we don't force trades"
```

**Rule: No parameter locks without walk-forward validation once the RA is operational.** This is the quality gate that separates institutional from hobby-grade.

### Regime Diagnosis

When walk-forward flags a weak window, the system automatically cross-references with regime tags:

```yaml
regime_diagnosis:
  weak_window: "Jul 2024"
  regime_tags: ["low_vol", "summer", "ranging"]
  
  comparison:
    metric_in_trending_regimes: 0.73
    metric_in_ranging_regimes: 0.58
    metric_in_low_vol_regimes: 0.44
  
  interpretation: "Parameter holds in trending and normal-vol regimes. 
                   Degrades in low-vol ranging conditions. This is expected — 
                   displacement is a volatility-dependent signal."
```

This is information Olya can act on: "In summer, tighten position size or skip displacement-dependent setups." That's an L2 decision informed by L1.5 evidence.

---

## A4. DEFERRED CAPABILITIES (Phase 5+)

These are noted for future build. Not in scope for initial RA deployment but architecturally accounted for.

### Signal Decay / Half-Life Analysis

**What:** Measure how quickly a detection's predictive value decays after firing. An OB detected at 08:15 — is it still valid at 09:00? At 14:00?

**Why deferred:** Requires ground truth labels to define "valid" (did price reach the zone? did it hold?). Build after annotation layer has accumulated data.

**Architecture note:** The detection engine already tracks OB lifecycle (ACTIVE → MITIGATED → INVALIDATED → EXPIRED). Half-life analysis is a statistical summary of lifecycle durations. No new detection logic needed — just an evaluation runner mode that aggregates lifecycle data.

**Expected output:**
```yaml
half_life:
  primitive: order_block
  timeframe: 5m
  median_lifespan_bars: 7
  pct_mitigated_within_10_bars: 0.68
  pct_mitigated_within_20_bars: 0.84
  pct_expired_without_mitigation: 0.16
  recommendation: "Current expiry of 10 bars is appropriate — captures 68% of mitigations"
```

### Event Concordance Matrix

**What:** Quantify which primitive combinations predict directional follow-through. When displacement + FVG + MSS fire together within N bars, what happens vs when only displacement fires alone?

**Why deferred:** This is L2 territory — strategy-layer analysis. The RA's initial scope is L1/L1.5. Concordance analysis should come after all primitives are locked and the ground truth label set is substantial.

**Architecture note:** The cascade evaluation (§3.4.2 in base spec) already tracks co-occurrence implicitly. Concordance matrix is a cross-tabulation of cascade output. The engine supports it — it just needs a dedicated evaluation mode and visualisation.

**Expected output:** Confluence heatmap showing co-occurrence rates and directional follow-through for all primitive pair combinations. This becomes the quantitative foundation for L2 strategy specification.

---

## A5. NOT BUILT (Available Ad-Hoc)

### Monte Carlo Permutation Testing
The parameterised engine supports generating random detection timestamps and running them through the cascade. If someone wants to validate that a primitive's cascade rate exceeds random chance, they can write a short script using the engine's API. No dedicated UI panel — the signal-vs-noise question is better answered by walk-forward validation for ICT primitives, which produce structural (not statistical) signals.

### Deflated Detection Rate (Multiple Testing Correction)
The provenance model (§3.5.4) already records how many configs were compared before locking. The calibration workflow is principled (research-motivated candidates, not brute-force search), so the multiple testing problem is mild. If the search space ever expands to hundreds of automated configs, revisit. For now, provenance is sufficient.

---

## A6. UPDATED BUILD PHASES (Revised from Base Spec §5)

Changes from base spec are marked with **[+NEW]**.

### Phase 1: Detection Engine + Data Layer (2-3 days)
*No changes from base spec.*

### Phase 2: Evaluation Runner + Comparison Stats (2-3 days) — was 1-2 days
- Statistical comparison engine (base spec)
- Cascade evaluation (base spec)
- **[+NEW] Parameter Stability Sweep mode** — grid sweep with heatmap output and automated plateau detection
- **[+NEW] Walk-Forward Validation mode** — rolling train/test protocol with regime cross-reference
- Output formats: YAML + CSV

### Phase 3: Comparison Interface (2-3 days)
- Full-stack chart with toggleable layers (base spec)
- Multi-config overlay (base spec)
- Parameter control panel (base spec)
- Statistics dashboard (base spec)
- Lock + provenance **(+walk_forward_validation required field)** [+NEW]
- **[+NEW] Ground Truth Annotation** — click-to-label on chart markers, label persistence, precision/recall/F1 integration in evaluation output

### Phase 4: External Algo Integration (Ongoing)
*No changes from base spec.*

### Phase 5: Production Monitoring + Advanced Analytics (Future)
- Live data ingestion (base spec)
- Regime drift detection (base spec)
- **[+NEW] Signal Decay / Half-Life analysis**
- **[+NEW] Event Concordance Matrix**

### Revised Total Estimate
Base spec: 7-10 days for Phases 1-3.
With addendum: **8-12 days for Phases 1-3.** The additions are analytically significant but build on infrastructure that already exists in the base spec. The stability sweep is an evaluation runner mode. Walk-forward is an evaluation runner mode. Ground truth is a UI feature + a join in the evaluation output. None of them require new architectural components.

---

## A7. DECISION FRAMEWORK FOR OPUS

When Opus receives the base spec + this addendum for build scoping, the priority order is:

1. **Detection engine with parameterised modules** — everything else depends on this
2. **Evaluation runner with cascade stats** — this is the core analytical capability
3. **Walk-forward validation** — this is the lock quality gate
4. **Parameter stability sweep** — this protects against fragile locks
5. **Comparison interface with chart** — this is how Olya interacts
6. **Ground truth annotation** — this makes everything measurable over time
7. **External algo integration** — this accelerates research

Items 1-6 are the "no compromise" scope. Item 7 is ongoing and can begin as soon as the engine interface is stable.

If build time is constrained, items 3 and 4 can ship as CLI-only tools initially (no UI), with visualisation added when the comparison interface is built. The analytical value exists without the chart — a YAML report showing walk-forward results or a heatmap rendered as a PNG is enough to make decisions.

---

*Addendum A to A8RA_RESEARCH_ACCELERATOR_SPEC.md — 2026-03-08*  
*Read together with base spec. This document does not supersede the base spec — it extends §3.4, §3.5, §5, and §7.*

Below is a drop-in Addendum B written in the same spec-style language as your current document so it can sit directly in the canonical repo.

⸻

ADDENDUM B — FORENSIC CASE RUNNER / EVENT BACKSOLVE MODE

document: A8RA_RESEARCH_ACCELERATOR_SPEC
addendum: B
title: FORENSIC_CASE_RUNNER
purpose: "Enable deterministic replay and diagnosis of known high-quality trading events to verify primitive detection fidelity and isolate cascade failures."
author: a8ra
status: PROPOSED


⸻

1. RATIONALE

The Research Accelerator currently evaluates primitive detection using:

datasets
parameter configs
benchmark algorithms
statistical evaluation

This provides broad calibration capability but does not fully address the following research requirement:

Given a known high-quality trade example identified by the trader,
determine whether the primitive detection stack would have detected it,
and if not, precisely identify where the cascade failed.

Professional discretionary traders often recognize high-quality setups visually and contextually. These examples represent valuable ground truth anchors.

The Forensic Case Runner enables the system to:

replay known events
trace primitive cascades
diagnose detection failures
guide parameter refinement

This converts the calibration system into a forensic research instrument capable of aligning algorithmic detection with expert pattern recognition.

⸻

2. CONCEPTUAL MODEL

The system introduces a new artifact:

EVENT_CASE

An Event Case represents a historically verified trading opportunity identified by the trader.

The system then runs:

CASE_REPLAY(event_case, config)

to determine:

Did the primitive cascade detect the event?
If not, which primitive failed and why?

This allows researchers to work backwards from known good trades rather than relying solely on forward statistical discovery.

⸻

3. EVENT CASE FILES

Event Cases are stored as structured artifacts in the Research Accelerator.

research_accelerator/
  cases/
    EURUSD_2024_09_18_SHORT_01.yaml
    GBPUSD_2024_11_07_LONG_02.yaml

Example case definition:

case_id: EURUSD_2024_09_18_SHORT_01

metadata:
  labelled_by: Olya
  labelled_at: 2026-03-08
  instrument: EURUSD
  confidence: TEXTBOOK
  strategy_family: LOKZ_REVERSAL

timeframe_stack:
  - 1H
  - 15m
  - 5m

event_window:
  start: 2024-09-18T08:20:00-04:00
  end:   2024-09-18T08:50:00-04:00

trade:
  direction: SHORT
  entry_zone:
    low: 1.0732
    high: 1.0739

expected_primitives:

  context:
    - type: HTF_BIAS
      timeframe: 1H
      expected: BEARISH

  setup:
    - type: LIQUIDITY_SWEEP
      timeframe: 15m
    - type: DISPLACEMENT
      timeframe: 5m
    - type: MSS
      timeframe: 5m
    - type: FVG
      timeframe: 5m

notes:
  - "London reversal after Asia high sweep"

Event Cases capture:

instrument
time window
expected primitives
timeframe hierarchy
entry zone
confidence rating

These cases become a library of known desirable trading opportunities.

⸻

4. CASE REPLAY ENGINE

The Forensic Case Runner executes a replay against the detection engine.

CASE_REPLAY(case, config)

Steps:

1. Load market dataset
2. Run primitive detection using config
3. Extract detections within event window
4. Match detections to expected primitives
5. Build cascade outcome report

Output classification:

PASS
PARTIAL
MISS


⸻

5. CASCADE FAILURE DIAGNOSTICS

The runner must diagnose exactly where detection failed.

Example output:

case_id: EURUSD_2024_09_18_SHORT_01
config: displacement_v2_locked

verdict: PARTIAL

cascade_results:

  liquidity_sweep_15m:
    status: PASS
    detection_id: sweep_20240918_0830

  displacement_5m:
    status: PASS
    detection_id: disp_20240918_0835

  mss_5m:
    status: FAIL
    failure_type: STRUCTURE_THRESHOLD

  fvg_5m:
    status: PASS

root_cause:

  primitive: MSS
  detail: "Swing promotion threshold prevented break recognition"

Failure categories:

THRESHOLD_TOO_STRICT
THRESHOLD_TOO_LOOSE
TIMEFRAME_MISMATCH
DETECTION_DELAY
MISSING_UPSTREAM_PRIMITIVE
CASCADE_LINK_WINDOW_EXCEEDED

This transforms a vague “missed detection” into a precise engineering diagnosis.

⸻

6. EVENT MATCH TOLERANCE

Exact timestamp equality is unreliable.

Matching must allow tolerance bands.

Example:

match_tolerance:

  time:
    sweep_15m: ±1 bar
    mss_5m: ±2 bars
    fvg_5m: ±2 bars

  price:
    default: ±0.25 ADR%

Without tolerances, legitimate detections may incorrectly appear as misses.

⸻

7. NEAR-MISS ANALYSIS

The system must identify near-miss scenarios where primitives almost fired.

Example output:

near_miss:

  primitive: MSS
  closest_candidate:
    break_distance:
      required: 1.8 ATR
      observed: 1.7 ATR

  classification: THRESHOLD_NEAR_MISS

Near-miss classification types:

THRESHOLD_NEAR_MISS
TIME_ALIGNMENT_NEAR_MISS
PREMATURE_DETECTION
DELAYED_DETECTION
PARTIAL_CASCADE

Near-miss analysis is one of the most valuable outputs of this system.

⸻

8. EXPECTED VS ACTUAL CASCADE

For each case the system constructs two graphs:

EXPECTED_CASCADE
ACTUAL_CASCADE

Example:

Expected:

sweep → displacement → MSS → FVG → entry

Actual:

sweep → displacement → FVG

This visualization allows rapid identification of cascade breaks.

⸻

9. CASE LIBRARY STRUCTURE

Cases should be stratified by quality.

confidence_levels:

  TEXTBOOK
  STRONG
  ACCEPTABLE
  BORDERLINE

Calibration and parameter search should primarily optimize for:

TEXTBOOK
STRONG

to avoid overfitting to marginal setups.

⸻

10. NEGATIVE CASES

The system must also support negative cases.

Negative cases represent situations where primitives should not fire.

Example:

negative_case:

  case_id: EURUSD_2024_10_04_FALSE_SWEEP

  expectation:
    liquidity_sweep: SHOULD_NOT_FIRE

  reason:
    "Equal highs but no displacement"

Maintaining both positive and negative cases ensures the system improves both:

recall
precision


⸻

11. RESEARCH WORKFLOW

Recommended workflow:

1. Trader marks prime setups in TradingView
2. Cases added to case library
3. Research Accelerator runs case replay
4. Diagnostics identify primitive failure points
5. Parameter search explores refinement surface
6. New candidate configs evaluated statistically
7. Stable configs locked via governance

This loop provides a powerful mechanism for aligning algorithmic detection with expert trading judgment.

⸻

12. RELATIONSHIP TO PARAMETER SEARCH

The Forensic Case Runner complements the Search Orchestrator described in Addendum A.

Search Orchestrator:

discovers candidate parameter configurations

Forensic Case Runner:

tests candidate configs against known good trades

Together they provide:

candidate discovery
+
expert-aligned validation


⸻

13. GOVERNANCE SAFEGUARDS

The following invariants apply:

INV_CASE_NO_AUTOMATIC_LOCK:
  Case success alone cannot lock a configuration.

INV_CASE_BOUNDED_SCOPE:
  Case replay cannot modify detection algorithms.

INV_CASE_HUMAN_REVIEW_REQUIRED:
  All parameter promotions require human approval.

The system remains deterministic and audit-safe.

⸻

14. STRATEGIC ROLE

The Forensic Case Runner transforms the Research Accelerator into a trading research laboratory.

It enables:

expert knowledge encoding
primitive detection verification
cascade failure diagnosis
precision calibration

Over time the case library becomes a high-value institutional dataset representing the trader’s pattern recognition expertise.

⸻

15. SUMMARY

The Forensic Case Runner enables the Research Accelerator to answer the most important question in primitive calibration:

If a trader clearly sees a prime trade,
can the system detect the primitive cascade that produced it?

When the answer is no, the system provides precise diagnostics explaining why the cascade failed.

This capability dramatically accelerates the process of aligning algorithmic detection with expert trading judgment.

⸻

Addendum C

Below is a spec-style Addendum C that fits directly after Addendum B and aligns with the architecture you have been shaping.

⸻

ADDENDUM C — SEARCH ORCHESTRATOR / PARAMETER DISCOVERY ENGINE

document: A8RA_RESEARCH_ACCELERATOR_SPEC
addendum: C
title: SEARCH_ORCHESTRATOR
purpose: "Enable bounded discovery of primitive parameter configurations through systematic search and evaluation."
author: a8ra
status: PROPOSED


⸻

1. RATIONALE

The Research Accelerator allows researchers to manually define primitive configurations and compare outcomes.

However, manual configuration testing introduces several limitations:

limitations:
  - limited exploration of parameter space
  - researcher bias in selecting candidate configs
  - slow discovery of robust parameter plateaus
  - missed interactions between primitive parameters

The Search Orchestrator addresses these limitations by enabling bounded exploration of configuration space.

Its role is to generate candidate parameter configurations, evaluate them against datasets and cases, and surface robust candidate regions for human review.

The orchestrator therefore converts calibration into a systematic parameter discovery process.

⸻

2. CONCEPTUAL MODEL

The orchestrator operates by exploring declared search spaces.

Researchers define:

search_space
evaluation_objectives
constraints

The system then performs structured exploration and returns ranked candidate configurations.

Example:

researcher_input:

  primitive: DISPLACEMENT

  search_space:
    atr_multiplier: [1.0, 2.0, step 0.1]
    body_ratio: [0.5, 0.8, step 0.05]
    combine_mode: [AND, OR]

  objective:
    maximize: precision

  constraints:
    max_detections_per_day: 6

The orchestrator generates candidate configurations, evaluates them, and produces a ranked frontier of viable options.

⸻

3. SYSTEM ARCHITECTURE

The Search Orchestrator sits between evaluation and visualization layers.

pipeline:

  dataset_loader
    →
  primitive_detection_engine
    →
  evaluation_runner
    →
  search_orchestrator
    →
  comparison_interface

Responsibilities:

search_orchestrator:
  generate_candidates
  execute_evaluations
  analyze_results
  surface_frontier_configs

The orchestrator never modifies primitive algorithms themselves.

It only explores parameter combinations.

⸻

4. SEARCH SPACE DEFINITION

Search spaces must be explicitly declared.

Example:

search_space:

  displacement:

    atr_multiplier:
      min: 1.0
      max: 2.0
      step: 0.1

    body_ratio:
      min: 0.5
      max: 0.8
      step: 0.05

    combine_mode:
      options:
        - AND
        - OR

Search space types:

parameter_types:

  numeric_range
  categorical_options
  boolean_toggle
  primitive_source_pool

All searches remain bounded to declared domains.

⸻

5. SEARCH MODES

The orchestrator supports multiple search strategies.

Initial implementation should include:

search_modes:

  GRID_SEARCH:
    deterministic parameter enumeration

  COMBINATORIAL_SEARCH:
    exploration of primitive source combinations

Future enhancements may include:

future_modes:

  RANDOM_SEARCH
  BAYESIAN_OPTIMIZATION
  ADAPTIVE_PLATEAU_SEARCH

These methods allow deeper exploration of high-dimensional parameter spaces.

⸻

6. EVALUATION METRICS

Candidate configurations are evaluated using multiple metrics.

Example metric set:

metrics:

  precision
  recall
  detections_per_day
  regime_consistency
  cascade_completion_rate

When Forensic Case Runner is enabled, additional metrics include:

case_metrics:

  case_detection_rate
  cascade_alignment_score
  near_miss_rate

Evaluation results are aggregated across:

datasets
regimes
cases


⸻

7. MULTI-OBJECTIVE OPTIMIZATION

Primitive calibration rarely reduces to a single objective.

The orchestrator therefore evaluates configurations across multiple objectives simultaneously.

Example objective definition:

objectives:

  primary:
    - precision
    - case_detection_rate

  secondary:
    - cascade_completion_rate
    - regime_consistency

The orchestrator identifies candidate configurations that lie on the Pareto frontier.

Example output:

pareto_frontier:

  config_12:
    precision: 0.94
    recall: 0.71
    detections_per_day: 2.3

  config_27:
    precision: 0.91
    recall: 0.77
    detections_per_day: 3.1

Researchers then evaluate trade-offs between candidate configurations.

⸻

8. ROBUSTNESS ANALYSIS

Peak-performing configurations are often unstable.

The orchestrator therefore analyzes parameter stability surfaces.

Example classification:

candidate_assessment:

  config_18:
    plateau_position: EDGE
    walk_forward_stability: LOW
    classification: FRAGILE

  config_27:
    plateau_position: CENTER
    walk_forward_stability: HIGH
    classification: ROBUST

Preference is given to plateau-center configurations rather than narrow local maxima.

⸻

9. SOURCE POOL EXPLORATION

Some primitives depend on multiple possible source pools.

Example for liquidity sweep:

source_pool:

  - session_high_low
  - asia_range
  - equal_highs
  - swing_levels

Search may explore combinations:

max_sources_enabled: 3

Example candidate outputs:

source_configs:

  - [asia_range, equal_highs]
  - [session_high_low, equal_highs]
  - [session_high_low, asia_range, equal_highs]

This enables systematic exploration of structural detection logic.

⸻

10. RESULT OUTPUT

Search runs generate a structured report.

Example:

search_run:

  run_id: SR_2026_03_08_001
  primitive: DISPLACEMENT
  configs_tested: 480

  top_candidates:

    config_27:
      precision: 0.91
      recall: 0.76
      robustness: HIGH

    config_12:
      precision: 0.94
      recall: 0.71
      robustness: MEDIUM

Supporting artifacts include:

outputs:

  ranked_config_table
  pareto_frontier
  stability_heatmap
  case_alignment_report

These results are stored in the research provenance layer.

⸻

11. GOVERNANCE CONSTRAINTS

The Search Orchestrator operates under strict constraints.

invariants:

  INV_SEARCH_BOUNDED:
    Search may vary only declared parameters.

  INV_SEARCH_NO_STRATEGY_INJECTION:
    Search cannot introduce strategy-level logic.

  INV_SEARCH_NO_AUTOMATIC_LOCK:
    Configurations discovered by search require human approval.

  INV_SEARCH_PROVENANCE:
    All search runs must record dataset, parameters, and metrics.

These safeguards ensure reproducibility and prevent uncontrolled algorithm mutation.

⸻

12. RESEARCH WORKFLOW

Recommended workflow:

workflow:

  1. Define primitive and search space
  2. Execute search run
  3. Review Pareto frontier
  4. Validate candidates with Forensic Case Runner
  5. Conduct regime walk-forward testing
  6. Lock configuration via governance

This process ensures parameter discovery remains systematic, transparent, and auditable.

⸻

13. STRATEGIC ROLE

The Search Orchestrator transforms the Research Accelerator from a manual calibration tool into a structured discovery engine.

It enables:

systematic parameter exploration
robust primitive calibration
objective algorithm benchmarking
plateau discovery

Combined with the Forensic Case Runner and core calibration tools, it forms a comprehensive research environment for developing reliable primitive detection logic.

⸻

14. SUMMARY

The Search Orchestrator enables the Research Accelerator to answer a critical research question:

Within the allowable parameter space,
which configurations most reliably detect meaningful market primitives?

By automating exploration of parameter configurations while maintaining strict governance boundaries, the system accelerates discovery while preserving architectural discipline.

⸻

Micro Search Function

Local Micro-Search (Event-Centered Parameter Exploration)

The idea is a small, fast search loop focused on a single Event Case, rather than the whole dataset. It accelerates diagnosis when a known trade almost matches your primitive logic.

⸻

1. Purpose

The Local Micro-Search compresses research around one event.

Instead of:

edit parameters
run full dataset
inspect results
repeat

the system performs:

focus on event window
explore nearby parameter space
identify why detection failed

Typical runtime target:

seconds to minutes

not hours.

⸻

2. Conceptual Model

The process begins with a case replay failure.

Example:

case_result:
  case_id: EURUSD_2024_09_18_SHORT_01
  verdict: MISS
  failing_primitive: MSS_5m

The Micro-Search then activates a local search surface around the failing primitive.

global calibration
        ↓
case replay
        ↓
primitive failure detected
        ↓
local micro-search around that primitive


⸻

3. Search Window

Micro-Search restricts the dataset to a small window around the event.

Example:

local_dataset:

  center_time: 2024-09-18T08:35
  window:
    before: 120 bars
    after: 60 bars

This ensures extremely fast iteration.

⸻

4. Parameter Surface Exploration

The system explores a narrow band of parameters near the current configuration.

Example:

primitive: MSS

current_config:

  swing_threshold: 1.0
  break_confirmation: close
  displacement_required: true

Micro-Search generates candidates:

search_surface:

  swing_threshold:
    range: [0.8 → 1.2]
    step: 0.05

  break_confirmation:
    options: [close, wick]

  displacement_required:
    options: [true, false]


⸻

5. Candidate Evaluation

Each candidate configuration is evaluated only on the local event window.

Outputs:

candidate_results:

  config_A:
    event_detected: true
    detection_time: 08:36
    cascade_complete: true

  config_B:
    event_detected: false
    reason: swing_not_promoted

  config_C:
    event_detected: true
    cascade_incomplete

This isolates the parameter combinations that would allow the primitive cascade to fire.

⸻

6. Outcome Classification

Results are categorized into three types.

diagnosis:

  PARAMETER_ISSUE:
    primitive logic correct
    thresholds too strict/loose

  LOGIC_ISSUE:
    primitive algorithm cannot represent event

  LABEL_MISMATCH:
    human interpretation differs from algorithm definition

This distinction is crucial for deciding whether to:

adjust parameters
or
revisit primitive design


⸻

7. Suggested Refinement Surface

The Micro-Search returns a ranked set of parameter changes.

Example:

suggested_refinements:

  candidate_1:
    swing_threshold: 0.9
    break_confirmation: close
    robustness_score: HIGH

  candidate_2:
    swing_threshold: 0.85
    break_confirmation: wick
    robustness_score: MEDIUM

These become candidate configs for full-dataset evaluation.

⸻

8. Safety Constraint

Micro-Search cannot promote configurations automatically.

All outputs must flow back through the normal validation pipeline:

micro-search
    ↓
candidate config
    ↓
global evaluation
    ↓
walk-forward testing
    ↓
human lock

This prevents overfitting to a single event.

⸻

9. Strategic Value

Micro-Search dramatically speeds up the research loop.

Instead of manually iterating parameters around a single trade example, the system performs targeted exploration automatically.

Benefits:

faster primitive debugging
clear root-cause diagnosis
better alignment with expert pattern recognition
reduced research friction

This feature is particularly powerful when combined with:

Event Case Library
Search Orchestrator
Forensic Case Runner

Together they create a research environment capable of both:

broad discovery
and
surgical event-level investigation


⸻

10. One-Line Summary

The Local Micro-Search allows the system to answer:

"If this trade should have fired,
what minimal parameter changes would allow the primitive cascade to detect it?"

This provides a rapid diagnostic tool for refining primitive logic without disrupting the broader research pipeline.