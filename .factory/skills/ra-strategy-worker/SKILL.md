---
name: ra-strategy-worker
description: Builds Phase 5 Strategy Designer features (detection enrichment, UI, chain evaluator, chart rendering, template persistence)
---

# RA Strategy Worker

## When to Use This Skill

Use for Strategy Designer features: detection data enrichment (detect.py --full), strategy.html page and JS modules, chain builder UI, chain evaluator engine, chart rendering overlays, template save/load, and serve.py extensions.

## Reference Documents

Read these based on what your feature needs:
- `STRATEGY_DESIGNER_LOCKED_BRIEF.md` — Full locked architecture. ALWAYS read relevant sections.
- `PROJECT_STATE.md` — Project context, detector inventory, file manifest.
- `site/js/validate-app.js` — Reference for state management, data loading patterns.
- `site/js/validate-chart.js` — Reference for chart creation, marker building, session bands.
- `site/js/validate-gt.js` — Reference for right sidebar panel pattern (drill-down).
- `site/js/shared.js` — Shared utilities (toTS, color palettes, Plotly dark theme).
- `site/detect.py` — Detection batch generator (modify for --full flag).
- `src/ra/engine/base.py` — Detection/DetectionResult dataclasses, field inventory.

## Technology Stack

- **Python 3.12** — pandas, duckdb, pydantic v2, pyyaml
- **Price charts:** TradingView Lightweight Charts v4.1.3 (CDN, global `LightweightCharts`)
- **Stats charts:** Plotly.js 2.35.2 (CDN, global `Plotly`)
- **Styling:** Vanilla CSS with dark theme design tokens
- **No build system.** Plain HTML/JS/CSS.

## Work Procedure

### Step 1: Understand the Feature

Read the feature description. Identify:
- Which files to create or modify
- What detection data fields are consumed
- What user interactions are required
- Dependencies on prior features

### Step 2: Read Current State

Read files you'll modify or that provide patterns:
- For detection enrichment: `site/detect.py`, `src/ra/engine/base.py`
- For UI work: `site/strategy.html` (if exists), JS modules
- For chart work: `site/js/validate-chart.js` for LWC patterns
- For template persistence: `site/serve.py`

### Step 3: Implement

Follow these conventions:

**For detect.py enrichment:**
- Add `--full` CLI argument (argparse)
- When `--full`, skip `slim_detection()` — serialize full Detection fields
- Preserve all `properties`, `tags`, `upstream_refs`
- Write to same `site/data/detections/` directory
- validate.html ignores extra fields — do NOT break existing format

**For strategy.html page:**
- Follow validate.html structure as template
- Global state object: `sApp = { ... }` (prefix 's' for strategy)
- Load data from `site/data/` (same candles, sessions, enriched detections)
- Dark theme: bg #0a0e17, surface #131722, border #2a2e39, text #d1d4dc
- Font: IBM Plex Mono, 11px labels, 13px body

**For chain builder UI:**
- Left panel, vertical step list
- Direction selector (Bull/Bear) at top — prominent, first-class
- Step cards: primitive dropdown, smart defaults shown, advanced expandable
- Gates section below steps
- Template controls at bottom
- No drag-and-drop. Sequential add. Reorder via arrows.

**For chain evaluator (strategy-chain.js):**
- Pre-index detections by (forex_day, kill_zone) on data load
- Walk chain steps sequentially, accumulate chain_context
- Support timing modes: same_bar, same_kill_zone, same_session, same_day, within_bars_N
- Spatial constraints: in_ote_zone checks price overlap using chain context
- Return ChainMatch[] with: status (FULL/NEAR_MISS), steps[], failed_step, diagnostic
- Near-miss = N-1 of N steps matched. Record which step failed and why.

**For chart rendering:**
- Chain highlight overlay: ISeriesPrimitive (green/amber bands)
- Numbered step markers on match selection
- Drill-down panel: right sidebar, 400px, slide-in

**For template persistence:**
- POST /api/strategies endpoint in serve.py
- GET /api/strategies for list
- Storage: site/data/strategies/{name}.json
- Schema version 1.0 per locked brief

### Step 4: Verify

**Python changes:** Run the modified script and verify output.
```bash
cd /Users/echopeso/research_accelerator
python3 site/detect.py --full --start 2025-09-01 --end 2025-09-07 \
    --config configs/locked_baseline.yaml --output site/data/
```

**Frontend changes:** Use agent-browser for visual verification.
```bash
cd /Users/echopeso/research_accelerator && python3 site/serve.py &
sleep 2
```
Navigate to http://localhost:8200/strategy.html, take screenshots, check console.

Always stop server after:
```bash
lsof -ti :8200 | xargs kill 2>/dev/null || true
```

### Step 5: Commit

Commit with descriptive message. Do NOT modify locked primitives or vLOCK.yaml.

## Smart Defaults Per Primitive

When building the chain builder, these are the default constraints per primitive:

| Primitive | Defaults |
|---|---|
| liquidity_sweep | qualified_sweep: true |
| mss | break_type: REVERSAL, displacement_grade_min: VALID |
| displacement | quality_grade_min: VALID |
| fvg | state: ACTIVE |
| order_block | state: ACTIVE, zone_type: body |
| ote | fib_range: [0.618, 0.79] |
| session_liquidity | classification: CONSOLIDATION_BOX |
| asia_range | tier: [tight, mid] |
| htf_eqh_eql | status: UNTOUCHED, min_touches: 2 |
| kill_zone | window: [lokz, nyokz] |
| reference_levels | (no filter) |

## Primitive Palette (LOCKED L1 only)

Only these appear in the chain builder dropdown:
- Liquidity Sweep, MSS, Displacement, FVG (+IFVG, BPR), Order Block
- OTE Zone, Session Liquidity, Asia Range, HTF EQH/EQL
- Kill Zone Window, Reference Levels

NOT included: Equal HL (DEFERRED), P/D standalone, Window B.

## When to Return to Orchestrator

- Detection engine output format has changed unexpectedly
- serve.py modifications break existing validate.html label persistence
- Chain evaluator logic requires architectural decisions not in the locked brief
- Cross-TF chain evaluation needed (deferred to Phase 2)
- Feature requires modifying locked primitive detection logic
