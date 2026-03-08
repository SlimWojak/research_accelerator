# Chart Rebuild Spec v2 — Native Multi-TF + NY Time
# ===================================================
# This file defines all shared changes every chart HTML file must implement.

## CRITICAL CHANGES

### 1. Timestamp Handling
All timestamps are now in NY time (EST, UTC-5). Format: "2024-01-09T08:15:00" (no Z suffix).

The toTS() function MUST be updated. The old version appended 'Z' (treating as UTC).
Since LightweightCharts just needs a Unix timestamp for the x-axis, and we want the 
x-axis to show NY time, we treat the NY time string AS IF it were UTC for chart display.
This is the standard trick for displaying local time on LightweightCharts.

```js
function toTS(s) {
  if (!s) return null;
  // NY time string like "2024-01-09T08:15:00"
  // Treat as-is (pretend UTC) so chart x-axis shows NY time
  const clean = s.includes('T') ? s : s.replace(' ', 'T');
  // Remove any trailing Z if present
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}
```

### 2. Per-TF Detection Data Files
Each chart now loads TF-specific detection data:
- FVG: `fvg_data_{tf}.json` (not `fvg_data.json`)
- Swings: `swing_data_{tf}.json`
- Displacement: `displacement_data_{tf}.json`
- OB: `ob_data_{tf}.json`
- NY Windows: `ny_windows_data_{tf}.json`

When TF changes, the chart must reload BOTH candles AND detection data for that TF.

### 3. TF-Specific Thresholds
Threshold sweep values differ per TF. They come from the detection JSON's `thresholds` field.
The sidebar threshold buttons must rebuild when TF changes.

### 4. Session Boundary Markers
Load `session_boundaries.json` once. For the current day, draw vertical bands/regions:
- Asia (purple): 19:00-00:00 NY
- LOKZ (blue): 02:00-05:00 NY
- NYOKZ (yellow): 07:00-10:00 NY
- NY-A (red, subtle): 08:00-09:00 NY
- NY-B (teal, subtle): 10:00-11:00 NY

Implementation: Use a custom ISeriesPrimitive similar to FVG zones but for vertical bands.
Each band spans the full price range of the chart, from session start_time to end_time.
Use the colors from session_boundaries.json data.

### 5. Session Labels in Sidebar
Change from UTC hours to NY time descriptions:
- Asia → "Asia 19:00-00:00"
- London → "LOKZ 02:00-05:00"
- NY → "NYOKZ 07:00-10:00"
- Other → "Other"

### 6. Detection Label Update
The chart info bar should say "Native {TF} detection" not "Detections on 1m · overlaid on selected TF"

### 7. Candle Data Format
Candle JSON files now have bars with field `time` (NY time string) instead of `t`.
OHLC fields remain: open, high, low, close (full names now, not o/h/l/c).
Also has: session, forex_day, atr, ny_window_a, ny_window_b.

### 8. FVG Data Format (per-TF JSON)
FVG objects now have full field names:
- detect_time (not dt), anchor_time, type (not ty), gap_pips (not gap),
- top, bottom (not bot), ce, forex_day (not fd), session (not ses),
- vi_confluent, ce_touched_time (not ce_t), boundary_closed_time (not bc_t)
- tf (the timeframe label)

### 9. Swing Data Format
- time, type, price, strength, height_pips, forex_day, session, tf, bar_index

### 10. Default TF
Default remains 5m. Default threshold should be the middle value of the TF's threshold array.

## SESSION BOUNDARY PRIMITIVE (shared code for all charts)

```js
// ═════════════════════════════════════════════════════════════
// Session Boundary Primitive — draws vertical colored bands
// ═════════════════════════════════════════════════════════════
class SessionBandsRenderer {
  constructor() { this._bands = []; }
  setBands(bands) { this._bands = bands; }
  draw(target) {
    if (!this._bands.length) return;
    target.useMediaCoordinateSpace(scope => {
      const ctx = scope.context;
      const H = scope.mediaSize.height;
      for (const b of this._bands) {
        if (b.x1 == null && b.x2 == null) continue;
        const xL = b.x1 != null ? b.x1 : 0;
        const xR = b.x2 != null ? b.x2 : scope.mediaSize.width;
        if (xR - xL < 0.5) continue;
        ctx.save();
        ctx.fillStyle = b.color;
        ctx.fillRect(xL, 0, xR - xL, H);
        // Left border line
        ctx.strokeStyle = b.border;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(xL, 0); ctx.lineTo(xL, H);
        ctx.stroke();
        ctx.restore();
      }
    });
  }
  drawBackground(target) {}
}

class SessionBandsPaneView {
  constructor() { this._renderer = new SessionBandsRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'bottom'; }
}

class SessionBandsPrimitive {
  constructor() {
    this._rawBands = [];
    this._paneView = new SessionBandsPaneView();
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }
  attached({ chart, series, requestUpdate }) {
    this._chart = chart; this._series = series; this._requestUpdate = requestUpdate;
  }
  detached() { this._chart = this._series = this._requestUpdate = null; }
  updateAllViews() {
    if (!this._chart) return;
    const ts = this._chart.timeScale();
    const computed = [];
    for (const b of this._rawBands) {
      try {
        const x1 = ts.timeToCoordinate(b.startTS);
        const x2 = ts.timeToCoordinate(b.endTS);
        if (x1 == null && x2 == null) continue;
        computed.push({ x1, x2, color: b.color, border: b.border });
      } catch(_) {}
    }
    this._paneView._renderer.setBands(computed);
  }
  paneViews() { return [this._paneView]; }
  setBands(rawBands) {
    this._rawBands = rawBands;
    if (this._requestUpdate) this._requestUpdate();
  }
  injectRefs(chart, series) {
    if (!this._chart) this._chart = chart;
    if (!this._series) this._series = series;
  }
}
```

## FULL UPDATE FLOW (pseudocode for each chart)

```
async function fullUpdate() {
  1. Load candle JSON for current day
  2. Load detection JSON for current TF (e.g., fvg_data_5m.json)
  3. Load levels_data.json (once)
  4. Load session_boundaries.json (once)
  5. Render candles from current TF
  6. Render session bands for current day
  7. Render detection overlays from TF-specific data
  8. Update threshold buttons from TF-specific thresholds
  9. Update sidebar stats
}

TF toggle click → {
  Set app.tf
  Clear cached detection data
  fullUpdate()
}
```

## SHARED CSS ADDITION

```css
/* Session legend items */
.ses-legend {
  display: flex; gap: 8px; flex-wrap: wrap; padding: 3px 0;
}
.ses-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; color: var(--muted); font-family: var(--mono);
}
.ses-dot {
  width: 8px; height: 8px; border-radius: 1px; flex-shrink: 0;
}
```

## FILE LISTING
- index.html — Update intro text to mention native detection + NY time
- fvg.html — FVG calibration (main chart)
- swings.html — Swing point calibration
- asia.html — Asia range + session display
- displacement.html — Displacement candle calibration
- ny-windows.html — NY reversal window events
- ob-staleness.html — Order Block staleness calibration
