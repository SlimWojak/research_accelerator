# PROJECT_STATE.md — a8ra ICT Primitives Codification
## Checkpoint: 2026-03-04 ~15:30 NY (Session 10)

> **Purpose**: Immediate orientation for any future session. Read this FIRST.

---

## 1. WHAT IS THIS PROJECT

Codification of Olya's ICT (Inner Circle Trader) methodology into production-quality algorithmic detection code. The primitives (FVG, Swing Points, Displacement, Order Blocks, Session Windows, PDH/PDL) must be detected on price data with configurable thresholds, validated visually against Olya's expert eye, then locked for production.

**End state**: A calibrated, tested detection engine that faithfully reproduces what Olya sees on her charts — no invention, no novel approaches. Research what EXISTS in production algo trading.

---

## 2. TEAM & ROLES

| Name | Role | Trust Level |
|------|------|-------------|
| **Craig** | Sovereign Operator, project owner | Final authority on all decisions |
| **Olya** | Strategist, ICT methodology source-of-truth | **INV-OLYA-ABSOLUTE** — her word overrides all advisors |
| **Claude Opus** | CTO — architecture, briefs, synthesis | Senior advisor |
| **Gemini** | Wise Owl — second opinion | Advisor |
| **Grok** | BOAR — stress testing | Advisor |
| **GPT** | Architecture/Lint validation | Advisor |
| **Perplexity Computer** | Naive-eyes pressure tester, builder | Execution agent (this tool) |

**Communication protocol**: Craig relays between advisors. Perplexity Computer does NOT contact other advisors directly. Craig + Olya do detailed review of all outputs.

---

## 3. THREE-LAYER ARCHITECTURE

```
┌─────────────────────────────────────────────┐
│  L1 — Geometric Detection (LOCKED)          │
│  Pure math: candle[A].high < candle[C].low  │
│  No tuning. Either a gap exists or it doesn't│
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│  L1.5 — Parameter Thresholds (CALIBRATING)  │
│  min_gap_pips, swing N, displacement ATR_k  │
│  This is what the Visual Bible calibrates   │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│  L2 — Strategy Interpretation (OLYA DOMAIN) │
│  "This FVG matters because of session       │
│   context + displacement + OB confluence"   │
│  NOT our job to codify — Olya decides       │
└─────────────────────────────────────────────┘
```

**Current focus**: L1.5 calibration via the Visual Bible tool.

---

## 4. LOCKED DECISIONS (DO NOT REVISIT)

These were resolved in Phase 2 brief + Craig's green-light answers:

| Decision | Resolution | Source |
|----------|-----------|--------|
| VI (Volume Imbalance) standalone | **KILLED** — retained only as FVG attribute | Phase 2 brief |
| MMXM (Market Maker Model) | **RETROSPECTIVE ONLY** — not real-time detection | Phase 2 brief |
| FVG geometry | `low[C] > high[A]` (bullish), `high[C] < low[A]` (bearish) | Phase 1 research, confirmed |
| Swing equality | `>=` left side, `>` right side | Phase 2 brief |
| Threshold model | **HYBRID**: `max(floor_pips, ATR_fraction)` | Craig Q2 answer |
| FVG invalidation | Track BOTH `ce_touched` and `boundary_closed_through` (zone color states) | Phase 2 brief |
| Swing strength | Cap at 20 additional bars beyond N=5 base | Phase 2 brief |
| OB retest | Wick-into-zone: `price.low <= ob.high` for bullish | Phase 2 brief |
| TF detection | **NATIVE per-TF** — NOT projected from 1m | Olya review (Session 9) |
| Timestamps | **NY time** throughout (Olya always works in NY time) | Olya review (Session 9) |
| Session markers | Visual session bands on ALL charts | Olya review (Session 9) |

---

## 5. WHAT HAS BEEN BUILT

### 5a. Data Pipeline

**Source data**: `eurusd_1m_2024-01-07_to_2024-01-12.csv` — 7,177 bars of real EURUSD 1-minute data.

**Pipeline script**: `preprocess_data_v2.py` (42.7 KB)
- Reads 1m CSV, aggregates to 5m and 15m candles natively
- Runs ALL detections independently on each timeframe's bars
- FVG, Swing, Displacement, OB, Sessions, NY Windows, PDH/PDL
- Outputs per-TF JSON files + candle JSON + session boundaries
- All timestamps in NY time (EST = UTC-5 for Jan 2024)

**YAML export**: `generate_advisor_export_v3.py` → produces `calibration_data_export.yaml` (294 KB, 2,882 lines)
- Structured data for CTO + Advisor panel review
- Full event lists at default thresholds, summary counts at all thresholds
- Multi-TF: 1m, 5m (primary), 15m

### 5b. Calibration Visual Bible (Deployed Website)

**Live URL**: https://www.perplexity.ai/computer/a/a8ra-calibration-visual-bible-RWDlyN.bTaOYst5ta40gJQ

**6 interactive chart pages** using TradingView Lightweight Charts v4:
1. **FVG** (`fvg.html`) — Fair Value Gaps with threshold slider, CE/boundary markers
2. **Swings** (`swings.html`) — Swing highs/lows with N-parameter slider
3. **Displacement** (`displacement.html`) — Displacement candles with ATR multiplier slider
4. **Order Blocks** (`ob-staleness.html`) — OB zones with staleness/retest tracking
5. **NY Windows** (`ny-windows.html`) — NY reversal windows A (08:00-09:00) and B (10:00-11:00)
6. **Asia Range** (`asia.html`) — Asia session high/low/midline with deviation tracking

**All charts feature**:
- Timeframe toggle: 1m / 5m / 15m (native detection per TF)
- Day-by-day navigation (forex days: Jan 8-12, 2024)
- Session boundary bands (Asia=teal, LOKZ=purple, NYOKZ=orange)
- NY timestamps throughout
- Threshold sliders where applicable
- Summary statistics panel

### 5c. Key Detection Counts (Native, Default Thresholds)

| Primitive | 1m | 5m | 15m |
|-----------|-----|-----|------|
| FVG | 2,017 | 345 | ~90 |
| Swings | 833 | 163 | ~45 |
| Displacement | 4,569 | 875 | ~250 |
| Order Blocks | 601 | 106 | ~30 |

---

## 6. FILE MANIFEST

### Root workspace (`/home/user/workspace/`)

| File | Description | Status |
|------|-------------|--------|
| `PROJECT_STATE.md` | **THIS FILE** — orientation checkpoint | Current |
| `SYNTHETIC_OLYA_METHOD_v0.4.yaml` | Full v0.4 methodology (806 lines) | Reference input |
| `eurusd_1m_2024-01-07_to_2024-01-12.csv` | Source 1m candle data (7,177 bars) | Source data |
| `PERPLEXITY_BRIEF_ICT_PRIMITIVES.md` | CTO's original research brief | Reference |
| `PERPLEXITY_PHASE2_BRIEF.md` | Phase 2 brief from CTO+Advisors | Reference |
| `ICT_PRIMITIVES_RESEARCH_PACK.md` | Phase 1 master synthesis (813 lines) | Completed research |
| `research_fvg_vi.md` | Phase 1: FVG + VI deep dive | Completed |
| `research_swing_points.md` | Phase 1: Swing point variants | Completed |
| `research_sessions_pdh_asia.md` | Phase 1: Sessions + PDH + Asia | Completed |
| `research_tier2_primitives.md` | Phase 1: OB, Displacement, Breaker, Mitigation | Completed |
| `sanity_band_results.md` | Sanity band analysis results | Completed |
| `sanity_band_analysis.py` | Initial sanity check script | Superseded |
| `sanity_band_analysis_v2.py` | Revised sanity check | Superseded |
| `preprocess_data.py` | Original pipeline (1m projection) | **SUPERSEDED by v2** |
| `preprocess_data_v2.py` | **CURRENT** pipeline (native multi-TF) | Active |
| `generate_advisor_export.py` | Original YAML exporter | Superseded |
| `generate_advisor_export_v2.py` | v2 YAML exporter | Superseded |
| `generate_advisor_export_v3.py` | **CURRENT** multi-TF YAML exporter | Active |
| `CHART_REBUILD_SPEC.md` | Spec used by subagents for chart rebuilds | Reference |

### Deployed site (`/home/user/workspace/calibration-bible/`)

| File | Description |
|------|-------------|
| `index.html` | Landing page with links to all 6 charts |
| `fvg.html` | Fair Value Gap chart |
| `swings.html` | Swing Points chart |
| `displacement.html` | Displacement chart |
| `ob-staleness.html` | Order Block chart |
| `ny-windows.html` | NY Reversal Windows chart |
| `asia.html` | Asia Range chart |
| `BUILDSPEC.md` | Design tokens, color system, technical spec |
| `metadata.json` | Pipeline metadata (thresholds, counts per TF) |
| `session_boundaries.json` | Session band coordinates for chart markers |
| `calibration_data_export.yaml` | Advisor YAML v3 (294 KB, 2,882 lines) |
| `candles_2024-01-{08-12}.json` | Per-day candle data (NY timestamps, full field names) |
| `{primitive}_data_{1m,5m,15m}.json` | Per-TF detection results (FVG, swing, displacement, OB, ny_windows) |
| `asia_data.json`, `levels_data.json` | Asia range + PDH/PDL (not TF-dependent) |
| `{primitive}_data.json` | Backward-compat copies (= 1m versions) |

---

## 7. TECHNICAL CONSTANTS

```
EURUSD pip value:     0.0001 (5-decimal pricing)
Forex day boundary:   17:00 NY
Data period:          2024-01-07 to 2024-01-12 (forex days Jan 8-12)
Timezone:             NY (EST in January = UTC-5, no DST)

Sessions (NY time):
  Asia:    19:00 — 00:00
  LOKZ:    02:00 — 05:00
  NYOKZ:   07:00 — 10:00

NY Reversal Windows (NY time):
  Window A: 08:00 — 09:00
  Window B: 10:00 — 11:00

Threshold sweep ranges:
  1m  FVG: [0.5, 1, 1.5, 2, 3, 5] pip
  5m  FVG: [1, 2, 3, 4, 5, 7, 10] pip
  15m FVG: [2, 3, 5, 7, 10, 15] pip
  Swing N: [3, 4, 5, 6, 7, 8, 10] (all TFs)
  Displacement ATR_k: [1.0, 1.5, 2.0, 2.5, 3.0] (all TFs)
```

---

## 8. CRITICAL PIVOT LOG

**Session 9 (Olya's review)** revealed three issues that required full rebuild:

1. **Native TF detection**: Original pipeline detected everything on 1m bars then "projected" to 5m/15m. Olya/CTO said this is wrong — "A genuine 5m FVG requires the gap to exist across 3 consecutive 5m candles." Detection must run independently on each TF's aggregated bars.

2. **NY time**: All timestamps were in UTC. Olya always works in NY time. Converted everything.

3. **Session markers**: Charts needed visual session boundary bands so Olya can see where Asia/LOKZ/NYOKZ start and end.

**Resolution (this session)**: Complete rewrite of pipeline (`preprocess_data_v2.py`), regeneration of all JSON data, rebuild of all 6 chart HTML files + index, new YAML export v3. Deployed and QA'd — all verified working.

---

## 9. CURRENT STATUS

| Item | Status |
|------|--------|
| Phase 1 research | ✅ COMPLETE |
| Phase 2 brief orientation | ✅ COMPLETE |
| L1 geometric detection | ✅ LOCKED |
| Native multi-TF pipeline | ✅ COMPLETE |
| Visual Bible v2 (6 charts) | ✅ DEPLOYED |
| Advisor YAML export v3 | ✅ COMPLETE |
| L1.5 threshold calibration | ⏳ NEXT — awaiting Olya's review |
| L2 strategy layer | 🔮 FUTURE — Olya's domain |

---

## 10. WHAT HAPPENS NEXT

1. **Olya reviews the Visual Bible** at the deployed URL, toggling thresholds and timeframes
2. **Craig + Olya report back** with calibration findings:
   - Which threshold values look right for each primitive on 5m and 15m
   - Any detection bugs (false positives, missed events)
   - Any visual/UX issues in the charts
3. **We iterate** on L1.5 thresholds based on their feedback
4. **Lock L1.5** once Olya approves threshold values
5. **L2 strategy interpretation** is Olya's domain — we provide tools, she provides meaning

---

## 11. OPERATING RULES FOR FUTURE SESSIONS

- **QUALITY > SPEED** — take time, do it properly
- **DO NOT INVENT** — research what EXISTS in production algo trading
- **CITE EVERYTHING** — no unsourced claims about "standard"
- **INV-OLYA-ABSOLUTE** — Olya's word overrides all advisors on methodology
- **NY TIME** everywhere — never UTC in user-facing output
- **Native per-TF** — never project 1m detections to higher timeframes
- **If no consensus exists** on a definition, label as VARIANT and list all variants with tradeoffs
- Craig's email: craig@imoon.ai

---

*Last updated: 2026-03-04 ~15:30 NY by Perplexity Computer*
