# MIRROR DEEP DIVE AUDIT BRIEF
## Date: 2026-03-25 | Owner: CTO | Priority: P0
## Principle: "Understand completely before touching anything."

---

## WHY THIS AUDIT

MIRROR has been through multiple fix cycles (Cursor sprint, Phase 5 fixes,
R2 patch round) and keeps exhibiting the same pattern: fix one interaction,
break another. This indicates the problem is architectural, not bug-level.

Previous approaches treated symptoms. This audit treats the disease.

MIRROR is not cosmetic — it is the VALIDATION INSTRUMENT for Olya to
confirm that detection producers are methodologically correct. If MIRROR
is unreliable, INV-OLYA-ABSOLUTE is unenforceable. We just built 564,471
signed CLAIM beads across 5 years. We need to SEE them correctly.

---

## YOUR MISSION

**DO NOT FIX ANYTHING.** Your job is to produce a complete architectural
map of MIRROR's frontend and backend. Every state variable. Every event
handler. Every data loading path. Every rendering function. Every interaction
between them.

The output is a document that makes the state machine VISIBLE so that
fixes can be made with full understanding of ripple effects.

---

## SCOPE

### Files to Audit

```yaml
FRONTEND:
  primary:
    - mirror/frontend/js/mirror-app.js      # main app state + orchestration
    - mirror/frontend/js/mirror-chart.js     # chart rendering + detection overlay
  secondary:
    - mirror/frontend/index.html             # DOM structure, element IDs
    - mirror/frontend/css/                   # any CSS that affects layout/visibility
  
BACKEND:
  primary:
    - mirror/backend/server.py               # FastAPI endpoints + WebSocket
  data_sources:
    - ~/dexter/output/detections/            # detection JSON files (per forex day)
    - ~/phoenix-river/EURUSD/                # River parquet + staging JSONL
    
RA_CALIBRATION_TOOL (reference for correct behavior):
    - research_accelerator/src/ra/app.py     # or equivalent entry point
    - research_accelerator/src/ra/charts/    # chart rendering that worked correctly
```

Note: the RA calibration tool (localhost:8787/8200) successfully handled
TF switching, date navigation, detection overlay, and session shading
during Olya's 14-trade annotation sessions. Use it as a REFERENCE for
how these interactions SHOULD work.

---

## AUDIT DELIVERABLES

### 1. STATE INVENTORY

For every piece of mutable state in the frontend, document:

```yaml
# Template for each state variable:
variable_name:
  location: "file:line"
  type: "string | number | array | object"
  initial_value: "what it starts as"
  set_by: ["list every function/handler that modifies it"]
  read_by: ["list every function that reads it"]
  purpose: "what it controls"
  interactions: "what other state it affects when changed"
```

Include at minimum:
- Current TF selection
- Current date / date range
- Week picker state
- Bar data (loaded candles)
- Detection data (loaded detections)
- Session band data
- Chart scroll / pan position
- Detection feed filter state
- Any flags (isHTF, isLive, isHistorical, etc.)

### 2. USER ACTION MAP

For every user interaction, trace the FULL execution path:

```yaml
# Template:
action: "User clicks 5m TF button"
handler: "file:line — function name"
state_changes:
  - "sets currentTF = '5m'"
  - "calls loadBars()"
  - "calls loadDetections()"
  - "calls renderChart()"
triggers:
  - "bar reload: /api/bars-range with 5m lookback"
  - "detection reload: /api/detections/{date} for current date"
  - "chart rerender with new bar data"
  - "detection feed filter update"
does_NOT_trigger:
  - "session band recalculation (BUG — should it?)"
```

Cover these actions at minimum:
- Click each TF button (1m, 5m, 15m, 1H, 4H, 1D)
- Pick a week via week picker dropdown
- Enter a date in the date input field
- Click a day button (Mon, Tue, Wed, Thu, Fri)
- Click the NOW button
- Click forward/back navigation arrows
- Scroll/pan the chart
- Click a detection marker (tooltip)
- Change Detection Feed filter dropdown

### 3. DATA LOADING MAP

For every API call, document:

```yaml
# Template:
endpoint: "/api/bars-range"
called_by: ["list every frontend function that calls this"]
parameters: "start_date, end_date, timeframe"
backend_handler: "server.py:line — function name"
data_source: "River parquets via RiverBarAdapter"
response_shape: "{ bars: [...], metadata: {...} }"
frontend_consumer: "function that processes the response"
renders_into: "chart candles / detection markers / session bands"
```

Cover these endpoints:
- `/api/bars/{date}` (single day)
- `/api/bars-range` (multi-day)
- `/api/detections/{date}` (single day detections)
- `/api/sessions/{date}` (session boundaries)
- Any WebSocket messages
- Any other endpoints

### 4. RENDERING PIPELINE MAP

For each visual element on the chart, trace from data to pixels:

```yaml
# Template:
element: "Session shading bands"
data_source: "session API response"
transform_chain:
  - "raw session times (NY) → toNYTS() → shifted timestamps"
  - "shifted timestamps → _findNearestSeqTime() → bar indices"
  - "bar indices → rect x positions on chart"
  - "render as colored rectangles behind candles"
failure_modes:
  - "toNYTS offset wrong for DST → bands shift by 1 hour"
  - "_findNearestSeqTime returns -1 → band not rendered"
  - "isHTF gate prevents rendering on LTF → no bands on 5m"
```

Cover these elements:
- Candlestick bars
- Detection markers (colored shapes on chart)
- Detection feed sidebar entries
- Session shading bands (Asia, LOKZ, NYOKZ)
- Tooltip popups
- State dots (green/amber/red row)
- Checklist display (F1-F5)
- Phase/Permission/Direction header bar
- Price cursor / crosshair
- Date/time axis labels

### 5. CONFLICT MAP

This is the most important deliverable. For every pair of interactions
that can conflict, document:

```yaml
# Template:
conflict: "Week picker vs TF button"
scenario: "User picks week X, then clicks 5m"
what_happens:
  - "Week picker sets date range to Mon-Fri"
  - "5m button recalculates lookback (2 days)"
  - "Lookback OVERRIDES week picker range"
  - "Chart shows 2 days, not the selected week"
expected: "Chart centers on selected week with 5m lookback"
root_cause: "Two independent range-setting mechanisms, no arbiter"
```

Look specifically for:
- Date range conflicts (week picker vs lookback vs scroll)
- TF change side effects (what gets reloaded, what doesn't)
- Detection loading gaps (multi-day views loading single-day detections)
- Session rendering conditions (what gates prevent rendering)
- State that persists when it shouldn't (stale data after TF switch)
- State that resets when it shouldn't (losing scroll position on TF switch)

### 6. COMPARISON WITH RA CALIBRATION TOOL

Where MIRROR's architecture diverges from the RA tool's approach:

```yaml
# Template:
feature: "Date navigation"
ra_approach: "Single centerDate + lookback per TF, scroll updates centerDate"
mirror_approach: "Multiple competing: weekRange, dateInput, dayButtons, NOW"
divergence: "RA has one source of truth for date. MIRROR has four."
recommendation: "Adopt RA pattern — single centerDate drives everything"
```

Cover: date navigation, TF switching, detection overlay, session rendering.

### 7. RECOMMENDED ARCHITECTURE

Based on everything found, propose:

```yaml
state_model:
  single_source_of_truth:
    centerDate: "the date the view is anchored to"
    currentTF: "the active timeframe"
  derived_state:
    barRange: "computed from centerDate + lookback[currentTF]"
    detectionRange: "same as barRange"
    sessionRange: "same as barRange"
  
action_flow:
  any_navigation_action:
    1: "update centerDate and/or currentTF"
    2: "recompute barRange from centerDate + lookback[currentTF]"
    3: "load bars for barRange"
    4: "load detections for barRange (all dates in range)"
    5: "load sessions for barRange"
    6: "render everything"
    
  rule: "EVERY user action flows through the same pipeline.
    No special cases. No conditional gates. No competing paths."
```

---

## WHAT NOT TO DO

- **DO NOT** modify any code during this audit
- **DO NOT** propose quick fixes for individual bugs
- **DO NOT** skip files or skim functions — read every line
- **DO NOT** assume prior fixes are correct (they may have introduced new issues)
- **DO NOT** limit scope to "just the bugs G reported" — map EVERYTHING

---

## OUTPUT FORMAT

Single document: `MIRROR_ARCHITECTURE_AUDIT.md`

Sections:
1. Executive Summary (1 page — key findings, severity, recommendation)
2. State Inventory (complete, per template above)
3. User Action Map (complete, per template above)
4. Data Loading Map (complete, per template above)
5. Rendering Pipeline Map (complete, per template above)
6. Conflict Map (complete, per template above)
7. RA Comparison (where MIRROR diverges from working reference)
8. Recommended Architecture (proposed state model + action flow)
9. Fix Priority List (ordered by impact, with effort estimates)

---

## SUCCESS CRITERIA

The audit is complete when:
- Another developer could read the document and understand MIRROR's
  entire state machine without reading the code
- Every reported bug (session shading, week picker, detection feed,
  HTF signals) can be traced to a specific conflict in the map
- The recommended architecture addresses ALL identified conflicts,
  not just the ones currently reported
- The fix priority list is actionable — specific files, specific
  functions, specific state variables to change

---

## CONTEXT FROM TODAY'S SESSION

Today we built the canonical detection-to-bead-field pipeline:
- Fixed export bug (FVG/OB silently dropped due to key name mismatch)
- Built claim_writer.py (ClaimSpec → signed CLAIM beads)
- Wired dual-write (JSON + beads from same pipeline run)
- Backfilled 564,471 beads across Jan 2021 → Mar 2026
- Detection JSON files now exist for every trading day in that range

This means MIRROR's backend has MUCH more data available than before.
The audit should consider:
- Backend can now serve bars and detections for ANY date 2021-2026
- Detection files cover ~1,400 trading days (was 3 before today)
- The date picker and navigation need to handle this full range smoothly
- Session data should be computable for any historical date

The data layer is solid. The pipeline is canonical. The display is the
remaining gap. This audit is how we close it properly.
