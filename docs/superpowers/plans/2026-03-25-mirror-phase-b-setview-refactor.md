# MIRROR Phase B: Unified setView() Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace MIRROR's flat mutable singleton + scattered state mutation with a unified `setView()` reducer that eliminates the "fix one interaction, break another" cycle permanently.

**Architecture:** All user actions (TF switch, date pick, week pick, day tab click, NOW button, scroll) flow through a single `setView(patch)` function that computes derived ranges, cancels in-flight fetches via AbortController, issues parallel data loads (bars + sessions + detections), and renders only when all data arrives with a matching version number. The chart rendering layer (mirror-chart.js) stays largely intact — it's the state management in mirror-app.js that gets replaced.

**Tech Stack:** Vanilla JS (no framework), LightweightCharts v4.1.3, FastAPI backend (minor endpoint addition only)

**Spec:** `research_accelerator/MIRROR_DEEP_DIVE_AUDIT_BRIEF.md` + Oracle audit findings from 2026-03-25 session

---

## Context: Why Phase B

Phase A (surgical fixes) confirmed the diagnosis: MIRROR has four competing navigation mechanisms, a real-vs-sequential timestamp confusion, and WS message handlers that trigger renders before all data is ready. Each targeted fix produced new regressions because the flat `mApp` singleton has no state transition discipline — any handler can mutate any field at any time, and the ripple effects are invisible.

### Confirmed Phase A Regressions (to be resolved by this refactor)
1. **NOW button → blank screen**: `_resetViewState()` clears `candleData`, then WS `detections` message arrives and triggers `refreshMirrorChart()` before bars for the active TF have loaded. Root cause: no "wait for all data" gate.
2. **Layout overflow**: Controls bar wraps to 2-3 rows + five-factor/state-timeline/day-tabs all `flex-shrink:0` = chrome exceeds viewport. CSS fix needed alongside the refactor.

### Phase A Fixes to PRESERVE
- ✅ Sequential timestamp conversion in `_mDayRange()` (Fix 2)
- ✅ Sequential timestamp conversion in `onFeedItemClick()` (Fix 3)
- ✅ Timezone contract documentation in mirror-chart.js header (Fix 5)
- ✅ WS subscribe handler in server.py (Fix 6)
- ✅ `var htf = isHTF(mApp.tf)` in scroll logic (Fix 1)

### Phase A Fixes SUBSUMED by this refactor
- ❌ `_resetViewState()` — replaced by `setView()` transition logic
- ❌ Separate `switchToLive()`/`switchToHistorical()` — merged into `setView({mode})`

---

## File Structure

```
mirror/
├── js/
│   ├── mirror-state.js     ← NEW: ViewState, setView(), fetch orchestration
│   ├── mirror-app.js       ← REWRITE: thin shell — boot, UI event wiring, WS client
│   ├── mirror-chart.js     ← MODIFY: minor — accept state from setView, keep rendering
│   └── mirror-feed.js      ← MODIFY: minor — call setView() instead of direct mutations
├── backend/
│   └── server.py           ← MODIFY: add /api/detections-range endpoint
├── mirror.html             ← MODIFY: add mirror-state.js script tag, CSS overflow fixes
└── css/
    └── (inline in html)    ← MODIFY: controls bar overflow, chrome height budget
```

### Responsibility Map

| File | Responsibility | Changes |
|------|---------------|---------|
| `mirror-state.js` | State management, fetch orchestration, derived state computation | **New file** — ~300 lines |
| `mirror-app.js` | Boot sequence, UI event binding, WS client, DOM updates | **Rewrite** — removes all state mutation logic, becomes thin wiring layer |
| `mirror-chart.js` | Chart creation, candle rendering, markers, session bands, tooltips | **Minor** — `refreshMirrorChart()` called by state module, not by individual handlers |
| `mirror-feed.js` | Detection feed sidebar, click-to-navigate | **Minor** — `onFeedItemClick` already fixed, just wire filter changes through setView |
| `server.py` | Backend API + WS | **Minor** — add `/api/detections-range` for parallel loading |
| `mirror.html` | DOM + CSS | **Minor** — add script tag, fix layout overflow |

---

## Task Breakdown

### Task 0: Fix Layout Overflow (CSS-only, zero risk)

**Files:**
- Modify: `research_accelerator/mirror/mirror.html` (CSS section)

This is a pure CSS fix with no JS interaction. Do it first so QA can see the full UI.

- [ ] **Step 1: Add max-height constraint to controls bar**

In `mirror.html` CSS, change `.controls-bar`:

```css
.controls-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    flex-wrap: wrap;
    max-height: 72px;      /* cap at ~2 rows */
    overflow-y: hidden;
}
```

Add overflow containment to `.prim-toggles`:

```css
.prim-toggles {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    max-height: 52px;      /* cap primitive toggle rows */
    overflow: hidden;
}
```

- [ ] **Step 2: Ensure five-factor, state-timeline, day-tabs don't stack unboundedly**

Add to CSS:

```css
/* Chrome height budget: header(48) + banner(32) + controls(72 max) + 
   optional rows(~80 max) + metadata(28) = 260px max chrome.
   Remaining viewport height goes to chart + sidebar. */

#five-factor-row, #state-timeline, #day-tabs {
    flex-shrink: 0;
    overflow: hidden;
}
```

- [ ] **Step 3: Verify in browser — full UI visible without scrolling**

Open mirror.html, verify no horizontal or vertical overflow.

- [ ] **Step 4: Commit**

```bash
git add mirror/mirror.html
git commit -m "fix: constrain controls bar and chrome height to prevent layout overflow"
```

---

### Task 1: Create mirror-state.js — ViewState + setView()

**Files:**
- Create: `research_accelerator/mirror/js/mirror-state.js`

This is the core of the refactor. A self-contained state management module.

- [ ] **Step 1: Create mirror-state.js with ViewState and setView()**

```javascript
/* ═══════════════════════════════════════════════════════════════════════════════
 * mirror-state.js — Unified state management for MIRROR dashboard
 *
 * ALL user actions flow through setView(patch). No other code mutates
 * view state directly. This eliminates race conditions, stale data leaks,
 * and the "fix one interaction, break another" cycle.
 *
 * Architecture:
 *   action → setView({tf?, date?, mode?})
 *     → compute derived ranges (barRange, detRange, sessRange)
 *     → cancel in-flight fetches (AbortController)
 *     → parallel fetch: bars + sessions + detections
 *     → on completion: render(version) — no-ops if version is stale
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── TF Lookback Table ─────────────────────────────────────────────────────── */

const VIEW_TF_LOOKBACK = {
  '1m': 1, '5m': 2, '15m': 4, '1H': 9, '4H': 29, '1D': 59,
};

/* ── ViewState — single source of truth ────────────────────────────────────── */

const viewState = {
  // Core state (set by setView only)
  mode: 'live',          // 'live' | 'historical'
  tf: '5m',              // active timeframe
  anchorDate: null,       // YYYY-MM-DD — the date the view is centered on (null = today)

  // Derived state (computed by setView, read-only externally)
  barRange: null,         // { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }

  // Loaded data (populated by fetch pipeline, read-only externally)
  bars: [],               // candle data for current TF
  detections: null,       // { detections_by_primitive: {...}, diagnostic_signals: [...] }
  sessions: [],           // session bands [{session, forex_day, start_time, end_time, color, border}]
  worldState: null,       // { htf_phase, direction_permission, ... }
  worldStateSnapshots: [],
  signals: [],

  // Navigation (derived from loaded data)
  forexDays: [],
  activeDay: null,        // currently focused forex day (for day tab highlighting)

  // Version counter — incremented on every setView call.
  // Render functions check this to skip stale renders.
  version: 0,

  // Fetch abort controller — cancels in-flight requests on new setView
  _abortController: null,

  // Loading state
  loading: false,
};

/* ── Compute derived bar range from anchor + TF lookback ───────────────────── */

function _computeBarRange(anchorDate, tf) {
  const lookback = VIEW_TF_LOOKBACK[tf] || 2;
  const anchor = anchorDate || _todayDateStr();
  const endD = new Date(anchor + 'T12:00:00Z');
  const startD = new Date(endD);
  startD.setUTCDate(startD.getUTCDate() - lookback);
  return {
    start: startD.toISOString().split('T')[0],
    end: endD.toISOString().split('T')[0],
  };
}

function _todayDateStr() {
  return new Date().toISOString().split('T')[0];
}

/* ── setView — THE state transition function ───────────────────────────────── */

/**
 * Update the view state. Every user action calls this.
 *
 * @param {Object} patch — partial update: { tf?, date?, mode?, day? }
 *   - tf: switch timeframe (e.g., '4H')
 *   - date: navigate to a date (e.g., '2026-03-20')
 *   - mode: switch mode ('live' | 'historical')
 *   - day: set active forex day (for day tab click)
 *   - rangeStart/rangeEnd: explicit range (week picker)
 *
 * setView() is idempotent for the same patch. It:
 *   1. Updates core state
 *   2. Computes derived ranges
 *   3. Cancels in-flight fetches
 *   4. Fetches all data in parallel
 *   5. Renders on completion (version-gated)
 */
async function setView(patch) {
  if (!patch || typeof patch !== 'object') return;

  const prevVersion = viewState.version;
  viewState.version++;
  const thisVersion = viewState.version;

  // ── 1. Update core state ────────────────────────────────────────────
  if (patch.mode != null) viewState.mode = patch.mode;
  if (patch.tf != null) viewState.tf = patch.tf;
  if (patch.date != null) viewState.anchorDate = patch.date;
  if (patch.day != null) viewState.activeDay = patch.day;

  // Live mode clears anchor date (follow current time)
  if (viewState.mode === 'live') {
    viewState.anchorDate = null;
  }

  // ── 2. Compute derived ranges ───────────────────────────────────────
  let barRange;
  if (patch.rangeStart && patch.rangeEnd) {
    // Explicit range (week picker) — expand by TF lookback for context
    const lookback = VIEW_TF_LOOKBACK[viewState.tf] || 9;
    const midDate = new Date(patch.rangeStart + 'T12:00:00Z');
    midDate.setUTCDate(midDate.getUTCDate() + 2); // ~Wednesday
    const rangeStart = new Date(midDate);
    rangeStart.setUTCDate(rangeStart.getUTCDate() - lookback);
    const rangeEnd = new Date(midDate);
    rangeEnd.setUTCDate(rangeEnd.getUTCDate() + lookback);
    const today = new Date();
    if (rangeEnd > today) rangeEnd.setTime(today.getTime());
    barRange = {
      start: rangeStart.toISOString().split('T')[0],
      end: rangeEnd.toISOString().split('T')[0],
    };
  } else {
    barRange = _computeBarRange(viewState.anchorDate, viewState.tf);
  }
  viewState.barRange = barRange;

  // ── 3. Cancel in-flight fetches ─────────────────────────────────────
  if (viewState._abortController) {
    viewState._abortController.abort();
  }
  viewState._abortController = new AbortController();
  const signal = viewState._abortController.signal;

  // ── 4. Show loading state ───────────────────────────────────────────
  viewState.loading = true;
  _showLoading(true);

  // ── 5. Parallel fetch: bars + sessions + detections ─────────────────
  try {
    const tf = viewState.tf;
    const { start, end } = barRange;

    const [barsResp, sessResp, detsResp] = await Promise.all([
      fetch(`/api/bars-range?start=${start}&end=${end}&tf=${tf}`, { signal }),
      fetch(`/api/sessions-range?start=${start}&end=${end}`, { signal }),
      fetch(`/api/detections-range?start=${start}&end=${end}`, { signal })
        .catch(() => null), // Fallback if endpoint doesn't exist yet
    ]);

    // ── Version gate: skip if a newer setView() has been called ───────
    if (viewState.version !== thisVersion) return;

    // Parse responses
    if (barsResp.ok) {
      const barsData = await barsResp.json();
      viewState.bars = barsData.data || [];
    } else {
      viewState.bars = [];
    }

    if (sessResp.ok) {
      const sessData = await sessResp.json();
      viewState.sessions = sessData.sessions || [];
    } else {
      viewState.sessions = [];
    }

    if (detsResp && detsResp.ok) {
      viewState.detections = await detsResp.json();
    } else {
      // Fallback: load detections day-by-day (until backend endpoint exists)
      viewState.detections = await _loadDetectionsRangeParallel(start, end, signal);
    }

    // ── Version gate again (after async parsing) ──────────────────────
    if (viewState.version !== thisVersion) return;

    // ── 6. Render ─────────────────────────────────────────────────────
    viewState.loading = false;
    _showLoading(false);

    // Sync into mApp for chart/feed consumption
    // (bridge layer — removed once chart reads viewState directly)
    _syncToMApp();

    // Trigger renders
    if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
    if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(viewState.detections);
    if (typeof updateWorldStateBanner === 'function') updateWorldStateBanner();
    if (typeof updateFiveFactorRow === 'function') updateFiveFactorRow();
    if (typeof updateSetupSummary === 'function') updateSetupSummary();
    if (typeof renderDayTabs === 'function') renderDayTabs();
    if (typeof renderStateTimeline === 'function') renderStateTimeline();
    if (typeof updateMetadata === 'function') updateMetadata();

  } catch (err) {
    if (err.name === 'AbortError') {
      // Expected — a newer setView() cancelled us
      return;
    }
    console.error('[MIRROR] setView fetch failed:', err);
    viewState.loading = false;
    _showLoading(false);
  }
}

/* ── Parallel detection loading (fallback until /api/detections-range) ────── */

async function _loadDetectionsRangeParallel(startDate, endDate, signal) {
  const merged = { detections_by_primitive: {}, diagnostic_signals: [] };
  const dates = [];
  const d = new Date(startDate + 'T12:00:00Z');
  const dEnd = new Date(endDate + 'T12:00:00Z');
  while (d <= dEnd) {
    dates.push(d.toISOString().split('T')[0]);
    d.setUTCDate(d.getUTCDate() + 1);
  }

  // Parallel fetch all dates (max ~60 concurrent — fine for local server)
  const results = await Promise.all(
    dates.map(ds =>
      fetch(`/api/detections/${ds}`, { signal })
        .then(r => r.ok ? r.json() : null)
        .catch(() => null)
    )
  );

  for (const dd of results) {
    if (!dd) continue;
    const byPrim = dd.detections_by_primitive || {};
    for (const [prim, byTf] of Object.entries(byPrim)) {
      if (!merged.detections_by_primitive[prim]) merged.detections_by_primitive[prim] = {};
      for (const [tf2, dets] of Object.entries(byTf)) {
        if (!merged.detections_by_primitive[prim][tf2]) merged.detections_by_primitive[prim][tf2] = [];
        merged.detections_by_primitive[prim][tf2].push(...dets);
      }
    }
    if (dd.diagnostic_signals) merged.diagnostic_signals.push(...dd.diagnostic_signals);
    // Capture world state from most recent day
    if (dd.world_state) merged.world_state = dd.world_state;
    if (dd.world_state_snapshots) merged.world_state_snapshots = dd.world_state_snapshots;
  }
  return merged;
}

/* ── Bridge: sync viewState → mApp (temporary until full migration) ────────── */

function _syncToMApp() {
  if (typeof mApp === 'undefined') return;

  mApp.tf = viewState.tf;
  mApp.mode = viewState.mode;
  mApp.currentDate = viewState.anchorDate;
  mApp.day = viewState.activeDay;

  // Candle data keyed by TF
  mApp.candleData[viewState.tf] = viewState.bars;
  mApp.detectionData = viewState.detections;
  mApp.sessionData = viewState.sessions;
  mApp.forexDays = viewState.forexDays;
  mApp.signals = viewState.signals;

  // World state from detection data
  if (viewState.detections) {
    if (viewState.detections.world_state) {
      mApp.worldState = viewState.detections.world_state;
    }
    if (viewState.detections.world_state_snapshots) {
      mApp.worldStateSnapshots = viewState.detections.world_state_snapshots;
    }
  }
}

/* ── Loading overlay helper ────────────────────────────────────────────────── */

function _showLoading(show) {
  const el = document.getElementById('loading-overlay');
  if (!el) return;
  if (show) el.classList.remove('hidden');
  else el.classList.add('hidden');
}

/* ── Live mode: handle WS data pushes ──────────────────────────────────────── */

/**
 * Process a WS data push without triggering a full reload.
 * In live mode, the server pushes incremental updates (bars, detections, etc.).
 * These update viewState data and trigger a render — but only if no setView()
 * fetch is in flight (prevents stale-data races).
 */
function handleLiveUpdate(msg) {
  if (!msg || !msg.type) return;
  if (viewState.loading) return; // setView() is in progress — skip WS updates

  switch (msg.type) {
    case 'bars':
      if (msg.tf === viewState.tf) {
        viewState.bars = msg.data || [];
        _syncToMApp();
        if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      }
      break;

    case 'detections': {
      const rawDet = msg.data || msg;
      viewState.detections = rawDet.detections_by_primitive
        ? rawDet
        : { detections_by_primitive: rawDet };
      _syncToMApp();
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(viewState.detections);
      if (typeof updateFiveFactorRow === 'function') updateFiveFactorRow();
      if (typeof updateSetupSummary === 'function') updateSetupSummary();
      if (typeof renderDayTabs === 'function') renderDayTabs();
      break;
    }

    case 'world_state':
      viewState.worldState = msg.data || msg;
      _syncToMApp();
      if (typeof updateWorldStateBanner === 'function') updateWorldStateBanner();
      break;

    case 'sessions':
      viewState.sessions = msg.data || [];
      _syncToMApp();
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;

    case 'world_state_snapshots':
      viewState.worldStateSnapshots = msg.data || [];
      _syncToMApp();
      if (typeof renderStateTimeline === 'function') renderStateTimeline();
      break;

    case 'signals':
      viewState.signals = msg.data || msg.signals || [];
      _syncToMApp();
      if (typeof updateSignalMarkers === 'function') updateSignalMarkers();
      if (typeof addSignalsToFeed === 'function') addSignalsToFeed(viewState.signals);
      break;

    case 'status': {
      const stData = msg.data || msg;
      const st = (stData.state || '').toUpperCase();
      if (typeof updateLiveBadge === 'function') {
        if (st === 'LIVE') updateLiveBadge('live');
        else if (st === 'STALE') updateLiveBadge('stale');
        else if (st === 'MARKET_CLOSED') updateLiveBadge('closed');
        else updateLiveBadge('connecting');
      }
      if (typeof updateMetadata === 'function') updateMetadata();
      break;
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add mirror/js/mirror-state.js
git commit -m "feat: add mirror-state.js — unified ViewState + setView() architecture"
```

---

### Task 2: Wire mirror-state.js into HTML + fix layout overflow

**Files:**
- Modify: `research_accelerator/mirror/mirror.html`

- [ ] **Step 1: Add mirror-state.js script tag BEFORE mirror-app.js**

In mirror.html, change the script section at the bottom:

```html
<!-- ── Application Scripts ─────────────────────────────────────────────── -->
<script src="js/mirror-state.js?v=20260325"></script>
<script src="js/mirror-app.js?v=20260325"></script>
<script src="js/mirror-chart.js?v=20260325"></script>
<script src="js/mirror-feed.js?v=20260325"></script>
```

mirror-state.js must load first — it defines `viewState`, `setView()`, and `handleLiveUpdate()` that the other files consume.

- [ ] **Step 2: Fix layout overflow in CSS**

In the `<style>` section, modify `.controls-bar`:

```css
.controls-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    flex-wrap: wrap;
    max-height: 80px;
    overflow: hidden;
}
```

Modify `.prim-toggles`:

```css
.prim-toggles {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    max-height: 56px;
    overflow: hidden;
}
```

- [ ] **Step 3: Commit**

```bash
git add mirror/mirror.html
git commit -m "feat: wire mirror-state.js, fix layout overflow with max-height constraints"
```

---

### Task 3: Rewrite mirror-app.js — thin wiring layer

**Files:**
- Modify: `research_accelerator/mirror/js/mirror-app.js`

This is the biggest change. mirror-app.js currently owns state management, WS routing, REST loading, AND UI wiring. After this task, it only does: WS client, UI event binding, and boot sequence. All state mutations go through `setView()` or `handleLiveUpdate()`.

- [ ] **Step 1: Replace the WebSocket message handler**

Replace the existing `handleWSMessage()` function with one that delegates to `handleLiveUpdate()` from mirror-state.js:

```javascript
function handleWSMessage(msg) {
  if (!msg || !msg.type) return;

  // In live mode, delegate ALL data messages to the state module.
  // This ensures version-gated rendering and prevents stale-data races.
  if (typeof handleLiveUpdate === 'function') {
    handleLiveUpdate(msg);
  }
}
```

- [ ] **Step 2: Replace switchToLive() and switchToHistorical()**

Remove `_resetViewState()`, `switchToLive()`, `switchToHistorical()`, `loadHistoricalDate()`, `loadWeekRange()`, and `_loadDetectionsRange()`. Replace with setView-based versions:

```javascript
function switchToLive() {
  disconnectWS();

  // Update date picker UI
  const picker = document.getElementById('date-picker');
  if (picker) picker.value = '';

  // Transition to live mode via setView — fetches initial data
  setView({ mode: 'live', date: null });

  // Reconnect WS for live pushes
  connectWS();
}

function switchToHistorical(dateStr) {
  disconnectWS();
  updateLiveBadge('disconnected');
  setView({ mode: 'historical', date: dateStr });
}
```

- [ ] **Step 3: Replace TF button click handler**

In `renderTFButtons()`, replace the click handler's async IIFE with:

```javascript
btn.addEventListener('click', function () {
  if (tf === mApp.tf) return;
  _savePreferences();
  renderTFButtons();

  if (typeof feedState !== 'undefined') {
    feedState.tfFilter = tf;
    if (typeof renderFeed === 'function') renderFeed();
  }

  // Single call — setView handles everything
  setView({ tf: tf });
});
```

- [ ] **Step 4: Replace week picker handler**

In `setupWeekPicker()`, replace the change handler:

```javascript
picker.addEventListener('change', function () {
  const val = picker.value;
  if (!val) return;
  const [start, end] = val.split('|');
  disconnectWS();
  updateLiveBadge('disconnected');
  setView({ mode: 'historical', date: start, rangeStart: start, rangeEnd: end });
});
```

- [ ] **Step 5: Replace date picker handler**

In `setupDatePicker()`, replace the change handler:

```javascript
picker.addEventListener('change', function () {
  const val = picker.value;
  if (!val) return;
  if (pickerEnd && pickerEnd.style.display !== 'none' && pickerEnd.value) {
    disconnectWS();
    updateLiveBadge('disconnected');
    setView({ mode: 'historical', date: val, rangeStart: val, rangeEnd: pickerEnd.value });
  } else {
    switchToHistorical(val);
  }
});
```

- [ ] **Step 6: Replace NOW button handler**

Already handled — `switchToLive()` in step 2 calls `setView({ mode: 'live' })`.

- [ ] **Step 7: Replace WS onopen to trigger initial setView in live mode**

In `connectWS()`, update the `ws.onopen` handler:

```javascript
mApp.ws.onopen = function () {
  console.log('[MIRROR] WebSocket connected');
  mApp.wsConnected = true;
  _wsBackoff = 1000;
  updateLiveBadge('live');

  // Send TF subscription for live bar pushes
  mApp.ws.send(JSON.stringify({ type: 'subscribe', tf: viewState.tf }));

  // If this is a fresh live connection (not reconnect), trigger initial data load.
  // setView fetches bars/sessions/detections for the current TF via REST,
  // then WS pushes keep it updated.
  if (!viewState.bars || viewState.bars.length === 0) {
    setView({ mode: 'live', tf: viewState.tf });
  }
};
```

- [ ] **Step 8: Remove dead code**

Remove these functions which are now handled by mirror-state.js:
- `_resetViewState()` (replaced by setView version-gated transitions)
- `loadHistoricalDate()` (replaced by setView)
- `loadWeekRange()` (replaced by setView with rangeStart/rangeEnd)
- `_loadDetectionsRange()` (replaced by `_loadDetectionsRangeParallel` in mirror-state.js)
- `_M_TF_LOOKBACK` (moved to mirror-state.js as `VIEW_TF_LOOKBACK`)

- [ ] **Step 9: Update boot sequence**

Replace the boot IIFE to use setView:

```javascript
(async function boot() {
  _loadPreferences();

  // Sync saved TF preference into viewState
  if (typeof viewState !== 'undefined') {
    viewState.tf = mApp.tf;
  }

  initPrimitiveToggles();
  renderTFButtons();
  renderPrimitiveToggles();
  renderSessionLegend();
  setupDatePicker();
  setupNowButton();
  setupKeyboardShortcuts();
  if (typeof initFeed === 'function') {
    initFeed();
    if (typeof feedState !== 'undefined') feedState.tfFilter = mApp.tf;
  }
  setupWeekPicker();

  // Connect WS — onopen will trigger initial setView()
  connectWS();
})();
```

- [ ] **Step 10: Commit**

```bash
git add mirror/js/mirror-app.js
git commit -m "refactor: rewrite mirror-app.js to route all actions through setView()"
```

---

### Task 4: Update mirror-chart.js — guard against partial data

**Files:**
- Modify: `research_accelerator/mirror/js/mirror-chart.js`

The chart rendering is mostly correct. The only change: `refreshMirrorChart()` should be resilient to being called when not all data is ready (the version gate in setView prevents this, but defense-in-depth).

- [ ] **Step 1: Add early-exit guard in refreshMirrorChart()**

At the top of `refreshMirrorChart()`, add:

```javascript
function refreshMirrorChart() {
  if (typeof mApp === 'undefined') return;
  if (typeof viewState !== 'undefined' && viewState.loading) return; // setView in progress

  if (!mApp.chart || !mApp.candleSeries) {
    createMirrorChart();
  }
  // ... rest unchanged
```

- [ ] **Step 2: Commit**

```bash
git add mirror/js/mirror-chart.js
git commit -m "fix: guard refreshMirrorChart against renders during setView loading"
```

---

### Task 5: Add /api/detections-range backend endpoint

**Files:**
- Modify: `research_accelerator/mirror/backend/server.py`

The parallel frontend fallback works, but a single backend endpoint is faster and cleaner.

- [ ] **Step 1: Add _load_detections_range helper**

After the existing `_load_detections()` function:

```python
def _load_detections_range(start_day: str, end_day: str) -> dict:
    """Load and merge detection JSON across a date range."""
    merged: dict[str, Any] = {"detections_by_primitive": {}, "diagnostic_signals": []}
    dt_start = date.fromisoformat(start_day)
    dt_end = date.fromisoformat(end_day)
    d = dt_start
    last_ws = None
    last_ws_snaps = None
    while d <= dt_end:
        det = _load_detections(d.isoformat())
        if det:
            by_prim = det.get("detections_by_primitive", {})
            for prim, by_tf in by_prim.items():
                if prim not in merged["detections_by_primitive"]:
                    merged["detections_by_primitive"][prim] = {}
                for tf, dets in by_tf.items():
                    if tf not in merged["detections_by_primitive"][prim]:
                        merged["detections_by_primitive"][prim][tf] = []
                    merged["detections_by_primitive"][prim][tf].extend(dets)
            if det.get("diagnostic_signals"):
                merged["diagnostic_signals"].extend(det["diagnostic_signals"])
            if det.get("world_state"):
                last_ws = det["world_state"]
            if det.get("world_state_snapshots"):
                last_ws_snaps = det["world_state_snapshots"]
        d += timedelta(days=1)
    if last_ws:
        merged["world_state"] = last_ws
    if last_ws_snaps:
        merged["world_state_snapshots"] = last_ws_snaps
    return merged
```

- [ ] **Step 2: Add the REST endpoint**

After the existing `/api/detections/{forex_day}` endpoint:

```python
@app.get("/api/detections-range")
async def get_detections_range(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
):
    """Serve merged detection data across a date range."""
    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid date format."})
    # Run blocking I/O in thread pool
    merged = await asyncio.to_thread(_load_detections_range, start, end)
    return merged
```

- [ ] **Step 3: Commit**

```bash
git add mirror/backend/server.py
git commit -m "feat: add /api/detections-range endpoint for parallel detection loading"
```

---

### Task 6: Integration QA + Day Tab setView Wiring

**Files:**
- Modify: `research_accelerator/mirror/js/mirror-app.js` (day tab click)

- [ ] **Step 1: Wire day tab clicks through setView**

In `renderDayTabs()`, update the click handler:

```javascript
btn.addEventListener('click', function () {
  setView({ day: fd });
  // Scroll chart to day range (setView updates activeDay,
  // but chart scroll is a display concern handled here)
  if (mApp.chart) {
    mApp.chart.timeScale().setVisibleRange(_mDayRange(fd));
  }
});
```

Note: day tab click does NOT trigger a full data reload — it just updates `activeDay` and scrolls. `setView()` should handle this as a "navigation-only" patch (no fetch needed). Add this check in `setView()`:

In mirror-state.js, at the top of `setView()`, add a fast path:

```javascript
// Fast path: day-only change doesn't need data reload
if (patch.day && !patch.tf && !patch.date && !patch.mode) {
  viewState.activeDay = patch.day;
  _syncToMApp();
  if (typeof renderDayTabs === 'function') renderDayTabs();
  return;
}
```

- [ ] **Step 2: Full QA checklist**

Test each interaction in order:

```
1. [ ] Load MIRROR → chart renders with candles on default TF
2. [ ] Switch TF to 4H → chart refetches + fits content (no blank flash)
3. [ ] Switch TF to 1m → chart refetches + scrolls to latest
4. [ ] Click day tab → chart scrolls to that day, tab highlights
5. [ ] Scroll chart → active day tab updates
6. [ ] Click detection in feed → chart pans to that candle
7. [ ] Pick a week → chart loads week range with detections
8. [ ] Pick a date → chart loads that date
9. [ ] Click NOW → live mode, candles load, no blank screen
10. [ ] Session bands visible on 5m
11. [ ] Session bands visible on 4H (reduced opacity)
12. [ ] Detection markers visible on 5m
13. [ ] Hover detection marker → tooltip shows
14. [ ] WorldState banner updates
15. [ ] Full UI fits in single browser window (no scroll)
16. [ ] Rapidly switch TFs (spam 1-2-3-4-5-6 keys) → no crash, last TF wins
```

- [ ] **Step 3: Commit**

```bash
git add mirror/js/mirror-app.js mirror/js/mirror-state.js
git commit -m "feat: wire day tabs through setView, add navigation fast-path"
```

---

### Task 7: Keyboard shortcut cleanup + preferences sync

**Files:**
- Modify: `research_accelerator/mirror/js/mirror-app.js`

- [ ] **Step 1: Fix keyboard shortcuts to use setView**

In `setupKeyboardShortcuts()`, replace the TF handling:

```javascript
if (tfMap[e.key]) {
  const newTf = tfMap[e.key];
  if (newTf !== viewState.tf) {
    _savePreferences();
    renderTFButtons();
    setView({ tf: newTf });
  }
  e.preventDefault();
  return;
}
```

Remove the `mApp.tf = newTf` direct mutation and the `btn.click()` call (which caused double execution).

- [ ] **Step 2: Update _savePreferences to read from viewState**

```javascript
function _savePreferences() {
  try {
    localStorage.setItem(_PREFS_KEY, JSON.stringify({
      tf: typeof viewState !== 'undefined' ? viewState.tf : mApp.tf,
      primitiveToggles: mApp.primitiveToggles,
    }));
  } catch (_) {}
}
```

- [ ] **Step 3: Commit**

```bash
git add mirror/js/mirror-app.js
git commit -m "fix: keyboard shortcuts use setView, no double execution"
```

---

## Summary: What Changes vs What Stays

### Changes (state management)
- **NEW** `mirror-state.js` — ViewState, setView(), fetch orchestration, version gating
- **REWRITE** `mirror-app.js` — removes all direct state mutation, routes through setView()
- **MINOR** `mirror-chart.js` — loading guard in refreshMirrorChart()
- **MINOR** `mirror.html` — script tag + CSS overflow fix
- **MINOR** `server.py` — /api/detections-range endpoint

### Stays (rendering)
- All chart rendering code (candles, markers, session bands, tooltips)
- All feed rendering code
- Sequential time mapping architecture
- Timezone contract and all Phase A timestamp fixes
- WS subscribe handler from Phase A

### Architecture After

```
User Action (click/key/scroll)
       │
       ▼
   setView({ tf?, date?, mode?, day? })
       │
       ├─ day-only? → fast path (no fetch, just scroll)
       │
       ├─ increment version
       ├─ cancel in-flight fetches
       ├─ compute bar range from anchor + lookback
       │
       ▼
   Promise.all([bars, sessions, detections])
       │
       ├─ version stale? → discard (newer setView won)
       │
       ▼
   _syncToMApp() → refreshMirrorChart() + updateFeed() + updateUI()
```

**One path. One gate. No races. No stale data. No whack-a-mole.**
