# Chart Code Patterns Reference — Phase 3 Worker Guide

> Extracted from `site/displacement.html`, `site/fvg.html`, `site/swings.html`, `site/ny-windows.html`, and `site/BUILDSPEC.md`.
> This document captures the **exact patterns** that Phase 3 chart workers MUST follow for consistency.

---

## A. DATA LOADING PATTERN

### JSON File Naming Convention
```
candles_{YYYY-MM-DD}.json       → per-day candle data
{primitive}_data_{tf}.json      → per-TF detection data (e.g., fvg_data_5m.json, displacement_data_1m.json)
{primitive}_data.json           → alias for 1m (legacy, same content as _1m)
session_boundaries.json         → shared session boundary data (loaded once)
levels_data.json                → PDH/PDL per day (loaded once)
```

### Fetch Pattern (displacement.html)
```js
// Per-TF detection data with caching
async function loadDisplacementData(tf) {
  if (state.dispDataCache[tf]) {
    state.dispData = state.dispDataCache[tf];
    return;
  }
  const resp = await fetch(`displacement_data_${tf}.json`);
  const data = await resp.json();
  state.dispDataCache[tf] = data;
  state.dispData = data;
}
```

### Fetch Pattern (fvg.html — no cache, reload on TF change)
```js
async function loadData() {
  // Static data — load once, guard with null check
  if (!app.levelsData) {
    try {
      const lr = await fetch('levels_data.json');
      app.levelsData = await lr.json();
    } catch (e) {
      console.warn('Could not load levels data:', e);
      app.levelsData = {};
    }
  }

  // Session boundaries — load once
  if (!app.sessionBands) {
    try {
      const sr = await fetch('session_boundaries.json');
      app.sessionBands = await sr.json();
    } catch (e) {
      console.warn('Could not load session boundaries:', e);
      app.sessionBands = [];
    }
  }

  // Per-TF detection data — reload when TF changes
  const fvgUrl = `fvg_data_${app.tf}.json`;
  try {
    const fr = await fetch(fvgUrl);
    app.fvgData = await fr.json();
  } catch (e) {
    console.warn('Could not load FVG data for', app.tf, e);
    app.fvgData = { fvgs: [], thresholds: [], stats: {} };
  }

  // Per-day candle data
  try {
    const cr = await fetch('candles_' + app.day + '.json');
    app.candleData = await cr.json();
  } catch (e) {
    console.warn('Could not load candles for', app.day, e);
    app.candleData = null;
  }
}
```

### Data Reload Triggers
| Event | Reloads |
|-------|---------|
| TF switch (1m/5m/15m) | Detection data for new TF. Candle data already has all TFs per day. |
| Day switch (tab click) | Candle data (`candles_{day}.json`). Detection data is pre-loaded for all days. |
| Threshold/param change | NO reload — just re-filter existing data and re-render. |

### Candle JSON Structure (per-day file)
```json
{
  "1m": [{"time": "2024-01-09T00:00:00", "open": 1.09123, "high": 1.09135, "low": 1.09110, "close": 1.09128}, ...],
  "5m": [...],
  "15m": [...]
}
```

---

## B. CHART INITIALIZATION PATTERN

### Chart Creation (displacement.html pattern — explicit sizing)
```js
const container = document.getElementById('chart-container');
container.innerHTML = '';

chart = LightweightCharts.createChart(container, {
  layout: {
    background: { color: '#131722' },
    textColor: '#d1d4dc',
    fontSize: 11,
    fontFamily: "'IBM Plex Mono', monospace",
  },
  grid: {
    vertLines: { color: '#1e222d' },
    horzLines: { color: '#1e222d' },
  },
  crosshair: {
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: { color: '#4a4e5a', width: 1, style: 2 },
    horzLine: { color: '#4a4e5a', width: 1, style: 2 },
  },
  rightPriceScale: {
    borderColor: '#2a2e39',
    scaleMargins: { top: 0.05, bottom: 0.05 },
  },
  timeScale: {
    borderColor: '#2a2e39',
    timeVisible: true,
    secondsVisible: false,
    // Optional custom tick formatter:
    tickMarkFormatter: (time) => {
      const d = new Date(time * 1000);
      const hh = String(d.getUTCHours()).padStart(2,'0');
      const mm = String(d.getUTCMinutes()).padStart(2,'0');
      return `${hh}:${mm}`;
    },
  },
  handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
  handleScale: { mouseWheel: true, pinch: true },
  width: container.clientWidth,
  height: container.clientHeight,
});
```

### Chart Creation (fvg.html pattern — autoSize)
```js
app.chart = LightweightCharts.createChart(el, {
  autoSize: true,   // <-- alternative to explicit width/height
  layout: {
    background: { type: 'solid', color: '#131722' },
    textColor: '#787b86',
    fontSize: 11,
    fontFamily: "'IBM Plex Mono', monospace",
  },
  // ... same grid, crosshair, scale options
});
```

### Candlestick Series (IDENTICAL across all pages)
```js
candleSeries = chart.addCandlestickSeries({
  upColor:         '#26a69a',
  downColor:       '#ef5350',
  borderUpColor:   '#26a69a',
  borderDownColor: '#ef5350',
  wickUpColor:     '#26a69a',
  wickDownColor:   '#ef5350',
});
```

### Chart Resize (displacement.html — ResizeObserver)
```js
const ro = new ResizeObserver(() => {
  chart.applyOptions({
    width: container.clientWidth,
    height: container.clientHeight,
  });
});
ro.observe(container);
```
> fvg.html uses `autoSize: true` instead, which handles resize internally.

### Setting Candle Data
```js
const data = raw.map(c => ({
  time: toTS(c.time),
  open:  c.open,
  high:  c.high,
  low:   c.low,
  close: c.close,
})).filter(b => b.time != null)
  .sort((a, b) => a.time - b.time);

candleSeries.setData(data);
```

### Fit Content After Data Load
```js
chart.timeScale().fitContent();
```

---

## C. OVERLAY RENDERING PATTERN

### ISeriesPrimitive Architecture (3-class pattern — used in BOTH files)

Every custom overlay follows this exact 3-class structure:

```
┌──────────────────────┐
│  XxxRenderer         │  — draws on Canvas2D via draw() / drawBackground()
│  .setData(computed)  │
│  .draw(target)       │  — target.useMediaCoordinateSpace(scope => { ... })
└──────────────────────┘
         ↑
┌──────────────────────┐
│  XxxPaneView         │  — returns renderer + zOrder
│  .renderer()         │
│  .zOrder()           │  — 'bottom' (session bands) or 'normal' (FVG zones)
└──────────────────────┘
         ↑
┌──────────────────────┐
│  XxxPrimitive        │  — ISeriesPrimitive implementation
│  .attached(refs)     │  — receives {chart, series, requestUpdate}
│  .detached()         │
│  .updateAllViews()   │  — converts raw data → pixel coords each frame
│  .paneViews()        │  — returns [paneView]
│  .setXxx(rawData)    │  — public API to update data, calls requestUpdate()
│  .injectRefs(c, s)   │  — fallback if attached() hasn't fired
└──────────────────────┘
```

**Attaching to series:**
```js
const primitive = new XxxPrimitive();
candleSeries.attachPrimitive(primitive);
```

### SessionBandsPrimitive (SHARED — identical code in displacement.html and fvg.html)

**Purpose:** Draws vertical colored session bands (Asia, LOKZ, NYOKZ).

```js
// In updateAllViews() — convert time → x pixel coordinates
const ts = this._chart.timeScale();
for (const b of this._rawBands) {
  const x1 = ts.timeToCoordinate(b.startTS);
  const x2 = ts.timeToCoordinate(b.endTS);
  computed.push({ x1, x2, color: b.color, border: b.border });
}

// In draw() — render colored rectangles + dashed border lines
target.useMediaCoordinateSpace(scope => {
  const ctx = scope.context;
  const H = scope.mediaSize.height;
  for (const b of bands) {
    ctx.fillStyle = b.color;
    ctx.fillRect(xL, 0, xR - xL, H);
    ctx.strokeStyle = b.border;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(xL, 0); ctx.lineTo(xL, H);
    ctx.stroke();
  }
});
```
- **zOrder:** `'bottom'` (renders behind candles)
- **Input data:** `{ startTS, endTS, color, border }` from `session_boundaries.json`

### FvgZonesPrimitive (fvg.html only)

**Purpose:** Draws colored rectangles for FVG zones (bullish/bearish, with state variants).

```js
// In updateAllViews() — converts time + price → pixel coords
const x1 = ts.timeToCoordinate(z.startTS);
const x2 = z.endTS != null ? ts.timeToCoordinate(z.endTS) : null;
const y1 = ps.priceToCoordinate(z.top);      // <-- USES PRICE SCALE
const y2 = ps.priceToCoordinate(z.bot);

// In draw() — render with state-dependent styling:
// Active:  fillStyle = 'rgba(38,166,154,0.22)' + solid border
// CE:      fillStyle = 'rgba(38,166,154,0.06)' + dashed border
// BC:      fillStyle = 'rgba(38,166,154,0.10)' + dashed border
// IFVG:    flipped color + dashed border + "IF" text label
// BPR:     purple fill rgba(156,39,176,0.25) + "BPR" text label
```
- **zOrder:** `'normal'` (renders at candle level)
- **Input data:** `{ startTS, endTS, top, bot, type, state }`

### Detection Markers (displacement.html — uses built-in markers API)

```js
// Build markers array, then:
candleSeries.setMarkers(markers);

// Marker shape for each type:
// Bullish displacement: { position: 'belowBar', shape: 'arrowUp', color: GRADE_COLOR }
// Bearish displacement: { position: 'aboveBar', shape: 'arrowDown', color: GRADE_COLOR }
// FVG indicator:        { position: 'belowBar', shape: 'circle', size: 0, text: '★' }
// Order Block:          { position: 'belowBar/aboveBar', shape: 'square', text: 'OB' }
// Override:             { shape: 'circle', color: '#f7c548' }
```

### Grade-Based Color Scheme
```js
const GRADE_COLORS_BULL = { STRONG: '#00e5d4', VALID: '#26a69a', WEAK: '#5a5f6e' };
const GRADE_COLORS_BEAR = { STRONG: '#ff6b6b', VALID: '#ef5350', WEAK: '#5a5f6e' };
```

### Price Lines (fvg.html — PDH/PDL levels)
```js
app.pdhLine = app.series.createPriceLine({
  price: lvl.pdh,
  color: 'rgba(247,197,72,0.55)',
  lineWidth: 1,
  lineStyle: LightweightCharts.LineStyle.Dashed,
  axisLabelVisible: true,
  title: 'PDH',
});
```

### requestAnimationFrame Pattern for Zone Updates
```js
// After fitContent, wait for layout to settle before rendering overlays:
app.chart.timeScale().fitContent();
requestAnimationFrame(() => {
  setTimeout(() => {
    renderZones();
    renderSessionBands();
  }, 50);
});

// Force multiple rAF updates for primitives:
requestAnimationFrame(() => {
  if (primitive._requestUpdate) primitive._requestUpdate();
  requestAnimationFrame(() => {
    if (primitive._requestUpdate) primitive._requestUpdate();
  });
});
```

### Subscribe to Scale Changes (fvg.html)
```js
app.chart.timeScale().subscribeVisibleTimeRangeChange(() => {
  if (app.primitive._requestUpdate) app.primitive._requestUpdate();
  if (app.sessionPrimitive._requestUpdate) app.sessionPrimitive._requestUpdate();
});
```

---

## D. INTERACTION PATTERNS

### Timeframe Switching
```js
// displacement.html: event delegation on container
document.getElementById('tf-toggle').addEventListener('click', async e => {
  const btn = e.target.closest('.tf-btn');
  if (!btn) return;
  const tf = btn.dataset.tf;
  if (tf === state.tf) return;
  state.tf = tf;
  document.querySelectorAll('.tf-btn').forEach(b => b.classList.toggle('active', b.dataset.tf === tf));
  await loadDisplacementData(tf);  // load new detection data
  refresh();                        // full re-render
});

// fvg.html: individual button listeners
document.querySelectorAll('.tf-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.tf === app.tf) return;
    app.tf = btn.dataset.tf;
    app.fvgData = null;     // Force reload
    app.threshold = null;   // Reset threshold
    document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fullUpdate(true);       // loading overlay + full reload
  });
});
```

### Day Navigation (tab buttons)
```js
// displacement.html: rebuild tabs + set active
function renderDayTabs() {
  const el = document.getElementById('day-tabs');
  el.innerHTML = '';
  for (const d of DAYS) {
    const btn = document.createElement('button');
    btn.className = 'day-tab' + (d.key === state.day ? ' active' : '');
    btn.textContent = d.label;
    btn.addEventListener('click', () => {
      state.day = d.key;
      refresh();
    });
    el.appendChild(btn);
  }
}

// fvg.html: static HTML tabs + event delegation
document.querySelectorAll('.day-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    if (tab.dataset.day === app.day) return;
    app.day = tab.dataset.day;
    app.candleData = null;   // force candle reload for new day
    document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    fullUpdate(true);
  });
});
```

### Threshold / Parameter Controls
```js
// displacement.html: button groups for discrete params (ATR mult, body ratio)
for (const v of ATR_MULTS) {
  const btn = document.createElement('button');
  btn.className = 'param-btn' + (Math.abs(v - state.atr) < 0.001 ? ' active-atr' : '');
  btn.textContent = formatAtr(v);
  btn.addEventListener('click', () => {
    state.atr = v;
    refresh();  // no data reload, just re-filter + re-render
  });
}

// fvg.html: threshold buttons built from data
for (const t of thresholds) {
  btn.addEventListener('click', () => {
    app.threshold = t;
    renderZones();       // re-filter existing data
    renderSidebar();
    renderStatsPanel();
  });
}
```

### Toggle Buttons (derived overlays)
```js
// Pattern: toggle boolean state, update button text + styling, re-render
document.getElementById('ob-toggle').addEventListener('click', () => {
  state.showOB = !state.showOB;
  const btn = document.getElementById('ob-toggle');
  btn.textContent = state.showOB ? 'Hide Order Blocks' : 'Show Order Blocks';
  btn.style.background = state.showOB ? 'rgba(41,98,255,0.2)' : '';
  btn.style.color = state.showOB ? '#2962ff' : '';
  renderChart();
});
```

### State Management Pattern

**displacement.html** — single `state` object:
```js
let state = {
  tf: '5m',
  day: '2024-01-09',
  atr: 1.5,
  br: 0.60,
  mode: 'and',
  closeGate: true,
  singleOnly: true,
  dispData: null,
  dispDataCache: {},     // keyed by TF
  candlesByDay: {},      // keyed by day
  showOB: false,
  sessionBoundaries: null,
};
```

**fvg.html** — single `app` object:
```js
const app = {
  day: '2024-01-09',
  tf: '5m',
  threshold: null,
  fvgData: null,
  levelsData: null,
  candleData: null,
  sessionBands: null,
  chart: null,
  series: null,
  primitive: null,
  sessionPrimitive: null,
  pdhLine: null,
  pdlLine: null,
  showIFVG: false,
  showBPR: false,
};
```

**Pattern:** All state in one global object. Chart/series refs also stored there. No classes, no modules.

### Refresh Hierarchy
```
refresh()                  — full UI update
├── renderParamButtons()   — rebuild sidebar controls
├── renderDayTabs()        — rebuild day tabs
├── renderSidebarStats()   — update count display
├── renderHeatmap()        — update param heatmap
├── renderStatsPanel()     — update bottom stats
├── renderChartInfoBar()   — update info labels
└── renderChart()          — re-set candle data + markers + session bands
    ├── candleSeries.setData(data)
    ├── renderSessionBands()
    ├── candleSeries.setMarkers(markers)
    └── chart.timeScale().fitContent()
```

---

## E. CSS PATTERNS

### Design Tokens (from BUILDSPEC.md — canonical)
```css
:root {
  --bg:      #0a0e17;       /* dark navy background */
  --surface: #131722;       /* chart bg, same as TradingView */
  --surface2: #1e222d;      /* card/panel bg */
  --border:  #2a2e39;       /* borders */
  --text:    #d1d4dc;       /* primary text (also --text-primary) */
  --muted:   #787b86;       /* muted text (also --text-muted) */
  --teal:    #26a69a;       /* bullish/positive */
  --red:     #ef5350;       /* bearish/negative */
  --blue:    #2962ff;       /* selection/active */
  --yellow:  #f7c548;       /* warning/highlight */
  --purple:  #9c27b0;       /* VI confluence/special */
  --font:    'IBM Plex Sans', system-ui, sans-serif;
  --mono:    'IBM Plex Mono', monospace;
}
```

> ⚠️ Variable names vary slightly between pages (`--text-primary` vs `--text`, `--accent-teal` vs `--teal`). **Prefer the shorter names** (`--text`, `--teal`, etc.) from fvg.html as the cleaner convention.

### Layout Structure
```
┌─────────────────────────────────────────────────────┐
│ HEADER (44-48px, flex, surface bg, border-bottom)   │
│  [Title] [Primitive Badge] [TF Toggle] [Nav Links]  │
├─────────────────────────────────────────────────────┤
│ CALLOUT (optional, blue-left-bordered)              │
├────────────┬────────────────────────────────────────┤
│ DAY TABS   │ (full width, surface bg)               │
├────────────┤────────────────────────────────────────┤
│ SIDEBAR    │ CHART AREA                             │
│ 236-248px  │  ┌─ chart-info-bar ──────────────────┐ │
│            │  │ [TF label] [session legend]        │ │
│ .s-sec     │  ├────────────────────────────────────┤ │
│ sections   │  │                                    │ │
│ with       │  │   CHART (flex: 1)                  │ │
│ border-    │  │   #chart-container / #chartEl      │ │
│ bottom     │  │                                    │ │
│            │  ├────────────────────────────────────┤ │
│            │  │ STATS PANEL (bottom, flex-shrink:0)│ │
│            │  └────────────────────────────────────┘ │
├────────────┴────────────────────────────────────────┤
│ FOOTER (surface bg, border-top, 7px padding)        │
└─────────────────────────────────────────────────────┘
```

### Key CSS Patterns

**Full viewport, no scroll:**
```css
html, body { height: 100%; overflow: hidden; }
.app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
```

**Sidebar:**
```css
.sidebar {
  width: 236px;             /* 236-248px depending on page */
  flex-shrink: 0;
  background: var(--surface);   /* or var(--surface2) */
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.sidebar-section {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}
```

**Chart wrapper (flex: 1, position: relative for overlays):**
```css
.chart-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 0;          /* critical for flex children */
}
#chart-container {
  width: 100%;
  height: 100%;
}
```

**TF Buttons:**
```css
.tf-btn {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 3px 10px;       /* or 5px 0 with flex:1 */
  cursor: pointer;
}
.tf-btn.active { background: var(--blue); color: #fff; border-color: var(--blue); }
/* OR (displacement variant): */
.tf-btn.active { color: var(--surface); background: var(--accent-red); }
```

**Day Tabs:**
```css
.day-tab {
  font-size: 11-12px;
  color: var(--muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8-10px 14px;
  cursor: pointer;
}
.day-tab.active { color: var(--blue); border-bottom-color: var(--blue); }
/* OR: color: var(--red); border-bottom-color: var(--red); */
```

**Loading Overlay:**
```css
.loading-overlay {
  position: absolute;
  inset: 0;
  background: var(--surface);   /* or rgba(10,14,23,0.8) */
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.loading-overlay.hidden { display: none; }
```

**Stat Cards (displacement.html):**
```css
.stats-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.stat-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 10px;
}
.stat-val { font-family: var(--mono); font-size: 18px; font-weight: 500; }
.stat-lbl { font-size: 10px; color: var(--muted); text-transform: uppercase; }
```

**Stat Rows (fvg.html — simpler):**
```css
.sr { display: flex; justify-content: space-between; align-items: baseline; padding: 3px 0; font-size: 12px; }
.sk { color: var(--muted); }
.sv { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.sv.bull { color: var(--teal); }
.sv.bear { color: var(--red); }
```

---

## F. KEY UTILITY FUNCTIONS

### toTS() — Timestamp Conversion (IDENTICAL in all files)
```js
function toTS(s) {
  if (!s) return null;
  // NY time string like "2024-01-09T08:15:00"
  // Treat as-is (pretend UTC) so chart x-axis shows NY time
  const clean = s.includes('T') ? s : s.replace(' ', 'T');
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}
```
> **Critical:** All time strings in the JSON are NY-local. We append 'Z' to trick `Date` into treating them as UTC so the chart x-axis displays NY time without timezone offset. This is intentional.

### formatTime() / tickMarkFormatter
```js
// Custom time axis formatting (displacement.html)
tickMarkFormatter: (time) => {
  const d = new Date(time * 1000);
  const hh = String(d.getUTCHours()).padStart(2,'0');
  const mm = String(d.getUTCMinutes()).padStart(2,'0');
  return `${hh}:${mm}`;
},
```
> fvg.html omits this (uses LWC default formatter).

### p5() — 5-Decimal Price Format (fvg.html)
```js
function p5(n) { return Number(n).toFixed(5); }
```

### dayLabel() — Day Key → Display Label
```js
function dayLabel(k) { return DAYS.find(d => d.key === k)?.label || k; }
```

### comboKey() — Param Combination Key (displacement.html)
```js
function comboKey(atr, br) {
  const atrStr = (atr === Math.floor(atr)) ? atr.toFixed(1) : String(atr);
  return `atr${atrStr}_br${String(br)}`;
}
```

### threshKey() — Threshold Key (fvg.html)
```js
function threshKey(t) { return t.toFixed(1); }
```

---

## G. SHARED CONSTANTS

### Days Array (IDENTICAL across all pages)
```js
const DAYS = [
  { key: '2024-01-08', label: 'Mon Jan 8'  },
  { key: '2024-01-09', label: 'Tue Jan 9'  },
  { key: '2024-01-10', label: 'Wed Jan 10' },
  { key: '2024-01-11', label: 'Thu Jan 11' },
  { key: '2024-01-12', label: 'Fri Jan 12' },
];
```

### Session Labels
```js
const SES_LABELS = {
  asia:  'Asia 19:00–00:00',
  lokz:  'LOKZ 02:00–05:00',
  nyokz: 'NYOKZ 07:00–10:00',
  other: 'Other',
};
```

### Color Constants
```
Bullish (active):    #26a69a   / rgba(38,166,154,0.22) fill
Bearish (active):    #ef5350   / rgba(239,83,80,0.22) fill
Bullish (faded/CE):  rgba(38,166,154,0.06)
Bearish (faded/CE):  rgba(239,83,80,0.06)
BPR/special:         #9c27b0   / rgba(156,39,176,0.25)
FVG star:            #f7c548
Selection/active UI: #2962ff
Stale/dimmed:        #5a5f6e or rgba opacity 0.3
```

---

## H. BOOT SEQUENCE PATTERN

### displacement.html
```js
async function loadData() {
  // 1. Load session boundaries (once)
  const [sessionResp] = await Promise.all([fetch('session_boundaries.json')]);
  state.sessionBoundaries = await sessionResp.json();

  // 2. Load detection data for default TF
  await loadDisplacementData(state.tf);

  // 3. Load candle data for ALL 5 days in parallel
  await Promise.all(DAYS.map(async d => {
    const resp = await fetch(`candles_${d.key}.json`);
    state.candlesByDay[d.key] = await resp.json();
  }));

  // 4. Create chart + hide loader + full refresh
  createChart();
  document.getElementById('loading-overlay').classList.add('hidden');
  refresh();
}

loadData().catch(err => {
  console.error('Failed to load data:', err);
  // Show error in chart container
});
```

### fvg.html
```js
(async function boot() {
  initChart();          // create chart FIRST (before data)
  await fullUpdate(false);  // load data + render all
})();
```

> **Key difference:** displacement.html creates the chart inside `loadData()` after data arrives. fvg.html creates the chart first, then loads data. The fvg.html pattern is cleaner — **prefer it for new pages**.

---

## I. TOOLTIP PATTERN (fvg.html)

```js
// Fixed-position tooltip element in DOM: <div id="tooltip"></div>
// Shown on mousemove when cursor is inside a zone's pixel bounds
wrap.addEventListener('mousemove', e => {
  // Hit-test each zone's pixel bounds
  for (const fvg of zones) {
    const x1 = ts.timeToCoordinate(toTS(fvg.detect_time));
    const y1 = series.priceToCoordinate(fvg.top);
    // ... check if mouse is inside rectangle
  }
});
// Position tooltip near cursor, clamp to viewport edges
tipEl.style.left = tx + 'px';
tipEl.style.top  = ty + 'px';
```

---

## J. CDN DEPENDENCY

```html
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
```
- Version: **4.1.3** (pinned, do not upgrade)
- Global: `LightweightCharts`
- Key APIs: `createChart()`, `addCandlestickSeries()`, `series.attachPrimitive()`, `series.setMarkers()`, `series.createPriceLine()`, `timeScale().fitContent()`, `timeScale().subscribeVisibleTimeRangeChange()`

---

## K. CHECKLIST FOR NEW CHART PAGES

1. [ ] Include Perplexity attribution in `<head>` and `<footer>`
2. [ ] Load Google Fonts: IBM Plex Sans + IBM Plex Mono
3. [ ] Load Lightweight Charts v4.1.3 from CDN
4. [ ] Use CSS custom properties from design tokens
5. [ ] Layout: header → callout → day-tabs → main (sidebar + chart-area) → footer
6. [ ] State in single global object (`state` or `app`)
7. [ ] Implement `toTS()` for timestamp conversion
8. [ ] Create chart with standard options (dark theme, grid, crosshair)
9. [ ] Candlestick series with standard colors
10. [ ] Attach SessionBandsPrimitive to series
11. [ ] Data loading: static data once, detection data per-TF, candles per-day
12. [ ] Day tabs with `.active` class toggle
13. [ ] TF buttons with `.active` class toggle
14. [ ] Loading overlay with `.hidden` toggle
15. [ ] `fitContent()` after data load
16. [ ] ResizeObserver or `autoSize: true`
17. [ ] Stats panel at bottom
18. [ ] Session legend in chart info bar
