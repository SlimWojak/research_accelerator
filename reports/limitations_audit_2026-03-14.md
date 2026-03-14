# Limitations Audit — a8ra Research Accelerator
## Date: 2026-03-14
## Scope: Full tool ecosystem (Phases 1–5), deployment, data coverage

---

## 1. Feature Completeness

### Phase 1: Detection Engine — FULLY WORKING

| Item | Status | Notes |
|------|--------|-------|
| 12 PrimitiveDetector modules | WORKING | All 13/13 LOCKED (EqualHL deferred) |
| CascadeEngine with topological sort | WORKING | 14-node dependency graph |
| Config validation (Pydantic v2) | WORKING | `extra='forbid'` catches typos |
| 378 detector unit tests | WORKING | All passing |

**No gaps found.**

### Phase 2: Evaluation Engine — FULLY WORKING

| Item | Status | Notes |
|------|--------|-------|
| Parameter sweep (1D/2D grid) | WORKING | |
| Walk-forward validation | WORKING | 25-week stability report generated |
| Comparison stats (Jaccard, deltas) | WORKING | |
| Cascade funnel stats | WORKING | |
| JSON schemas 4A–4E | WORKING | |
| 253 evaluation tests | WORKING | All passing |

**No gaps found.**

### Phase 3: Comparison Interface (compare.html) — PARTIALLY WORKING

| Item | Status | Severity | Notes |
|------|--------|----------|-------|
| Chart tab with multi-config overlay | WORKING | — | |
| Stats tab (Plotly bar charts, funnel) | WORKING | — | |
| Heatmap tab (2D/1D sweep) | WORKING | — | |
| Walk-forward tab | WORKING | — | |
| Divergence navigator | WORKING | — | |
| Ground truth annotation | WORKING | — | localStorage only, no disk persistence |
| Lock panel | WORKING | — | |
| **HTF support (1H/4H/1D chart rendering)** | **MISSING** | LIMITING | compare.html has no TF selector — renders whatever TF the evaluation fixture was generated for. Cannot switch TFs in the UI. Calibration pages have full HTF support but compare.html does not. |
| **Multi-pair comparison** | **MISSING** | LIMITING | Hardcoded to EURUSD. No pair selector in UI, no cross-pair comparison fixtures. |

### Phase 3.5: Validation Mode (validate.html) — FULLY WORKING with GAPS

| Item | Status | Severity | Notes |
|------|--------|----------|-------|
| Week picker (25 weeks) | WORKING | — | |
| Chart with detection markers | WORKING | — | |
| Day tabs + TF buttons (1m/5m/15m) | WORKING | — | |
| Ground truth labeling (disk-persisted) | WORKING | — | |
| Lock panel (disk-persisted) | WORKING | — | |
| Session bands | WORKING | — | |
| Primitive toggles | WORKING | — | |
| **HTF support (1H/4H/1D)** | **MISSING** | LIMITING | TF selector only offers 1m/5m/15m (`V_TF_OPTIONS`). Detection data includes HTF detections in `detections_by_primitive[prim]['global']` but the UI cannot render HTF candles or select HTF views. Calibration pages have this; validate.html does not. |
| **Enriched detection display** | **NOT EXPOSED** | COSMETIC | Enriched fields (tags, upstream_refs, full properties) are in the JSON but validate.html displays only the slim view. Not a functional gap — validate.html doesn't need enrichment — but if a user clicks a detection marker, the detail popover shows limited info. |

### Phase 4: Variant Comparison + GT Scoring + Search — FULLY WORKING

| Item | Status | Severity | Notes |
|------|--------|----------|-------|
| LuxAlgo MSS/OB variants | WORKING | — | |
| Ground truth scoring (P/R/F1) | WORKING | — | |
| Parameter search (perturbation) | WORKING | — | |
| Winner export | WORKING | — | |
| 65 validation assertions | WORKING | — | |

**No gaps found.**

### Phase 5: Strategy Designer (strategy.html) — FULLY WORKING with KNOWN DEFERRALS

| Item | Status | Severity | Notes |
|------|--------|----------|-------|
| Chain composer (direction, steps, gates) | WORKING | — | 11 LOCKED L1 primitives |
| Evaluator engine | WORKING | — | Direction/constraint/timing matching, FULL_MATCH/NEAR_MISS |
| Chart overlays (green/amber bands) | WORKING | — | |
| Drill-down panel | WORKING | — | Per-step PASS/FAIL with detection properties |
| Convergence funnel | WORKING | — | Step-by-step attrition counts |
| Template persistence | WORKING | — | Save/load via serve.py |
| **Cross-TF chains** | **DEFERRED** | DEFERRED | Schema supports per-step `tf` field. UI uses single global TF (5m/15m). Documented in locked brief. |
| **Replay mode** | **DEFERRED** | DEFERRED | Step through matches bar-by-bar. Documented in locked brief. |
| **Advanced constraint editing** | **DEFERRED** | DEFERRED | Smart defaults shown, "Advanced" expandable section exists but only shows placeholder text. User cannot edit constraints beyond smart defaults. |
| **Convergence stats export** | **DEFERRED** | DEFERRED | Funnel visible in UI, no export to file. |
| **Stale TODO comment** | **—** | COSMETIC | `strategy-chart.js:383` has leftover `// TODO: Task 6 will implement chain highlight overlay rendering here` — the feature IS implemented, the comment is stale. |

### Calibration Visual Bible (6 chart pages) — FULLY WORKING

| Item | Status | Severity | Notes |
|------|--------|----------|-------|
| FVG, Swings, Displacement, OB, NY Windows, Asia Range | WORKING | — | All have TF selectors including HTF |
| HTF Liquidity page | WORKING | — | |
| **Data scope: Jan 2024 week only** | **—** | LIMITING | All 6 calibration pages are hardcoded to the Jan 8–12, 2024 EURUSD week. No week picker, no date range selector. Adding a new week requires regenerating all `*_data_*.json` files. |
| **Oct 2025 candle files** | **PRESENT** | — | `candles_2025-09-29.json` through `candles_2025-10-03.json` exist in site/ but no calibration chart page loads them. HTF page has hardcoded Jan 2024 day tabs. |

---

## 2. Cross-TF Limitations

| Tool | LTF (1m/5m/15m) | HTF (1H/4H/1D) | Notes |
|------|-----------------|-----------------|-------|
| **Calibration pages** (6 charts) | 1m, 5m, 15m | 1H, 4H, 1D | Full TF switching via buttons. HTF data files present for all 6 pages. |
| **HTF Liquidity page** | 5m base chart | 1H, 4H, 1D, W1, MN overlays | Dedicated HTF tool with multi-TF overlay. |
| **compare.html** | Whatever TF the fixture uses | **NOT SUPPORTED** | No TF selector in compare.html UI. TF is baked into the evaluation fixture at generation time. Rendering is fixed to the fixture's TF. |
| **validate.html** | 1m, 5m, 15m | **NOT SUPPORTED** | `V_TF_OPTIONS` hardcoded to `['1m', '5m', '15m']`. Detection data includes HTF detections (via `'global'` key) but cannot render HTF candles. |
| **strategy.html** | 5m, 15m | **NOT SUPPORTED** | Execution TFs only, by design. Cross-TF deferred. |
| **detect.py** | 1m, 5m, 15m | **PARTIAL** | Engine runs all TFs natively. `detect.py` outputs detections per TF including HTF primitives (tagged as `global`). Candle data generation only writes LTF candles per day. No HTF candle files in `site/data/candles/`. |

**Summary**: Calibration pages have full HTF support. validate.html, compare.html, and strategy.html do not. The detection engine runs all TFs — the gap is purely in the frontend rendering.

---

## 3. Data Coverage

### Time Periods

| Dataset | Period | Weeks | Detections | Pair | Used By |
|---------|--------|-------|------------|------|---------|
| Calibration data | Jan 8–12, 2024 | 1 week | ~5,000 | EURUSD | 6 calibration chart pages, compare.html fixtures |
| Walk-forward data | Sep 2025 – Feb 2026 | 25 weeks | 100,481 | EURUSD | validate.html, strategy.html |
| Enriched detection data | Sep 2025 – Feb 2026 | 25 weeks | 100,481 | EURUSD | strategy.html (full properties, tags, upstream_refs) |

### Pair Coverage

| Pair | River Data | Detection Data | Frontend Support |
|------|-----------|---------------|-----------------|
| EURUSD | Available (Phoenix River) | Generated (25 weeks) | All tools |
| GBPUSD | Available (Phoenix River) | **NOT GENERATED** | **NONE** |
| USDJPY | Available (Phoenix River) | **NOT GENERATED** | **NONE** |
| AUDUSD | Available (Phoenix River) | **NOT GENERATED** | **NONE** |
| NZDUSD | Available (Phoenix River) | **NOT GENERATED** | **NONE** |
| USDCAD | Available (Phoenix River) | **NOT GENERATED** | **NONE** |

### What's Needed to Extend Coverage

| Extension | Effort | What to Do |
|-----------|--------|------------|
| **Add a new week (EURUSD)** | LOW | Run `detect.py --full --start <date> --end <date>` — automatic. weeks.json updates, tools pick it up. |
| **Add a new pair** | MEDIUM | Change `detect.py` hardcoded `"EURUSD"` to accept `--pair` flag. Regenerate all week files. Frontend tools are pair-agnostic (no pair-specific logic) but metadata displays would need updating. |
| **Add calibration data for Oct 2025** | MEDIUM | Oct 2025 candle files exist in `site/` but calibration pages are hardcoded to Jan 2024 dates. Would need to modify each `.html` page's day tabs and data file references, or build a week-picker for calibration pages. |
| **Extend date range beyond Feb 2026** | LOW | Just run `detect.py` with new dates. Requires Phoenix River data to be available for those dates. |

---

## 4. Deployment

### Current State

| Deployment | URL | What Works | What Doesn't |
|------------|-----|------------|--------------|
| **localhost:8100** | `python3 -m http.server 8100 -d site` | compare.html, calibration pages | No write endpoints — GT labels go to localStorage only |
| **localhost:8200** | `python3 site/serve.py` | validate.html, strategy.html, all calibration pages | Full functionality including label/strategy persistence |
| **GitHub Pages** | `slimwojak.github.io/ra-tools/` | validate.html (read-only), compare.html, calibration pages | **No strategy.html** (not deployed), **no label persistence** (no server), **no strategy persistence** |

### Gap: GitHub Pages → Full Remote Access

| Gap | Severity | Description |
|-----|----------|-------------|
| **strategy.html not deployed** | BLOCKING | ra-tools repo on GitHub Pages doesn't have strategy.html or the 4 strategy-*.js modules. Would need to be added and pushed. |
| **No server for persistence** | BLOCKING | GitHub Pages is static-only. Template save/load, GT label persistence, and lock-record persistence all require serve.py POST endpoints. These features silently fail on static hosting. |
| **Enriched detection data not deployed** | BLOCKING | ra-tools has detection data but it's the slim format (pre-`--full`). Strategy Designer needs enriched data. Would need to regenerate with `--full` and push ~150MB of JSON to the GitHub Pages repo. |
| **Data size** | LIMITING | 25 weeks of enriched detection data is ~150MB JSON. GitHub Pages has a 1GB repo size limit but performance degrades with large repos. The candle files add another ~200MB. Total site/data/ could be 400MB+. |
| **Alternative: Cloudflare Workers or similar** | — | A lightweight serverless function could handle POST/GET for strategy templates. Would need ~50 lines of code. Labels and lock-records could use the same approach. |
| **Alternative: Local-only with export** | — | Keep strategy.html as localhost-only. Add "Export Strategy JSON" button that downloads the file. User can share strategies via file transfer. No server dependency. |

### Features That Only Work on Localhost

| Feature | Tool | Reason |
|---------|------|--------|
| GT label persistence (disk) | validate.html | Requires serve.py POST /api/labels/ |
| Lock-record persistence (disk) | validate.html | Requires serve.py POST /api/lock-records/ |
| Strategy template save/load | strategy.html | Requires serve.py POST/GET /api/strategies/ |
| Compare-mode GT labels | compare.html | Uses localStorage (works anywhere) but no cross-device sync |

---

## 5. Code Quality

### Duplicated Code

| Pattern | Instances | Files | Severity |
|---------|-----------|-------|----------|
| `SessionBandsPrimitive` (ISeriesPrimitive 3-class pattern) | 3 copies | `chart-tab.js`, `validate-chart.js`, `strategy-chart.js` | COSMETIC | 
| `toTS()` timestamp converter | 3 copies | `shared.js`, `validate-app.js`, `strategy-app.js` | COSMETIC |
| `findNearestCandleTime()` | 2 variants | `chart-tab.js` (generic), `strategy-chart.js` (strategy-specific) | COSMETIC |

**Recommendation**: Extract shared primitives and utilities into `shared.js` or a new `chart-primitives.js`. Not blocking — each copy works independently and the prefixed names (V-, S-) prevent conflicts.

### Stale Comments / TODO

| File | Line | Content | Severity |
|------|------|---------|----------|
| `strategy-chart.js` | 383 | `// TODO: Task 6 will implement chain highlight overlay rendering here` | COSMETIC — feature IS implemented, comment is stale |
| `strategy-chain.js` | 3 | Header says "evaluator STUB" — evaluator is fully implemented | COSMETIC |

### Orphaned / Unused Files

| File | Status | Notes |
|------|--------|-------|
| `site/candles_2025-09-29.json` through `candles_2025-10-03.json` | ORPHANED | Oct 2025 candle files in site/ root — no calibration page loads them. Were generated for HTF calibration work but the HTF page uses Jan 2024 data. Not harmful (16KB–380KB each). |
| `site/data/params/` | EMPTY | Directory exists, no files. Was presumably intended for parameter snapshot storage. |
| `site/data/labels/` | NEAR-EMPTY | Directory exists with no label files — no GT labeling has been done in validation mode yet. |
| `site/data/lock-records/` | NEAR-EMPTY | Same — no lock records saved yet. |
| `site/__pycache__/` | GENERATED | Python bytecache from running detect.py. Should be in .gitignore. |

### Dead Code

No significant dead code found. The LuxAlgo variant detectors (`luxalgo_mss.py`, `luxalgo_ob.py`) are active and tested — they're variant implementations, not dead code.

### Technical Debt Summary

| Item | Severity | Impact |
|------|----------|--------|
| 3× SessionBandsPrimitive copies | COSMETIC | No functional impact. Maintenance burden if the primitive API changes. |
| 3× toTS() copies | COSMETIC | Any timestamp bug must be fixed in 3 places. |
| No .gitignore for `__pycache__` in site/ | COSMETIC | Bytecache files could accidentally be committed. |
| detect.py hardcodes "EURUSD" | LIMITING | Must modify source code to run on other pairs. Should accept `--pair` flag. |
| Calibration pages hardcode Jan 2024 dates | LIMITING | Cannot view other weeks without modifying HTML source. |
| compare.html has no TF selector | LIMITING | TF is baked into fixture at generation time. |

---

## Summary by Severity

| Severity | Count | Key Items |
|----------|-------|-----------|
| **BLOCKING** (prevents core workflow) | 3 | strategy.html not on GitHub Pages, no server for persistence on static hosting, enriched data not deployed |
| **LIMITING** (works but constrained) | 6 | No HTF in validate/compare/strategy, single pair (EURUSD), calibration pages locked to Jan 2024, compare.html no TF selector |
| **COSMETIC** (annoying but not functional) | 6 | Duplicated SessionBandsPrimitive/toTS, stale TODO comments, orphaned candle files, empty directories |
| **DEFERRED** (known, intentionally postponed) | 4 | Cross-TF chains, replay mode, advanced constraint editing, convergence stats export |

---

*Audit performed: 2026-03-14. Repos scanned: research_accelerator (primary), ra-tools (deployment), phoenix-swarm (methodology specs).*
