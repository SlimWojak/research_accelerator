# a8ra Calibration Visual Bible

Interactive threshold calibration tool for ICT trading primitives detection. Built for Olya's visual review of L1.5 parameter tuning on EURUSD data.

## Quick Start

```bash
# Open locally — no server needed
open site/index.html
# or
python -m http.server 8000 --directory site
# then visit http://localhost:8000
```

## Repo Structure

```
├── site/                          # Self-contained static site (deploy anywhere)
│   ├── index.html                 # Landing page → links to all 6 chart pages
│   ├── fvg.html                   # Fair Value Gap — threshold slider + CE/boundary markers
│   ├── swings.html                # Swing Points — N-parameter slider
│   ├── displacement.html          # Displacement — ATR multiplier slider
│   ├── ob-staleness.html          # Order Blocks — staleness/retest tracking
│   ├── ny-windows.html            # NY Reversal Windows A & B
│   ├── asia.html                  # Asia Range — high/low/midline + deviations
│   ├── *_data_{1m,5m,15m}.json   # Per-TF detection results
│   ├── candles_2024-01-*.json     # Per-day candle data (NY timestamps)
│   ├── session_boundaries.json    # Session band coordinates
│   ├── calibration_data_export.yaml  # Full advisor export (294KB)
│   └── BUILDSPEC.md               # Design tokens & technical spec
│
├── pipeline/                      # Data processing scripts
│   ├── preprocess_data_v2.py      # Main pipeline: 1m CSV → aggregated TFs → all detections → JSON
│   └── generate_advisor_export_v3.py  # Generates YAML export for advisor panel
│
├── data/                          # Source data
│   └── eurusd_1m_2024-01-07_to_2024-01-12.csv  # 7,177 bars of real EURUSD 1m
│
├── research/                      # Phase 1 research archive
│   ├── ICT_PRIMITIVES_RESEARCH_PACK.md  # Master synthesis (813 lines)
│   ├── PERPLEXITY_BRIEF_ICT_PRIMITIVES.md
│   ├── PERPLEXITY_PHASE2_BRIEF.md
│   └── research_*.md              # Individual research deep-dives
│
├── PROJECT_STATE.md               # Full project checkpoint & orientation
├── SYNTHETIC_OLYA_METHOD_v0.4.yaml  # Source methodology (806 lines)
└── CHART_REBUILD_SPEC.md          # Spec for chart construction
```

## Regenerating Data

When you modify detection logic or thresholds in the pipeline:

```bash
# 1. Edit pipeline/preprocess_data_v2.py (tweak thresholds, logic)
# 2. Run pipeline (outputs JSON into site/)
cd pipeline
python preprocess_data_v2.py

# 3. Regenerate advisor YAML (optional)
python generate_advisor_export_v3.py

# 4. Open site/index.html — charts pick up new data automatically
```

> **Note**: Pipeline scripts expect source CSV at `../data/eurusd_1m_2024-01-07_to_2024-01-12.csv` and output to `../site/`. Adjust paths in the scripts if your layout differs.

## Technical Details

- **Charts**: TradingView Lightweight Charts v4 (loaded from CDN)
- **Detection**: Native per-timeframe (1m, 5m, 15m) — NOT projected from 1m
- **Timestamps**: All NY time (EST = UTC-5 for Jan 2024 data)
- **Forex day boundary**: 17:00 NY
- **Sessions**: Asia 19:00-00:00, LOKZ 02:00-05:00, NYOKZ 07:00-10:00 (NY)
- **No build step** — pure HTML/JS/JSON, open in any browser

## Architecture Context

See `PROJECT_STATE.md` for full project context including:
- Three-layer architecture (L1 geometric → L1.5 thresholds → L2 strategy)
- All locked decisions
- Team roles and operating rules
- Detection counts per timeframe
