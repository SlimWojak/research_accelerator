# MIRROR_RECON — Cross-Repo Feature Audit
## RA → MIRROR Gap Analysis for TradingView-Grade Hardening

**Generated**: 2026-03-24  
**Repos scanned**: `research_accelerator/mirror/`, `research_accelerator/site/`, `research_accelerator/src/ra/`, `dexter/`  
**Exit gate**: Every issue has RA solution (file:line), MIRROR gap (file:line), Dexter data fields, and implementation notes.

---

## §1 — ARCHITECTURE COMPARISON

| Dimension | RA (Calibration Tool) | MIRROR (Live Dashboard) |
|---|---|---|
| **Backend** | `site/serve.py` — static file server; pre-generated JSON fixtures (`candles_*.json`, `*_data_*.json`, `session_boundaries.json`) | `mirror/backend/server.py` — FastAPI + WebSocket; reads River parquets live via `RiverBarAdapter`; watchdog on staging JSONL + detection JSON |
| **Frontend** | `site/js/shared.js` + `chart-tab.js` + `strategy-chart.js` — multi-page SPA with tabs (Chart, Stats, Heatmap, Walk-Forward) | `mirror/js/mirror-app.js` + `mirror-chart.js` + `mirror-feed.js` — single-page live dashboard |
| **Chart library** | Lightweight Charts v4.1.3 | Lightweight Charts v4.1.3 (same) |
| **Data source** | Pre-exported JSON per-week (`data/candles/{week}.json`, `data/detections/{week}.json`, `data/sessions/{week}.json`); week manifest `data/weeks.json` | Live: River parquets via `RiverBarAdapter` → `tf_aggregator.aggregate()`. Detections: `~/dexter/output/detections/{date}.json` written by `detection_runner.py` |
| **Session data** | Pre-computed `session_boundaries.json` with canonical fields: `session`, `forex_day`, `start_time`, `end_time`, `color`, `border` | Hardcoded fallback session defs in `mirror-chart.js:630-660`; no backend session endpoint |
| **Detection model** | Schema 4A envelope: `{per_config: {config: {per_primitive: {prim: {per_tf: {tf: {detections: [...]}}}}}}}`; also flat `detections_by_primitive` for week mode | Flat `{detections_by_primitive: {prim: {tf: [...]}}}` from Dexter daily export |
| **State display** | Minimal (no WorldState display in RA) | WorldState banner in HTML (`#worldstate-banner`); fields: PHASE, PERM, AUTH, DIR, MECH |
| **Navigation** | Week picker dropdown + day tabs + TF buttons; HTF loads all weeks merged | Date picker (`<input type="date">`) + NOW button; TF buttons; no day tabs or week navigation |
| **Deployment** | Local dev server (`python serve.py`) | M3 Ultra, Cloudflare Tunnel → `mirror.a8ra.com`; `start-mirror.sh` (server + detection runner) |

### Key Architectural Difference
RA uses **pre-generated JSON fixtures** — all data is materialized ahead of time, enabling instant week/day switching. MIRROR reads **live parquets** — more flexible but requires thoughtful caching and range-query APIs to match RA's navigation fluidity.

---

## §2 — ISSUE-BY-ISSUE GAP TABLE

### ISSUE 1: Session Shading

**Symptom**: Sessions start at inconsistent/wrong times on MIRROR. Shading differs across timeframes. Not canonical.

| Aspect | Detail |
|---|---|
| **RA implementation** | `src/ra/data/session_tagger.py:30-58` — canonical session boundaries: Asia 19:00-00:00, Pre-London 00:00-02:00, LOKZ 02:00-05:00, Pre-NY 05:00-07:00, NYOKZ 07:00-10:00, Other 10:00-19:00. All NY time. Forex day boundary: 17:00 NY (`session_tagger.py:79-83`). Pre-computed `session_boundaries.json` served to frontend. `site/js/chart-tab.js:573-595` — `getSessionBandsForDay()` reads session data, filters to `{asia, lokz, nyokz}`, applies HTF opacity reduction via regex on alpha channel. Uses `toTS(b.start_time)` / `toTS(b.end_time)` for precision. |
| **MIRROR current state** | `mirror/js/mirror-chart.js:630-660` — **hardcoded fallback** session defs (`_M_SESSION_DEFS`): Asia startH=19 endH=0, LOKZ startH=2 endH=5, NYOKZ startH=7 endH=10. Computes bands from forex day string using manual date math (`mirror-chart.js:665-710`). Has `mApp.sessionData` path for backend-provided sessions, but **backend never sends session data** — no `/api/sessions` endpoint, no WebSocket `type: "sessions"` message. HTF opacity reduction exists (`mirror-chart.js:688-691`) but applied to the hardcoded fallback, which has imprecise time computation. |
| **Dexter data** | `dexter/bead_field/producers/session_boundary.py:30-36` — `_BOX_WINDOWS_NY`: ASIA_BOX (19,0), PRE_LONDON_BOX (0,2), PRE_NY_BOX (5,7). Reference levels: LONDON (2,5), NY (7,10). Kill zone hours match RA's `session_tagger.py`. The `daily_detection_export.py` includes `session_boundary` claims in the per-day JSON, but these are box classifications (CONSOLIDATION_BOX / TREND_OR_EXPANSION), not display-ready session band data. |
| **Gap** | MIRROR lacks a backend session-band endpoint. Frontend falls back to hardcoded computation which doesn't account for DST transitions or precise bar-time boundaries. No `session_boundaries.json` equivalent. |
| **Implementation notes** | 1. Add `/api/sessions/{forex_day}` endpoint to `server.py` that computes session bands using the same logic as RA's `session_tagger.py` (or Dexter's `session_boundary.py` windows). Return `[{session, forex_day, start_time, end_time, color, border}]`. 2. Push session data over WebSocket on initial connect and day change. 3. Frontend `getMirrorSessionBands()` already has the `mApp.sessionData` path — just needs data. 4. For DST correctness, compute in Python using `zoneinfo`, not JS date math. |
| **Effort** | **S** — Backend endpoint + WebSocket push. Frontend path already exists. |

---

### ISSUE 2: Primitive Signals Per Timeframe

**Symptom**: Primitives only appear on 5m/15m. Should render on ALL timeframes with signals native to that TF.

| Aspect | Detail |
|---|---|
| **RA implementation** | `site/js/shared.js:97-136` — `derivePrimitivesFromData()` scans all TFs in `per_config.per_primitive.per_tf` and adds primitives that have detections on any TF in `{1m, 5m, 15m, 1H, 4H}`. `site/js/chart-tab.js:147-248` — `buildMarkers()` reads `tfData = primData.per_tf[app.tf]` — each TF gets its own detection array, so markers are always native to the displayed TF. Week mode: `buildWeekModeMarkers()` reads `byTf[app.tf]` from `detections_by_primitive`. |
| **MIRROR current state** | `mirror/js/mirror-chart.js:505-545` — `buildMirrorMarkers()` reads `byTf[mApp.tf] || byTf['global']`. The fallback to `'global'` means if Dexter only exported detections under `5m` and `15m` keys (no `1H`/`4H`/`1D` keys), those TFs show nothing. `mirror/js/mirror-app.js:206-225` — WS `bars` handler stores per-TF candle data, but detection data is a single blob — not re-fetched per TF. |
| **Dexter data** | `daily_detection_export.py:367-379` — `_build_export()` groups claims by `source_timeframe` from `reasoning_trace`. LTF producers (FVG, MSS, swing, etc.) tag `source_timeframe: "5m"` or `"15m"`. HTF producers (`htf_producers.py`) tag `"1H"`, `"4H"`, `"1D"`. So the detection JSON **does** include per-TF keys for HTF primitives. The issue is: HTF producers only emit `swing_point`, `fvg`, `displacement`, `mss` (4 types), while LTF has 9+ types. Session boundary, liquidity sweep, order block, OTE, asia range are LTF-only. |
| **Gap** | Two sub-gaps: (a) MIRROR doesn't re-fetch detections when switching TF — it uses the initial detection blob which may have been loaded for a different date. (b) Dexter only runs HTF versions of 4 primitives — sweep, OB, OTE, session boundary have no HTF equivalents. This is a pipeline limitation, not a MIRROR bug. |
| **Implementation notes** | 1. **Frontend**: When TF changes, MIRROR already fetches bars via REST (`mirror-app.js:346-370`). Add detection re-fetch for the new date too — or ensure the single detection JSON contains all TF keys (it already does from Dexter). The `byTf[mApp.tf] || byTf['global']` fallback already handles this correctly. 2. **Verify**: Load a detection JSON and confirm it has `1H`/`4H` keys — if Dexter's HTF producers are running, these should exist. 3. **Marker tolerance**: `findMirrorNearestCandleTime()` at `mirror-chart.js:797-830` already has TF-aware tolerance (`htf ? 14400 : 3600`). 4. For 1D specifically: detections may need wider time tolerance since daily bars span 24h. RA uses `maxDiff = 86400` for 1D (`chart-tab.js:155`), MIRROR doesn't handle 1D specifically — add this case. |
| **Effort** | **S** — Mostly verification + 1D tolerance fix. If HTF detection gaps are real, that's a Dexter pipeline enhancement (M). |

---

### ISSUE 3: Signal Tooltips

**Symptom**: Hovering over markers doesn't show what they are. Hard to distinguish FVG from swing point from displacement.

| Aspect | Detail |
|---|---|
| **RA implementation** | `site/js/strategy-chart.js:421-478` — `subscribeCrosshairMove()` tooltip. On crosshair move, finds markers at `param.time`, builds HTML with: primitive label (colored), direction, time, price, and **primitive-specific properties** (MSS: break_type + displacement grade; sweep: level + breach_pips + qualified; FVG: range; displacement: grade + ATR mult; OB: zone; OTE: fib levels). Tooltip is a `div.chart-tooltip` appended to chart container, positioned at `param.point.x + 16, param.point.y + 16`. **RA markers carry `_det` reference** to the full detection object — this is what enables rich tooltips. |
| **MIRROR current state** | `mirror/js/mirror-chart.js:586-672` — MIRROR has tooltips, but **only for DIAGNOSTIC_SIGNAL markers** (the gold diamond ◆). Implemented via `chart.subscribeClick()` (click, not hover). Shows five-factor breakdown (mss, sweep, fvg_ob, ote, session scores). Regular primitive markers (FVG, MSS, etc.) have **no tooltip at all** — `text: ''` in marker construction (`mirror-chart.js:536`). No `_det` reference stored on regular markers. |
| **Dexter data** | Detection JSON contains full `properties` dict per detection (e.g., `break_type`, `zone_body`, `quality_grade`, `breach_pips`). The data is available — MIRROR just doesn't read it for tooltips. |
| **Gap** | Regular primitive markers lack: (a) `_det` property pointing to the source detection, (b) crosshair-move tooltip handler, (c) primitive-specific property formatting. Only DIAGNOSTIC_SIGNAL has click tooltip. |
| **Implementation notes** | 1. In `buildMirrorMarkers()` (`mirror-chart.js:505`), add `_det: det` to each marker object (RA pattern from `strategy-chart.js:555`). 2. Add `chart.subscribeCrosshairMove()` handler to `createMirrorChart()` that: finds markers at `param.time`, reads `_det`, builds HTML per primitive type. 3. Port the property extraction logic from `strategy-chart.js:440-475` (MSS → break_type, FVG → range, displacement → grade, etc.). 4. Style tooltip identically to existing signal tooltip (`#1e222d` bg, border matching primitive color, `IBM Plex Mono` 11px). 5. Keep existing click tooltip for DIAGNOSTIC_SIGNAL — hover tooltip for primitives, click tooltip for signals. |
| **Effort** | **S** — Pattern exists in RA strategy-chart.js, port directly. |

---

### ISSUE 4: Date Scrolling / Navigation

**Symptom**: MIRROR locked to latest week on all TFs. 4H/1D should scroll across months. RA has week picker and scrollable nav.

| Aspect | Detail |
|---|---|
| **RA implementation** | `site/js/shared.js:760-885` — **Week picker** dropdown populated from `data/weeks.json` manifest. `onCompareWeekSelect()` loads `data/candles/{week}.json`, `data/detections/{week}.json`, `data/sessions/{week}.json`. For HTF (1H/4H/1D), `loadAllWeeksHTF_compare()` merges ALL weeks into one continuous timeline — lazy loads all manifested weeks in parallel. **Day tabs**: `chart-tab.js:834-860` — day navigation buttons per forex day; click scrolls chart to `cDayRange(dayStr)`. HTF shows "All" tab for full week view. Scroll sync: `chart.timeScale().subscribeVisibleTimeRangeChange()` updates active day tab as user scrolls. |
| **MIRROR current state** | `mirror/mirror.html:722-726` — HTML `<input type="date">` picker + "NOW" button. `mirror-app.js:260-290` — `switchToHistorical(dateStr)` disconnects WS, calls `loadHistoricalDate()` which fetches **single-day** bars and detections via REST. `mirror-app.js:328-370` — TF switch fetches bars for HTF via `/api/bars-range?start=...&end=...&tf=...` with a **hardcoded 10-day lookback** (`startD.setUTCDate(startD.getUTCDate() - 9)`). No week picker. No day tabs. No scroll-to-day. No "All weeks" merge for HTF. |
| **Backend API** | `server.py:399-415` — `/api/bars-range` endpoint exists and supports arbitrary date ranges. `/api/dates` returns available detection dates. These APIs are sufficient for expanded navigation — the limitation is frontend-only. |
| **Gap** | (a) No week-level navigation (only single-date picker). (b) HTF hardcoded to 10-day lookback — should be expandable. (c) No day tabs for intra-week navigation. (d) No scroll sync to update active day. |
| **Implementation notes** | 1. **Week picker**: Add `<select id="week-picker">` to header. Backend: add `/api/weeks` endpoint that returns available date ranges (scan detection files, group into Mon-Fri forex weeks). Frontend: on select, load bars + detections for the full week range via existing `/api/bars-range` + per-day detection fetches. 2. **Day tabs**: Add day-tab bar below controls. Derive forex days from loaded bar data using `getForexDay()`. On click, scroll chart via `chart.timeScale().setVisibleRange(dayRange)`. 3. **HTF extended range**: For 4H/1D, load 30-60 days via `/api/bars-range` instead of 10. Consider paginated/chunked loading for very large ranges. 4. **Scroll sync**: Subscribe to `visibleTimeRangeChange`, compute center timestamp, map to forex day, highlight corresponding day tab — RA pattern from `chart-tab.js:890-910`. |
| **Effort** | **M** — New UI components (week picker, day tabs), extended data loading. Backend already supports it. |

---

### ISSUE 5: Full History Access

**Symptom**: 4+ years of River parquet data exists but MIRROR only shows latest week. All historical data should be accessible.

| Aspect | Detail |
|---|---|
| **RA implementation** | `src/ra/data/river_adapter.py:163-195` — `available_range(pair)` scans the filesystem to find earliest/latest parquet dates. `load_bars(pair, start_date, end_date)` reads any date range. `load_and_aggregate()` aggregates to any TF. The RA **site** uses pre-exported fixtures, but the **adapter** supports arbitrary ranges. |
| **MIRROR current state** | `server.py:139-168` — `_load_bars_as_dicts()` loads a single forex day. `_load_bars_range()` loads any date range — **no hardcoded limit**. The backend CAN serve full history. The constraint is entirely in the frontend: `mirror-app.js:337-350` only requests 10-day windows for HTF. The `/api/bars-range` endpoint accepts any `start`/`end` parameters. `/api/dates` returns all available detection dates. |
| **Dexter River adapter** | `dexter/bead_field/river/river_adapter.py` — same pattern as RA's adapter, reads any date range from River parquets. |
| **Gap** | Frontend never requests more than 10 days. No UI to browse or select historical ranges. No performance optimization for large date ranges (e.g., streaming, pagination, or progressive loading). |
| **Implementation notes** | 1. **Date range selector**: Replace single `<input type="date">` with a range picker (start + end date fields, or a calendar widget). 2. **Backend range endpoint** already exists (`/api/bars-range`). For very large ranges (months), add optional `limit` parameter or server-side downsampling (e.g., return 4H bars instead of 1m for ranges > 30 days). 3. **Progressive loading**: For 4H/1D charts spanning months, load initial window then fetch more as user scrolls left — use LWC's `subscribeVisibleLogicalRangeChange()` to trigger lazy loads. 4. **Backend `/api/available-range`**: New endpoint returning `{earliest: "2022-...", latest: "2026-..."}` so frontend can set picker bounds. Use `RiverBarAdapter.available_range()` logic from RA (`river_adapter.py:163`). 5. **Performance**: For 1D spanning 4 years ≈ ~1000 bars — trivial. For 1m spanning months — need pagination. 4H for 1 year ≈ ~1500 bars — fine. |
| **Effort** | **M** — UI range picker + lazy loading + `/api/available-range` endpoint. Backend data access already works. |

---

### ISSUE 6: State & Strategy Display

**Symptom**: Unclear how WorldState and checklist results appear on MIRROR. Olya needs: current system state + trade setups found.

| Aspect | Detail |
|---|---|
| **Dexter WorldState** | `dexter/state/classifier.py` — `WorldState` dataclass: `htf_phase`, `direction_permission`, `authority_tf`, `daily_direction`, `mechanism_used`, `h1_alignment`, `h4_counter`, `confidence`, `notes`, `computed_at`. `classify_day_snapshots()` produces time-indexed snapshots. `daily_detection_export.py:291-305` exports `world_state` to per-day JSON with all fields. Also exports `world_state_snapshots` array (time series of intraday state changes). |
| **Dexter ChecklistResult** | `checklist/evaluator.py:45-78` — `ChecklistResult`: `f1_bias_pass`, `f2_liquidity_pass`, `f3_structure_pass`, `f4_pda_pass`, `f5_target_pass`, `all_factors_pass`, `eligible_for_signal`, `model_type` (REVERSAL/CONTINUATION), `chain_type`, `direction`, `pda_type`, `pda_confluence`, `primary_target` (level, type, distance_pips), `pd_position` (PREMIUM/DISCOUNT/EQUILIBRIUM). |
| **Dexter DIAGNOSTIC_SIGNAL** | `checklist/signal_builder.py:49-120` — builds `DIAGNOSTIC_SIGNAL` ClaimSpec with `shadow_mode=True`. Fields in `reasoning_trace`: `f1-f5_pass`, `model_type`, `chain_type`, `direction`, `pda_type`, `pda_confluence`, `primary_target`, `worldstate_snapshot`. Exported in daily JSON as `diagnostic_signals` array. |
| **MIRROR current state** | `mirror/mirror.html:660-673` — WorldState banner exists with PHASE, PERM, AUTH, DIR, MECH fields. `mirror-app.js:453-472` — `updateWorldStateBanner()` populates these from `mApp.worldState`. `server.py:275-278` — extracts `world_state` from detection JSON on load. `server.py:306-310` — broadcasts `world_state` over WebSocket. **Works for basic display.** DIAGNOSTIC_SIGNAL: `mirror-chart.js:543-565` — renders gold square markers on chart. Click tooltip shows five-factor breakdown. `mirror-feed.js:189-231` — signal items in feed with F1-F5 checkmarks. **Partially working.** |
| **Gap** | (a) **No snapshot timeline** — MIRROR shows last WorldState only, not how it evolved during the day. (b) **No checklist panel** — five factors are only visible on signal click tooltip, not as a persistent dashboard element. (c) **No setup overview** — Olya can't see "system found 2 bullish setups today at LOKZ" without clicking each signal marker. (d) **No state transition indicator** — when WorldState changes (e.g., phase shifts from EXPANSION to RETRACE), there's no visual cue on the chart or timeline. |
| **Implementation notes** | 1. **State Timeline Widget**: Below the WorldState banner, add a collapsible timeline showing `world_state_snapshots` as color-coded dots (green=EXPANSION, yellow=RETRACE, gray=RANGE). Backend: include `world_state_snapshots` in WebSocket `world_state` message (it's already in the JSON). 2. **Setup Summary Panel**: In the detection feed sidebar, add a "Setups" section above the detection list showing: count of DIAGNOSTIC_SIGNALs today, grouped by direction, with pass/fail factor summary. Data source: `diagnostic_signals` array already sent to frontend. 3. **Five-Factor Dashboard Row**: Persistent row (like the WorldState banner) showing the latest DIAGNOSTIC_SIGNAL's five-factor status: `F1✓ F2✓ F3✓ F4✗ F5✓` with color coding. Updates when new signal arrives. 4. **Chart State Bands**: Optionally, render WorldState phase transitions as colored horizontal bands on the chart (like session bands but for state). Use the snapshot timestamps as boundaries. 5. **Active Levels**: The pipeline tracks active levels (`_extract_levels` in `level_lifecycle.py`). These could be rendered as horizontal lines on the chart — the data exists in the detection JSON. |
| **Effort** | **M** — State timeline + setup summary. **L** if chart state bands + active levels are included. |

---

## §3 — SHARED COMPONENTS (RA → MIRROR Direct Port)

| Component | RA Source | Port Target | Notes |
|---|---|---|---|
| **Session band computation** | `site/js/chart-tab.js:573-595` (`getSessionBandsForDay`) | `mirror/js/mirror-chart.js:625` | MIRROR already has the consumer code (`mApp.sessionData` path). Just need backend data. |
| **Crosshair tooltip** | `site/js/strategy-chart.js:421-478` | `mirror/js/mirror-chart.js` (new) | Port the `subscribeCrosshairMove` pattern + primitive-specific property formatting. |
| **Day tab component** | `site/js/chart-tab.js:834-860` (`renderDayTabs`) | `mirror/js/mirror-app.js` (new) | Self-contained: render buttons, click → scroll chart. |
| **Week picker + manifest** | `site/js/shared.js:760-885` | `mirror/js/mirror-app.js` (new) | Needs backend `/api/weeks` endpoint. Frontend pattern is reusable. |
| **Marker `_det` reference** | `site/js/strategy-chart.js:555` | `mirror/js/mirror-chart.js:536` | Add `_det: det` to marker objects in `buildMirrorMarkers()`. |
| **1D time tolerance** | `site/js/chart-tab.js:155` (`maxDiff = 86400`) | `mirror/js/mirror-chart.js:818` | Add `'1D'` case to tolerance map. |
| **Primitive label helper** | `site/js/shared.js:321` (`primLabel()`) | Already in MIRROR as `mPrimLabel()` | ✓ Already ported. |
| **Session band primitives** (LWC ISeriesPrimitive) | `site/js/chart-tab.js:63-130` | `mirror/js/mirror-chart.js:58-130` | ✓ Already ported (nearly identical code). |

---

## §4 — BACKEND API GAPS

| Endpoint | Status | Purpose | Implementation |
|---|---|---|---|
| `GET /api/bars/{date}?tf=` | ✅ Exists | Single-day bars | `server.py:397` |
| `GET /api/bars-range?start=&end=&tf=` | ✅ Exists | Multi-day bars | `server.py:409` |
| `GET /api/detections/{date}` | ✅ Exists | Per-day detection JSON | `server.py:424` |
| `GET /api/dates` | ✅ Exists | Available detection dates | `server.py:437` |
| `GET /api/heartbeat` | ✅ Exists | Streamer status | `server.py:445` |
| `GET /api/sessions/{date}` | ❌ Missing | Session band data for a forex day | Compute from bar data using session tagger logic. Return `[{session, forex_day, start_time, end_time, color, border}]` |
| `GET /api/sessions-range?start=&end=` | ❌ Missing | Session bands for date range | Same as above but for multi-day HTF views |
| `GET /api/available-range` | ❌ Missing | Earliest/latest date in River | Scan parquet dirs. Return `{pair, earliest, latest}` |
| `GET /api/weeks` | ❌ Missing | Week manifest for navigation | Group available dates into forex weeks (Mon-Fri). Return `[{week, start, end, forex_days, detection_count}]` |
| `GET /api/world-state/{date}` | ❌ Missing | WorldState snapshots for a day | Read from detection JSON's `world_state_snapshots` field. Already in the file. |
| `WS: type=sessions` | ❌ Missing | Push session data on connect | Send alongside initial bars/detections |
| `WS: type=world_state_snapshots` | ❌ Missing | Push snapshot timeline | Send alongside `world_state` message |

---

## §5 — RECOMMENDED BUILD ORDER

Build sequenced by dependency and impact:

| # | Task | Deps | Impact | Effort |
|---|---|---|---|---|
| **1** | **Backend: `/api/sessions` + WS push** | None | Fixes Issue 1 (session shading). Foundation for all session-related display. | S |
| **2** | **Frontend: Crosshair tooltips for all primitives** | None | Fixes Issue 3 (tooltips). Massive UX upgrade — Olya can identify signals. | S |
| **3** | **Frontend: 1D marker tolerance fix** | None | Partial fix for Issue 2 on 1D TF. One-line change. | XS |
| **4** | **Frontend: Day tabs + scroll sync** | None | Fixes Issue 4 (date scrolling, part 1). Intra-week navigation. | S |
| **5** | **Backend: `/api/weeks` + `/api/available-range`** | None | Enables Issue 4+5 (date scrolling, full history). | S |
| **6** | **Frontend: Week picker + extended HTF loading** | #5 | Fixes Issue 4 (date scrolling, part 2). Multi-week navigation. | M |
| **7** | **Frontend: Date range selector + progressive loading** | #5 | Fixes Issue 5 (full history). 4+ years accessible. | M |
| **8** | **Frontend: State timeline + setup summary** | None | Fixes Issue 6 (state display). Olya sees system state at a glance. | M |
| **9** | **Frontend: Five-factor dashboard row** | #8 | Enhances Issue 6. Persistent checklist status. | S |
| **10** | **Frontend: Active level lines on chart** | Backend data exists | Enhancement. Horizontal reference levels on chart. | S |

**Critical path for "TradingView quality"**: Tasks 1-4 (session shading, tooltips, 1D tolerance, day tabs) are the minimum to eliminate jank. Tasks 5-7 unlock full data access. Tasks 8-10 make the state readable.

---

## §6 — CHART LIBRARY ASSESSMENT

**Library**: Lightweight Charts v4.1.3 (TradingView's open-source library)

| Capability | Required For | Supported? | Notes |
|---|---|---|---|
| Candlestick series | Core display | ✅ Yes | Already working |
| Markers (setMarkers) | Detection signals | ✅ Yes | Already working. Limited to built-in shapes (arrow, circle, square). |
| ISeriesPrimitive | Session bands, overlays | ✅ Yes | Already implemented (`MSessionBandsPrimitive`). Can extend for state bands, level lines. |
| CrosshairMove subscription | Tooltips | ✅ Yes | RA uses this. MIRROR doesn't yet for primitives. |
| Click subscription | Signal drill-down | ✅ Yes | MIRROR already uses for DIAGNOSTIC_SIGNAL tooltip. |
| timeScale.setVisibleRange | Day/week navigation | ✅ Yes | Already used. |
| timeScale.scrollToRealTime | Live mode | ✅ Yes | Already used. |
| subscribeVisibleTimeRangeChange | Scroll sync | ✅ Yes | RA uses this for day tab sync. MIRROR has it but limited. |
| Price lines (createPriceLine) | Active levels | ✅ Yes | Not yet used. Native LWC feature — trivial to add. |
| Custom tick formatting | Multi-day axis labels | ✅ Yes | MIRROR already has `tickMarkFormatter` with sequential time mapping. |
| Multi-series (line + candle) | Moving averages, etc. | ✅ Yes | Not currently needed but available. |

**Verdict**: LWC v4.1.3 supports **all 6 fixes** natively. No library change needed. The gap is implementation, not capability.

### TradingView-Grade Enhancement Recommendations

Beyond the 6 issues, these upgrades would bring MIRROR to Olya's "it just works" TradingView standard:

1. **Crosshair price label**: Show current crosshair price on the y-axis (TradingView does this by default). LWC supports this — just `crosshair.horzLine.labelVisible: true`.

2. **OHLC legend in chart header**: Real-time OHLC values updating as crosshair moves. TradingView shows `O: 1.08234 H: 1.08345 L: 1.08123 C: 1.08267` in the top-left. Use `subscribeCrosshairMove` to update a DOM element.

3. **Multi-symbol support**: Currently hardcoded to EURUSD. The architecture supports other pairs — `RiverBarAdapter` accepts `pair` parameter. Future-proof the frontend with a symbol selector.

4. **Keyboard shortcuts**: TradingView muscle memory: `1`-`6` for TF switch, `←`/`→` for scroll, `+`/`-` for zoom. Trivial to add.

5. **Chart drawing tools**: Not in scope for v1, but LWC supports custom drawing via primitives (trend lines, horizontal lines, rectangles). Olya may want these for manual annotation.

6. **Screenshot/export**: One-click chart screenshot. LWC has `chart.takeScreenshot()` returning a canvas — convert to PNG download.

7. **Persistent user preferences**: Save TF, active primitives, date position to `localStorage`. Restore on page load. Currently resets to defaults on every visit.

---

*End of MIRROR_RECON.md — CTO can write build brief from this document.*
