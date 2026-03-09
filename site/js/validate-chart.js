/* ═══════════════════════════════════════════════════════════════════════════════
 * validate-chart.js — Lightweight Charts candlestick chart with detection
 *                     markers, session bands, and responsive sizing for
 *                     the Phase 3.5 Validation Mode page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _vChartCreated = false;
let _vSessionPrimitive = null;
let _vAllMarkers = [];         // All built markers (unfiltered) for current day/tf
let _vCandleTimeSet = null;    // Current candle time set
let _vCandleTimesArr = null;   // Current candle times array
let _vResizeObserver = null;

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
        if (b.x1 == null || b.x2 == null) continue;
        const xL = Math.min(b.x1, b.x2);
        const xR = Math.max(b.x1, b.x2);
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
  chart.timeScale().subscribeVisibleTimeRangeChange(() => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
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

  // Get candle data for current TF
  const raw = vApp.candleData[vApp.tf];
  if (!raw || !raw.length) {
    vApp.candleSeries.setData([]);
    _vAllMarkers = [];
    rebuildValidateMarkers();
    if (_vSessionPrimitive) _vSessionPrimitive.setBands([]);
    updateDetectionCounts();
    return;
  }

  // Map candle data — filter by current day if we have a day selected
  let candles = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    _rawTime: c.time,
  })).filter(b => b.time != null);

  // Filter candles to the selected day
  if (vApp.day) {
    candles = candles.filter(c => {
      // Strip timezone, check date prefix
      const clean = (c._rawTime || '').replace(/[+-]\d{2}:\d{2}$/, '');
      return clean.startsWith(vApp.day);
    });
  }

  candles.sort((a, b) => a.time - b.time);

  // Set candle data (strip the _rawTime helper)
  const chartData = candles.map(c => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));

  vApp.candleSeries.setData(chartData);

  // Build candle time lookup sets
  _vCandleTimeSet = new Set(chartData.map(c => c.time));
  _vCandleTimesArr = chartData.map(c => c.time);

  // Build all markers (unfiltered) and store
  _vAllMarkers = buildValidateMarkers();

  // Apply toggle filters
  rebuildValidateMarkers();

  // Session bands for current day
  const bands = getValidateSessionBandsForDay(vApp.day);
  if (_vSessionPrimitive) {
    _vSessionPrimitive.setBands(bands);
  }

  // Fit content
  vApp.chart.timeScale().fitContent();

  // Force primitive update after layout settles
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

  // Update detection count summary
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
    const primColor = vPrimColor(primName);

    // Get detections for current TF (or 'global' for primitives that don't have per-TF data)
    const tfDets = byTf[vApp.tf] || byTf['global'] || [];

    // Filter to current day
    const dayDets = filterValidateDetectionsByDay(tfDets, vApp.day);

    for (const det of dayDets) {
      const barTime = findValidateNearestCandleTime(det.time);
      if (barTime == null) continue;

      const isBullish = det.direction === 'bullish' || det.direction === 'high';
      const isBearish = det.direction === 'bearish' || det.direction === 'low';

      markers.push({
        time: barTime,
        position: isBearish ? 'aboveBar' : 'belowBar',
        shape: isBearish ? 'arrowDown' : 'arrowUp',
        color: primColor,
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

  // Find nearest candle time (within 15 min for 1m, 1h for larger TFs)
  const maxDiff = vApp.tf === '1m' ? 900 : 3600;
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
  if (!vApp.sessionData || !dayKey) return [];
  return vApp.sessionData
    .filter(b => b.forex_day === dayKey)
    .map(b => ({
      startTS: toTS(b.start_time),
      endTS: toTS(b.end_time),
      color: b.color,
      border: b.border,
      session: b.session,
      label: b.label,
    }))
    .filter(b => b.startTS != null && b.endTS != null);
}
