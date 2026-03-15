/* ═══════════════════════════════════════════════════════════════════════════════
 * validate-chart.js — Lightweight Charts candlestick chart with detection
 *                     markers, session bands, and responsive sizing for
 *                     the Phase 3.5 Validation Mode page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Per-Primitive Marker Styles (unified across tools) ─────────────────── */

const V_MARKER_STYLES = {
  swing_points:        { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#00e5ff' },
  liquidity_sweep:     { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ff9800' },
  mss:                 { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ffeb3b' },
  displacement:        { shape_high: 'square',    shape_low: 'square',   color: '#e040fb' },
  order_block:         { shape_high: 'square',    shape_low: 'square',   color: '#448aff' },
  fvg:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#69f0ae' },
  ote:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#ffb74d' },
  asia_range:          { shape_high: 'square',    shape_low: 'square',   color: '#e91e63' },
  htf_liquidity:       { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#8bc34a' },
  session_liquidity:   { shape_high: 'square',    shape_low: 'square',   color: '#795548' },
  reference_levels:    { shape_high: 'circle',    shape_low: 'circle',   color: '#607d8b' },
};

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _vChartCreated = false;
let _vSessionPrimitive = null;
let _vAllMarkers = [];
let _vCandleTimeSet = null;
let _vCandleTimesArr = null;
let _vResizeObserver = null;

function vWeekRange(weekEntry) {
  if (!weekEntry) return null;
  return { from: toTS(weekEntry.start + 'T00:00:00'), to: toTS(weekEntry.end + 'T23:59:00') };
}

function highlightValidateDayTab(dayStr) {
  const container = document.getElementById('day-tabs');
  if (!container) return;
  container.querySelectorAll('.day-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.day === dayStr);
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands Primitive (ISeriesPrimitive 3-class pattern)
 * ═══════════════════════════════════════════════════════════════════════════════ */

class VSessionBandsRenderer {
  constructor() { this._bands = []; }
  setData(bands) { this._bands = bands; }
  draw(target) {
    target.useMediaCoordinateSpace(scope => {
      const ctx = scope.context;
      const H = scope.mediaSize.height;
      for (const b of this._bands) {
        if (b.x1 == null && b.x2 == null) continue;
        const rawL = b.x1 ?? 0;
        const rawR = b.x2 ?? scope.mediaSize.width;
        const xL = Math.min(rawL, rawR);
        const xR = Math.max(rawL, rawR);
        if (xR < 0 || xL > scope.mediaSize.width) continue;
        // Fill
        ctx.fillStyle = b.color;
        ctx.fillRect(xL, 0, xR - xL, H);
        // Dashed border lines
        ctx.strokeStyle = b.border;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xL, 0); ctx.lineTo(xL, H);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(xR, 0); ctx.lineTo(xR, H);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }
}

class VSessionBandsPaneView {
  constructor() { this._renderer = new VSessionBandsRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'bottom'; }
}

class VSessionBandsPrimitive {
  constructor() {
    this._paneView = new VSessionBandsPaneView();
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._rawBands = [];
  }
  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._requestUpdate = requestUpdate;
  }
  detached() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }
  paneViews() { return [this._paneView]; }
  updateAllViews() {
    if (!this._chart) return;
    const ts = this._chart.timeScale();
    const computed = [];
    for (const b of this._rawBands) {
      const x1 = ts.timeToCoordinate(b.startTS);
      const x2 = ts.timeToCoordinate(b.endTS);
      computed.push({ x1, x2, color: b.color, border: b.border });
    }
    this._paneView._renderer.setData(computed);
  }
  setBands(rawBands) {
    this._rawBands = rawBands;
    if (this._requestUpdate) this._requestUpdate();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chart Creation
 * ═══════════════════════════════════════════════════════════════════════════════ */

function createValidateChart() {
  const container = document.getElementById('chart-container');
  if (!container) return;

  // Clear any existing content (empty state, previous chart)
  container.innerHTML = '';
  _vChartCreated = true;

  const chart = LightweightCharts.createChart(container, {
    layout: {
      background: { type: 'solid', color: '#131722' },
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
      tickMarkFormatter: (time) => {
        const d = new Date(time * 1000);
        const hh = String(d.getUTCHours()).padStart(2, '0');
        const mm = String(d.getUTCMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
      },
    },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
    handleScale: { mouseWheel: true, pinch: true },
    width: container.clientWidth,
    height: container.clientHeight,
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderUpColor: '#26a69a',
    borderDownColor: '#ef5350',
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
  });

  // Session bands primitive
  const sessionPrimitive = new VSessionBandsPrimitive();
  candleSeries.attachPrimitive(sessionPrimitive);

  // Subscribe to visible range changes
  chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
    if (_vScrollSyncActive || !range || range.from == null || range.to == null) return;

    const center = Math.floor((range.from + range.to) / 2);

    if (isHTF(vApp.tf) && _vHTFAllWeeksLoaded && vApp.weeks.length > 0) {
      // Week-level scroll sync on HTF
      for (const w of vApp.weeks) {
        const wStart = toTS(w.start + 'T00:00:00');
        const wEnd = toTS(w.end + 'T23:59:00');
        if (center >= wStart && center <= wEnd && w.week !== (vApp.currentWeek && vApp.currentWeek.week)) {
          vApp.currentWeek = w;
          const picker = document.getElementById('week-picker');
          if (picker) picker.value = w.week;
          break;
        }
      }
      return;
    }

    if (!vApp.currentWeek || !vApp.day) return;
    const days = vApp.currentWeek.forex_days || [];
    for (const dk of days) {
      const r = vDayRange(dk);
      if (center >= r.from && center <= r.to && dk !== vApp.day) {
        vApp.day = dk;
        highlightValidateDayTab(dk);
        break;
      }
    }
  });

  // Resize observer for responsive chart
  if (_vResizeObserver) _vResizeObserver.disconnect();
  _vResizeObserver = new ResizeObserver(() => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  });
  _vResizeObserver.observe(container);

  // Store refs
  vApp.chart = chart;
  vApp.candleSeries = candleSeries;
  _vSessionPrimitive = sessionPrimitive;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initOrRefreshChart — Called when a week is selected
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initOrRefreshChart() {
  if (!_vChartCreated) {
    createValidateChart();
    // Initialize ground truth system after chart is created
    if (typeof initValidateGT === 'function') {
      initValidateGT();
    }
  }
  refreshValidateChart();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * refreshValidateChart — Load candles, markers, session bands for current state
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _vScrollSyncActive = false;

function vDayRange(dayStr) {
  const d = new Date(dayStr + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  const prevDate = d.toISOString().split('T')[0];
  return { from: toTS(prevDate + 'T17:00:00'), to: toTS(dayStr + 'T16:59:00') };
}

function scrollValidateToDay(dayStr) {
  if (!vApp.chart) return;
  _vScrollSyncActive = true;
  if (dayStr) {
    vApp.chart.timeScale().setVisibleRange(vDayRange(dayStr));
  } else {
    vApp.chart.timeScale().fitContent();
  }
  setTimeout(() => { _vScrollSyncActive = false; }, 200);
}

function refreshValidateChart() {
  if (!vApp.chart || !vApp.candleSeries) return;
  if (!vApp.candleData) {
    vApp.candleSeries.setData([]);
    _vAllMarkers = [];
    rebuildValidateMarkers();
    if (_vSessionPrimitive) _vSessionPrimitive.setBands([]);
    updateDetectionCounts();
    return;
  }

  const raw = vApp.candleData[vApp.tf];
  if (!raw || !raw.length) {
    vApp.candleSeries.setData([]);
    _vAllMarkers = [];
    rebuildValidateMarkers();
    if (_vSessionPrimitive) _vSessionPrimitive.setBands([]);
    updateDetectionCounts();
    return;
  }

  // Always load ALL candles for the week (continuous timeline)
  const chartData = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })).filter(b => b.time != null)
    .sort((a, b) => a.time - b.time);

  vApp.candleSeries.setData(chartData);

  _vCandleTimeSet = new Set(chartData.map(c => c.time));
  _vCandleTimesArr = chartData.map(c => c.time);

  // Build markers for ALL days
  _vAllMarkers = buildValidateMarkers();
  rebuildValidateMarkers();

  // Session bands for ALL days (reduced opacity)
  const bands = getValidateSessionBandsForDay(null);
  if (_vSessionPrimitive) {
    _vSessionPrimitive.setBands(bands);
  }

  // Scroll to selected day, or week on HTF, or fit all
  if (vApp.day) {
    scrollValidateToDay(vApp.day);
  } else if (isHTF(vApp.tf) && _vHTFAllWeeksLoaded && vApp.currentWeek) {
    _vScrollSyncActive = true;
    const wr = vWeekRange(vApp.currentWeek);
    if (wr) vApp.chart.timeScale().setVisibleRange(wr);
    setTimeout(() => { _vScrollSyncActive = false; }, 200);
  } else {
    vApp.chart.timeScale().fitContent();
  }

  requestAnimationFrame(() => {
    if (_vSessionPrimitive && _vSessionPrimitive._requestUpdate) {
      _vSessionPrimitive._requestUpdate();
    }
    requestAnimationFrame(() => {
      if (_vSessionPrimitive && _vSessionPrimitive._requestUpdate) {
        _vSessionPrimitive._requestUpdate();
      }
    });
  });

  updateDetectionCounts();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Build Markers from Detection Data
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildValidateMarkers() {
  if (!vApp.detectionData || !vApp.detectionData.detections_by_primitive) return [];
  if (!_vCandleTimeSet || !_vCandleTimesArr) return [];

  const markers = [];

  for (const [primName, byTf] of Object.entries(vApp.detectionData.detections_by_primitive)) {
    const style = V_MARKER_STYLES[primName];
    const primColor = vPrimColor(primName);

    const tfDets = byTf[vApp.tf] || byTf['global'] || [];

    for (const det of tfDets) {
      const barTime = findValidateNearestCandleTime(det.time);
      if (barTime == null) continue;

      const isBullish = det.direction === 'bullish' || det.direction === 'high';
      const isBearish = det.direction === 'bearish' || det.direction === 'low';

      markers.push({
        time: barTime,
        position: isBearish ? 'aboveBar' : 'belowBar',
        shape: style ? (isBearish ? style.shape_high : style.shape_low) : (isBearish ? 'arrowDown' : 'arrowUp'),
        color: style ? style.color : primColor,
        size: 1,
        text: '',
        _primitive: primName,
        _detId: det.id,
      });
    }
  }

  // Sort by time (required by LWC)
  markers.sort((a, b) => a.time - b.time);

  // Deduplicate same time+position+primitive
  const seen = new Set();
  return markers.filter(m => {
    const k = `${m.time}_${m.position}_${m._primitive}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * rebuildValidateMarkers — Filter by toggle state and apply
 * ═══════════════════════════════════════════════════════════════════════════════ */

function rebuildValidateMarkers() {
  if (!vApp.candleSeries) return;

  const filtered = _vAllMarkers.filter(m => {
    if (vApp.primitiveToggles[m._primitive] === false) return false;
    return true;
  });

  // Sort by time (required by LWC)
  filtered.sort((a, b) => a.time - b.time);

  try {
    vApp.candleSeries.setMarkers(filtered);
  } catch (e) {
    console.warn('setMarkers error:', e);
  }

  // Rebuild GT rings after markers are updated
  if (typeof rebuildVGTRings === 'function') {
    rebuildVGTRings();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Find Nearest Candle Time for a Detection
 * ═══════════════════════════════════════════════════════════════════════════════ */

function findValidateNearestCandleTime(detTime) {
  if (!_vCandleTimeSet || !_vCandleTimesArr) return null;

  const ts = toTS(detTime);
  if (ts == null) return null;

  // Exact match
  if (_vCandleTimeSet.has(ts)) return ts;

  // Find nearest candle time (within 15 min for 1m, 4h for HTF, 1h for other LTFs)
  const maxDiff = vApp.tf === '1m' ? 900 : isHTF(vApp.tf) ? 14400 : 3600;
  let best = null;
  let bestDiff = Infinity;
  for (const ct of _vCandleTimesArr) {
    const diff = Math.abs(ct - ts);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = ct;
    }
  }
  return (bestDiff <= maxDiff) ? best : null;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands for Day
 * ═══════════════════════════════════════════════════════════════════════════════ */

function getValidateSessionBandsForDay(dayKey) {
  if (vApp.tf === '4H') return [];
  if (!vApp.sessionData) return [];
  const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
  const htf = isHTF(vApp.tf);

  return vApp.sessionData
    .filter(b => VISIBLE_SESSIONS.has(b.session) && (!dayKey || b.forex_day === dayKey))
    .map(b => {
      let color = b.color;
      let border = b.border;
      // Reduce opacity on HTF week view to prevent solid color stacking
      if (htf && !dayKey) {
        color = color.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.4).toFixed(2) + ')');
        border = border.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.5).toFixed(2) + ')');
      }
      return {
        startTS: toTS(b.start_time),
        endTS: toTS(b.end_time),
        color,
        border,
        session: b.session,
        label: b.label,
      };
    })
    .filter(b => b.startTS != null && b.endTS != null);
}
